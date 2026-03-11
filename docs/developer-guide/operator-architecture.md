# cr8tor Operator - Developer Reference

> A developer guide on the existing operator structure.

---

## Overview

The `cr8tor-operator` is a Kubernetes operator written in Python using the [Kopf](https://kopf.readthedocs.io/) framework. It watches for changes to custom Kubernetes resources (CRDs) and reconciles them against external systems. For example, **Keycloak** (identity/SSO) and native **Kubernetes** resources (namespaces, quotas, PVCs, network policies).

The two main things it manages are:

1. **Identity** - Users, Groups, Keycloak OIDC clients, and research Projects
2. **Workspaces** - On-demand VDI (Virtual Desktop) instances

---

## Source Layout

```
src/cr8tor/
├── main.py                   # Operator entry point
├── handlers/                 # Kopf event handlers ("what to do")
│   ├── identity_handler.py   # User / Group / KeycloakClient / Project
│   └── vdi_handler.py        # VDIInstance
├── services/                 # Custom logic called by handlers
│   ├── client.py             # Keycloak connection factory
│   ├── user_manager.py       # Sync/delete users in Keycloak
│   ├── group_manager.py      # Sync/delete groups in Keycloak
│   ├── client_manager.py     # Sync/delete OIDC clients in Keycloak
│   ├── namespace_manager.py  # K8s namespaces, ResourceQuota, LimitRange, RoleBinding
│   ├── storage_manager.py    # PVC creation/deletion for VDI and notebooks
│   ├── network_policy_manager.py  # CiliumNetworkPolicy per project namespace
│   └── utils.py              # Password generation helpers
├── plugins/                  # Plugin system
│   ├── base.py               # Abstract PluginBase class
│   ├── registry.py           # PluginRegistry singleton (discovers + wires plugins)
│   ├── identity.py           # IdentityPlugin
│   └── workspaces.py         # WorkspacesPlugin
├── crd/                      # CRD schema generation + registration
│   ├── base.py               # Pydantic base classes for CRD spec/status
│   ├── registry.py           # CRDRegistry singleton + @register decorator
│   └── generator.py          # KareCRDManager - generates + applies CRD YAML
└── models/
    └── registry_config.py    # Maps cr8tor-metamodel models -> CRD metadata
```

---

## Startup Sequence (`main.py`)

On startup, the operator does these steps in order:

1. **Apply CRDs** - `KareCRDManager` generates CRD schemas from Pydantic models and applies them to the cluster (in-memory by default, no YAML files written unless `GENERATE_CRD_FILES=true`).
2. **Discover plugins** - `PluginRegistry` loads the two built-in plugins (`identity`, `workspaces`) and any external plugins registered via Python entry points (`cr8tor_plugins`).
3. **Initialise plugins** - each plugin validates its dependencies (e.g. Keycloak realm, VDI templates).
4. **Register handlers** - each plugin's `register_handlers()` is called, which imports the relevant handler module. Kopf picks up the `@kopf.on.*` decorators automatically.
5. **Run** - `kopf.run()` starts the event loop.

---

## CRDs (Custom Resource Definitions)

The operator owns five CRDs. All are `v1alpha1`. Their schemas come from Pydantic models in the `cr8tor-metamodel` package (a separate repo).

| Kind | API Group | Plural | Namespace stored in | Handler |
|---|---|---|---|---|
| `User` | `identity.karectl.io` | `users` | `keycloak` | `identity_handler` |
| `Group` | `identity.karectl.io` | `groups` | `keycloak` | `identity_handler` |
| `KeycloakClient` | `identity.karectl.io` | `keycloakclients` | `keycloak` | `identity_handler` |
| `Project` | `research.karectl.io` | `projects` | `keycloak` | `identity_handler` |
| `VDIInstance` | `karectl.io` | `vdiinstances` | project namespace | `vdi_handler` |

The mapping is declared in `models/registry_config.py`:

```python
CRDRegistry.register("identity.karectl.io", "v1alpha1", "User", "users")(User)
CRDRegistry.register("research.karectl.io", "v1alpha1", "Project", "projects")(ProjectSpec)
# etc.
```

---

## Handlers - Explains each CRD

### `User` (`identity_handler.py`)

**On create/update/resume:**
- Ensures the Keycloak realm exists.
- Creates or updates the user in Keycloak
- If newly created, generates a temporary password and writes it to the CRD status.
- Looks up all `Group` CRDs to find which research projects the user belongs to.
- For each project, creates a **notebook PVC** in the project's namespace (named using `{workspace_type}-{user_uid}-{project_uid}` to avoid collisions on normalised names).

**On delete:**
- Deletes the user from Keycloak.
- PVCs are deliberately **kept** - they are cleaned up when the Project is deleted (namespace cascade).

---

### `Group` (`identity_handler.py`)

**On create/update:**
- Creates or updates the group in Keycloak.
- Reconciles group membership: removes users no longer listed in `spec.members`, adds new ones.
- For each member, creates **notebook PVCs** in every project listed in `spec.projects`.

**On delete:**
- Deletes the group from Keycloak.

---

### `KeycloakClient` (`identity_handler.py`)

**On create/update/resume:**
- Creates or updates an OIDC client in Keycloak.
- Supports reading the client secret from a Kubernetes Secret (`secretRef`)
- Assigns default/optional client scopes.
- Creates/updates protocol mappers.

**On delete:**
- Deletes the OIDC client from Keycloak.

---

### `Project` (`identity_handler.py`)

**On create/update/resume** - provisions the full project environment in one shot:

1. **Namespace** - creates `project-{name}` with standard labels.
2. **ResourceQuota** - CPU/memory/pod/PVC limits
3. **LimitRange** - default container CPU/memory limits.
4. **JupyterHub RoleBinding** - grants the `hub` service account in the `jupyterhub` namespace permission to create pods/PVCs/services inside the project namespace.
5. **CiliumNetworkPolicy** - isolates the namespace: allows intra-namespace traffic, traffic from infrastructure namespaces (`jupyterhub`, `backend`, `cr8tor`, `keycloak`), DNS, and outbound internet. Blocks cross-project traffic.

**On delete:**
- Deletes the project namespace (which cascades and removes all resources inside it, including PVCs).

---

### `VDIInstance` (`vdi_handler.py`)

**On create:**
- Generates a unique Linux username (`vdx-{user}-{project}`).
- Generates a random VDI password (stored in CRD status).
- Resolves storage config using a priority chain: VDI spec > Project CRD > Helm values.
- If storage is configured, creates a **VDI PVC** using k8s UIDs for the name.
- Resolves scheduling config (nodeSelector, tolerations, affinity, resource limits) the same way.
- Copies `vdi-init-scripts` ConfigMap from the `cr8tor` namespace into the project namespace.
- Renders a **Jinja2 pod template** (`vdi-pod-template.yaml.j2`) with all resolved values.
- Creates the Pod and a ClusterIP Service.
- Sets an owner reference on all created resources so they are garbage-collected if the CRD is deleted.

**On update:**
- If environment variables changed (e.g. token refresh), deletes the pod so it restarts with new env vars.

**On delete:**
- Deletes the Pod and Service.
- Deletes the PVC unless `spec.storage.persist: true`.

---

## Plugin System

The plugin system provides a clean extension point. Each plugin is a class that inherits from `PluginBase` and declares:

- `name` / `version` / `description` (metadata)
- `models` - list of Pydantic model classes this plugin contributes to the CRD registry
- `_initialise_plugin()` - setup logic (e.g. ensure Keycloak realm, check templates exist)
- `register_handlers()` - imports the handler module(s) for this plugin

The `PluginRegistry` (singleton) discovers plugins and wires everything together.

Currently two built-in plugins exist:

| Plugin class | File | CRDs it manages |
|---|---|---|
| `IdentityPlugin` | `plugins/identity.py` | User, Group, KeycloakClient, Project |
| `WorkspacesPlugin` | `plugins/workspaces.py` | VDIInstance |

External plugins can theoretically be registered via Python entry points (group `cr8tor_plugins`) — the discovery code exists in `registry.py` — but **no `cr8tor_plugins` entry point group is declared anywhere** in `pyproject.toml`. This is a forward-looking hook that is not yet wired up.

---

## CRD Generation System (`crd/`)

The CRD schemas are **generated at startup** from Pydantic models

- **`CRDRegistry`** - a singleton with a `@register` class decorator. Stamps `_crd_group`, `_crd_version`, `_crd_kind`, etc. onto the model class and stores it in a dict.
- **`KareCRDManager`** - calls `CRDRegistry.discover_models()`, then for each registered model:
  - Calls `model.model_json_schema()` to get the Pydantic schema.
  - Converts it to OpenAPI v3 format via `OpenAPIConverter`.
  - Builds the full `CustomResourceDefinition` dict.
  - Applies it to the cluster via `ApiextensionsV1Api` (create or replace).
- Hash-based change detection avoids unnecessary regeneration.

Controlled by env vars:
- `MANAGE_CRDS=true` - whether to apply CRDs at all (default: `true`)
- `GENERATE_CRD_FILES=false` - whether to also write YAML files to disk (default: `false`)

---

## Data Models (`cr8tor-metamodel`)

All CRD spec field definitions come from **LinkML schemas defined in the `cr8tor-metamodel` repository** (a separate git dependency). The operator defines no spec fields itself.

The LinkML schemas are compiled into Pydantic models (`cr8tor_metamodel_pydantic.py`) and consumed here. The flow is:

```
LinkML schema  (cr8tor-metamodel repo)
  -> generates ->  Pydantic models  (cr8tor_metamodel.datamodel.cr8tor_metamodel_pydantic)
    -> imported by ->  models/registry_config.py  +  plugins/
      -> wrapped by ->  CRDRegistry.register(...)
        -> converted by ->  KareCRDManager  ->  applied to cluster as CRDs
```
---

## Helm Chart

The operator is deployed via the Helm chart at `charts/cr8tor-operator/`. Key configurable values:

| Value | What it controls |
|---|---|
| `keycloak.adminSecretName` | K8s secret with Keycloak admin credentials |
| `identity.namespace` | Namespace where User/Group CRDs are stored (default: `keycloak`) |
| `config.manageCrds` | Whether operator auto-applies CRDs on startup |
| `storage.defaultVdiSize` / `defaultNotebookSize` | Cluster-wide default PVC sizes |
| `storage.maxVdiSize` / `maxNotebookSize` | Hard caps on PVC sizes (Project CRD values are capped here) |
| `storage.defaultPersist` | Whether VDI PVCs survive VDI deletion by default |
| `vdi.defaultResources` | Default CPU/memory for VDI pods |
| `vdiTemplates.enabled` | Deploy VDI pod Jinja2 templates as a ConfigMap |

---

## Extending the Operator - Where to Update ?

### Adding a new CRD and handler

Suppose you want to add a `DatasetCatalog` resource.

**Step 1 - Add/update the model in `cr8tor-metamodel`**
Add a new class to the **LinkML schema** in the `cr8tor-metamodel` repo, then regenerate the Pydantic output. The resulting `DatasetCatalog` class will appear in `cr8tor_metamodel_pydantic.py`.

**Step 2 - Register the CRD mapping**
In `src/cr8tor/models/registry_config.py`:
```python
from cr8tor_metamodel.datamodel.cr8tor_metamodel_pydantic import DatasetCatalog

CRDRegistry.register(
    "research.karectl.io", "v1alpha1", "DatasetCatalog", "datasetcatalogs"
)(DatasetCatalog)
```

**Step 3 - Write the handler**
Create `src/cr8tor/handlers/catalog_handler.py` with Kopf decorators:
```python
import kopf

@kopf.on.create("research.karectl.io", "v1alpha1", "datasetcatalog")
@kopf.on.update("research.karectl.io", "v1alpha1", "datasetcatalog")
def catalog_create_update(spec, meta, patch, **kwargs):
    # your logic here
    pass

@kopf.on.delete("research.karectl.io", "v1alpha1", "datasetcatalog")
def catalog_delete(spec, meta, **kwargs):
    pass
```

**Step 4 - Create a plugin** (or add to an existing one)
Create `src/cr8tor/plugins/catalog.py`:
```python
from .base import PluginBase

class CatalogPlugin(PluginBase):
    @property
    def name(self): return "catalog"
    @property
    def version(self): return "1.0.0"
    @property
    def description(self): return "Manages dataset catalog resources"
    @property
    def models(self):
        from cr8tor_metamodel.datamodel.cr8tor_metamodel_pydantic import DatasetCatalog
        return [DatasetCatalog]
    def register_handlers(self):
        from cr8tor.handlers import catalog_handler
```

**Step 5 - Register the plugin**
In `src/cr8tor/plugins/registry.py`, add it to `_load_builtin_plugins()`:
```python
builtin_plugins = [
    "cr8tor.plugins.identity",
    "cr8tor.plugins.workspaces",
    "cr8tor.plugins.catalog",   # <-- add this
]
```

**Step 6 - Update the handlers `__init__.py`**
In `src/cr8tor/handlers/__init__.py`:
```python
from . import catalog_handler
```

**That's it.** On next startup, the operator will:
- Generate and apply the `datasetcatalogs.research.karectl.io` CRD automatically.
- Start watching for `DatasetCatalog` resources and calling your handler.

---

### Adding a new service

If your handler needs calling an external API or managing k8s resources, put it in a new file under `services/` and import it from the handler. Keep services stateless as they should just take arguments and return results.

---

### Modifying storage behaviour

Storage resolution uses a layered priority chain implemented in `services/storage_manager.py`:

```
VDI spec > Project CRD spec > Helm values
```

To change defaults or add a new storage type, edit `resolve_vdi_storage_config()` or `resolve_notebook_storage_config()` - or add a new resolver function following the same pattern.

---

### Adding a new Helm value

1. Add it to `charts/cr8tor-operator/values.yaml`.
2. Pass it as an env var in `charts/cr8tor-operator/templates/deployment.yaml`.
3. Read it in the relevant service using `os.environ.get(...)`.

---

## Internal Environment Variables

| Variable | Default | Used by |
|---|---|---|
| `KEYCLOAK_URL` | `http://keycloak.keycloak/` | `services/client.py` |
| `KEYCLOAK_ADMIN` | *(required)* | `services/client.py` |
| `KEYCLOAK_ADMIN_PASSWORD` | *(required)* | `services/client.py` |
| `KEYCLOAK_REALM` | `karectl-app` | `services/client.py` |
| `KEYCLOAK_VERIFY_TLS` | `true` | `services/client.py` |
| `IDENTITY_NAMESPACE` | `keycloak` | `identity_handler`, `storage_manager` |
| `MANAGE_CRDS` | `true` | `main.py` |
| `GENERATE_CRD_FILES` | `false` | `main.py` |
| `STORAGE_DEFAULT_VDI_SIZE` | *(empty)* | `storage_manager` |
| `STORAGE_MAX_VDI_SIZE` | *(empty)* | `storage_manager` |
| `STORAGE_DEFAULT_NOTEBOOK_SIZE` | *(empty)* | `storage_manager` |
| `STORAGE_MAX_NOTEBOOK_SIZE` | *(empty)* | `storage_manager` |
| `STORAGE_DEFAULT_STORAGE_CLASS` | *(empty)* | `storage_manager` |
| `STORAGE_DEFAULT_PERSIST` | `false` | `storage_manager` |
| `LOG_LEVEL` | `INFO` | `main.py` |
| `WORKER_LIMIT` | `5` | `main.py` |
