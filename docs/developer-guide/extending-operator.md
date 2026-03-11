# Extending the cr8tor Operator

> A comprehensive guide to adding new custom resources and external integrations to the cr8tor operator.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture Summary](#architecture-summary)
3. [Extension Workflow](#extension-workflow)
4. [Step 1: Define the CRD Model](#step-1-define-the-crd-model)
5. [Step 2: Register the CRD](#step-2-register-the-crd)
6. [Step 3: Create the Service Layer](#step-3-create-the-service-layer)
7. [Step 4: Create the Handler](#step-4-create-the-handler)
8. [Step 5: Create the Plugin](#step-5-create-the-plugin)
9. [Step 6: Register the Plugin](#step-6-register-the-plugin)
10. [Step 7: Update Helm Chart](#step-7-update-helm-chart)
11. [Step 8: Configure RBAC](#step-8-configure-rbac)
12. [Working Example: Gitea Integration](#working-example-gitea-integration)
13. [Testing Your Extension](#testing-your-extension)
14. [Best Practices](#best-practices)
15. [Troubleshooting](#troubleshooting)

---

## Overview

The cr8tor operator is built with extensibility in mind. New custom resources can be added by following a structured process that involves:

- **Models** — Pydantic classes that define the CRD schema
- **Services** — Business logic for interacting with external systems
- **Handlers** — Kopf-based event handlers that respond to CRD changes
- **Plugins** — Modular units that bundle models, services, and handlers together

This guide walks through each step required to add a new custom resource using **Gitea integration** as a real-world reference example.

---

## Architecture Summary

Before extending the operator, understand its core components:

```
src/cr8tor/
├── main.py                   # Operator entry point (startup/shutdown)
├── handlers/                 # Kopf event handlers
├── services/                 # Business logic layer
├── plugins/                  # Plugin system
├── crd/                      # CRD schema generation
└── models/                   # Pydantic model definitions
```

### Key Concepts

| Component | Purpose |
|-----------|---------|
| **CRDRegistry** | Singleton that maps Pydantic models to CRD metadata |
| **PluginBase** | Abstract base class all plugins inherit from |
| **PluginRegistry** | Discovers, initialises, and manages plugins |
| **KareCRDManager** | Generates and applies CRDs to the cluster |

### Startup Flow

```
main.py startup
  → CRD generation (KareCRDManager)
  → Plugin discovery (PluginRegistry.discover_plugins)
  → Plugin initialization (PluginRegistry.initialise_all_plugins)
  → Handler registration (PluginRegistry.register_all_handlers)
  → Kopf event loop
```

---

## Extension Workflow

Adding a new custom resource follows this workflow:

```
┌─────────────────────────────────────────────────────────────────┐
│  1. Define Model   →   2. Register CRD   →   3. Create Service  │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│  4. Create Handler  →  5. Create Plugin  →  6. Register Plugin  │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│  7. Update Helm     →   8. Configure RBAC   →   9. Test         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Step 1: Define the CRD Model

CRD schemas are defined using Pydantic models. Create your model in `src/cr8tor/models/`.

### Model Location Options

1. **Add to existing file** — If your resource relates to an existing domain (e.g., identity-related resources go in `identity.py`)
2. **Create new file** — For new domains, create a new file (e.g., `git_hosting.py`)

### Model Structure

All CRD spec models must inherit from `CRDSpec`:

```python
# src/cr8tor/models/your_domain.py

from pydantic import Field
from typing import List, Optional, Dict, Any
from cr8tor.crd.base import CRDSpec
from cr8tor.crd.registry import CRDRegistry


class SubResourceConfig(CRDSpec):
    """Nested configuration object (not a CRD itself)."""
    
    name: str = Field(..., description="Resource name")
    enabled: bool = Field(default=True, description="Whether enabled")


@CRDRegistry.register("yourdomain.karectl.io", "v1alpha1", "YourResource", "yourresources")
class YourResourceSpec(CRDSpec):
    """Your Resource CRD specification."""

    # Required fields use ... as default
    name: str = Field(..., description="Unique name for the resource")
    
    # Optional fields with defaults
    description: str = Field(default="", description="Human-readable description")
    enabled: bool = Field(default=True, description="Whether the resource is active")
    
    # Lists with factory defaults
    tags: List[str] = Field(default_factory=list, description="Resource tags")
    
    # Optional nested objects
    config: Optional[SubResourceConfig] = Field(
        default=None, description="Additional configuration"
    )
    
    # Flexible dict fields
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
```

### Field Types Reference

| Pydantic Type | Kubernetes Schema Type | Example |
|--------------|------------------------|---------|
| `str` | `string` | `name: str` |
| `int` | `integer` | `replicas: int` |
| `bool` | `boolean` | `enabled: bool` |
| `float` | `number` | `ratio: float` |
| `List[str]` | `array` (items: string) | `tags: List[str]` |
| `Dict[str, Any]` | `object` (additionalProperties) | `labels: Dict[str, Any]` |
| `Optional[T]` | nullable type | `config: Optional[str]` |

### Base Classes

```python
from cr8tor.crd.base import CRDSpec, CRDStatus, CRDMetadata, CRDCondition
```

- **CRDSpec** — Base for all spec objects. Strict validation, no extra fields allowed.
- **CRDStatus** — Base for status objects. Flexible, allows extra fields.
- **CRDCondition** — Standard Kubernetes condition structure.

---

## Step 2: Register the CRD

CRDs are registered using the `@CRDRegistry.register` decorator.

### Decorator Signature

```python
@CRDRegistry.register(
    group="yourdomain.karectl.io",     # API group
    version="v1alpha1",                 # API version
    kind="YourResource",                # Kind name (PascalCase)
    plural="yourresources",             # Plural name (lowercase)
    scope="Namespaced"                  # "Namespaced" or "Cluster"
)
class YourResourceSpec(CRDSpec):
    ...
```

### API Group Conventions

| Domain | API Group | Use For |
|--------|-----------|---------|
| Identity | `identity.karectl.io` | Users, Groups, Auth clients |
| Research | `research.karectl.io` | Projects, Datasets |
| Workspaces | `karectl.io` | VDI instances, environments |
| Git Hosting | `git.karectl.io` | Gitea, GitLab resources |

### Automatic Discovery

Models are auto-discovered at startup when:

1. The model file is in `src/cr8tor/models/`
2. The model file is imported in `src/cr8tor/models/__init__.py`

Update `__init__.py` to include your new module:

```python
# src/cr8tor/models/__init__.py

from . import identity
from . import workspaces
from . import your_domain  # Add this

__all__ = ["identity", "workspaces", "your_domain"]
```

---

## Step 3: Create the Service Layer

Services contain business logic for interacting with external systems. They are stateless functions/classes that handlers call.

### Service Structure

For external integrations, create a package under `src/cr8tor/services/`:

```
services/
├── gitea/              # Gitea integration package
│   ├── __init__.py     # Public exports
│   ├── client.py       # HTTP client, auth, config
│   └── manager.py      # Business logic functions
```

### Client Pattern (for HTTP APIs)

```python
# src/cr8tor/services/your_service/client.py

import os
import logging
import httpx

logger = logging.getLogger(__name__)


def get_verify_tls():
    """Get TLS verification from environment."""
    return os.environ.get("YOUR_SERVICE_VERIFY_TLS", "true").lower() in ("true", "1", "yes")


def get_service_url():
    """Get service URL from environment."""
    return os.environ.get("YOUR_SERVICE_URL", "http://your-service.default.svc.cluster.local")


def get_api_token():
    """Get API token from environment."""
    return os.environ.get("YOUR_SERVICE_API_TOKEN")


def is_service_enabled():
    """Check if integration is enabled (token present)."""
    return bool(get_api_token())


class YourServiceClient:
    """Async HTTP client for Your Service API."""

    def __init__(self):
        self.base_url = get_service_url().rstrip("/")
        self.token = get_api_token()
        self.verify_tls = get_verify_tls()

        if not self.token:
            raise ValueError("YOUR_SERVICE_API_TOKEN environment variable is required")

    def _get_headers(self):
        """Get headers for API requests."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def get(self, path):
        """Make GET request."""
        async with httpx.AsyncClient(verify=self.verify_tls, timeout=30.0) as client:
            url = f"{self.base_url}{path}"
            logger.debug(f"GET {url}")
            response = await client.get(url, headers=self._get_headers())
            response.raise_for_status()
            return response.json()

    async def post(self, path, data):
        """Make POST request."""
        async with httpx.AsyncClient(verify=self.verify_tls, timeout=30.0) as client:
            url = f"{self.base_url}{path}"
            logger.debug(f"POST {url}")
            response = await client.post(url, headers=self._get_headers(), json=data)
            response.raise_for_status()
            return response.json() if response.content else {}

    async def delete(self, path):
        """Make DELETE request."""
        async with httpx.AsyncClient(verify=self.verify_tls, timeout=30.0) as client:
            url = f"{self.base_url}{path}"
            logger.debug(f"DELETE {url}")
            response = await client.delete(url, headers=self._get_headers())
            response.raise_for_status()


def get_client():
    """Get a new client instance."""
    return YourServiceClient()
```

### Manager Pattern (Business Logic)

```python
# src/cr8tor/services/your_service/manager.py

import logging
from httpx import HTTPStatusError
from .client import get_client

logger = logging.getLogger(__name__)


async def ensure_resource(name, description="", **kwargs):
    """Create resource if it doesn't exist.
    
    Args:
        name: Resource name
        description: Resource description
        **kwargs: Additional configuration
        
    Returns:
        dict: {"created": bool, "resource": dict}
    """
    client = get_client()
    
    # Check if exists
    try:
        resource = await client.get(f"/api/v1/resources/{name}")
        logger.info(f"Resource '{name}' already exists")
        return {"created": False, "resource": resource}
    except HTTPStatusError as e:
        if e.response.status_code != 404:
            raise

    # Create resource
    payload = {
        "name": name,
        "description": description,
        **kwargs
    }

    try:
        resource = await client.post("/api/v1/resources", payload)
        logger.info(f"Created resource: {name}")
        return {"created": True, "resource": resource}
    except HTTPStatusError as e:
        logger.error(f"Failed to create resource '{name}': {e}")
        raise


async def delete_resource(name):
    """Delete a resource.
    
    Args:
        name: Resource name
        
    Returns:
        bool: True if deleted successfully
    """
    client = get_client()

    try:
        await client.delete(f"/api/v1/resources/{name}")
        logger.info(f"Deleted resource: {name}")
        return True
    except HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.info(f"Resource '{name}' already deleted or not found")
            return True
        logger.error(f"Failed to delete resource '{name}': {e}")
        raise
```

### Package Exports

```python
# src/cr8tor/services/your_service/__init__.py

from .client import get_client, is_service_enabled, get_verify_tls
from .manager import (
    ensure_resource,
    delete_resource,
)

__all__ = [
    "get_client",
    "get_verify_tls",
    "is_service_enabled",
    "ensure_resource",
    "delete_resource",
]
```

---

## Step 4: Create the Handler

Handlers use [Kopf](https://kopf.readthedocs.io/) decorators to respond to Kubernetes events.

### Handler Location

Create handlers in `src/cr8tor/handlers/`:

```python
# src/cr8tor/handlers/your_handler.py

import logging
import kopf
from cr8tor.services.your_service import (
    is_service_enabled,
    ensure_resource,
    delete_resource,
)

logger = logging.getLogger(__name__)


@kopf.on.create("yourdomain.karectl.io", "v1alpha1", "yourresource")
@kopf.on.update("yourdomain.karectl.io", "v1alpha1", "yourresource")
async def resource_create_update(body, spec, meta, patch, **kwargs):
    """Handle resource creation and updates.
    
    Args:
        body: Full resource body
        spec: Resource spec dict
        meta: Resource metadata dict
        patch: Object to patch status/metadata
        **kwargs: Additional Kopf arguments
    """
    resource_name = spec["name"]
    description = spec.get("description", "")
    
    logger.info(f"Processing resource: {resource_name}")
    
    # Sync to external service
    if is_service_enabled():
        try:
            result = await ensure_resource(
                name=resource_name,
                description=description,
            )
            
            # Update CRD status
            patch.status["externalResource"] = {
                "synced": True,
                "created": result["created"],
            }
            
            kopf.info(
                meta,
                reason="ResourceSynced",
                message=f"Resource {resource_name} synced successfully",
            )
            
        except Exception as e:
            logger.error(f"Failed to sync resource {resource_name}: {e}")
            patch.status["externalResource"] = {
                "synced": False,
                "error": str(e),
            }
            kopf.warn(
                meta,
                reason="SyncFailed",
                message=f"Failed to sync resource: {e}",
            )
    else:
        logger.info("External service not enabled, skipping sync")
        patch.status["externalResource"] = {"synced": False, "reason": "disabled"}


@kopf.on.delete("yourdomain.karectl.io", "v1alpha1", "yourresource")
async def resource_delete(body, spec, meta, **kwargs):
    """Handle resource deletion.
    
    Args:
        body: Full resource body
        spec: Resource spec dict
        meta: Resource metadata dict
        **kwargs: Additional Kopf arguments
    """
    resource_name = spec["name"]
    
    logger.info(f"Deleting resource: {resource_name}")
    
    if is_service_enabled():
        try:
            await delete_resource(resource_name)
            kopf.info(
                meta,
                reason="ResourceDeleted",
                message=f"Resource {resource_name} deleted from external service",
            )
        except Exception as e:
            logger.error(f"Failed to delete resource {resource_name}: {e}")
            kopf.warn(
                meta,
                reason="DeleteFailed",
                message=f"Failed to delete from external service: {e}",
            )
```

### Handler Decorator Reference

| Decorator | When Triggered |
|-----------|----------------|
| `@kopf.on.create` | Resource created |
| `@kopf.on.update` | Resource spec changed |
| `@kopf.on.delete` | Resource deleted |
| `@kopf.on.resume` | Operator restarts (existing resources) |
| `@kopf.on.field` | Specific field changed |

### Kombining Decorators

Multiple decorators can be stacked:

```python
@kopf.on.create("yourdomain.karectl.io", "v1alpha1", "yourresource")
@kopf.on.update("yourdomain.karectl.io", "v1alpha1", "yourresource")
@kopf.on.resume("yourdomain.karectl.io", "v1alpha1", "yourresource")
async def resource_sync(spec, meta, patch, **kwargs):
    ...
```

### Update Handlers Init

Add your handler to `src/cr8tor/handlers/__init__.py`:

```python
# src/cr8tor/handlers/__init__.py

from . import identity_handler
from . import vdi_handler
from . import project_sync_handler
from . import your_handler  # Add this

__all__ = ["identity_handler", "vdi_handler", "project_sync_handler", "your_handler"]
```

---

## Step 5: Create the Plugin

Plugins bundle models and handlers together. They manage initialization and cleanup.

### Plugin Structure

```python
# src/cr8tor/plugins/your_plugin.py

import logging
from .base import PluginBase

logger = logging.getLogger(__name__)


class YourPlugin(PluginBase):
    """Plugin for managing your custom resources."""

    @property
    def name(self) -> str:
        return "your-plugin"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Manages your custom resources through Kubernetes CRDs"

    @property
    def models(self):
        """Return list of CRD models this plugin provides."""
        from cr8tor.models.your_domain import YourResourceSpec
        return [YourResourceSpec]

    def _initialise_plugin(self):
        """Custom initialization logic.
        
        Called once during operator startup. Use for:
        - Validating external service connectivity
        - Checking required configurations
        - Creating baseline resources
        """
        logger.info("Initializing your plugin...")

        # Example: Validate external service
        try:
            from cr8tor.services.your_service import is_service_enabled
            
            if is_service_enabled():
                logger.info("External service integration enabled")
            else:
                logger.warning("External service token not configured, integration disabled")
                
        except Exception as e:
            logger.warning(f"Could not validate external service: {e}")

    def register_handlers(self):
        """Register Kopf handlers for this plugin's CRDs."""
        logger.info("Registering your plugin handlers...")

        try:
            from cr8tor.handlers import your_handler
            logger.info("Your plugin handlers registered successfully")
        except Exception as e:
            logger.error(f"Failed to register handlers: {e}")
            raise

    def _shutdown_plugin(self):
        """Custom shutdown logic.
        
        Called during operator shutdown. Use for:
        - Closing connections
        - Cleanup resources
        """
        logger.info("Shutting down your plugin...")
```

### Plugin Base Class Methods

| Method | Required | Purpose |
|--------|----------|---------|
| `name` | Yes | Unique plugin identifier |
| `version` | Yes | Plugin version string |
| `description` | Yes | Human-readable description |
| `models` | Yes | List of CRD model classes |
| `_initialise_plugin()` | No | Custom startup logic |
| `register_handlers()` | No | Import handler modules |
| `_shutdown_plugin()` | No | Custom cleanup logic |

---

## Step 6: Register the Plugin

Add your plugin to the plugin registry.

### Update Registry

Edit `src/cr8tor/plugins/registry.py`:

```python
def _load_builtin_plugins(self):
    """Load built-in plugins from cr8tor.plugins package."""
    builtin_plugins = [
        "cr8tor.plugins.identity",
        "cr8tor.plugins.workspaces",
        "cr8tor.plugins.project_sync",
        "cr8tor.plugins.your_plugin",  # Add this
    ]
    # ... rest of method
```

### Alternative: Entry Points (External Plugins)

For external plugins distributed as separate packages, use Python entry points:

```toml
# In external package's pyproject.toml
[project.entry-points."cr8tor_plugins"]
your-plugin = "your_package.plugins:YourPlugin"
```

---

## Step 7: Update Helm Chart

### Add Values

Edit `charts/cr8tor-operator/values.yaml`:

```yaml
# Your Service Configuration
yourService:
  # Set to true to enable integration
  enabled: false
  # Secret containing API credentials
  adminSecretName: "your-service-credentials"
```

### Add Environment Variables

Edit `charts/cr8tor-operator/templates/deployment.yaml`:

```yaml
env:
  # ... existing env vars ...
  
  # Your Service configuration
  {{- if .Values.yourService.enabled }}
  - name: YOUR_SERVICE_URL
    valueFrom:
      configMapKeyRef:
        name: {{ .Values.servicesConfigMapName }}
        key: your-service-url
        optional: true
  - name: YOUR_SERVICE_VERIFY_TLS
    valueFrom:
      configMapKeyRef:
        name: {{ .Values.servicesConfigMapName }}
        key: your-service-verify-tls
        optional: true
  - name: YOUR_SERVICE_API_TOKEN
    valueFrom:
      secretKeyRef:
        name: {{ .Values.yourService.adminSecretName }}
        key: api-token
        optional: true
  {{- end }}
```

### Add Init Container (if needed)

If your service requires a secret to exist before startup:

```yaml
{{- if .Values.yourService.enabled }}
initContainers:
  - name: wait-for-your-service-secret
    image: alpine/k8s:1.29.0
    command:
      - /bin/sh
      - -c
      - |
        echo "Waiting for your-service credentials secret..."
        until kubectl get secret {{ .Values.yourService.adminSecretName }} -n {{ .Release.Namespace }} >/dev/null 2>&1; do
          echo "  Secret not found, waiting..."
          sleep 5
        done
        echo "Secret found..."
{{- end }}
```

---

## Step 8: Configure RBAC

Add permissions for your new CRD in `charts/cr8tor-operator/templates/rbac.yaml`:

```yaml
rules:
  # ... existing rules ...
  
  # Your Domain CRDs
  - apiGroups: ["yourdomain.karectl.io"]
    resources: ["yourresources"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  
  # Status updates for your CRDs
  - apiGroups: ["yourdomain.karectl.io"]
    resources: ["*/status"]
    verbs: ["get", "update", "patch"]
```

---

## Working Example: Gitea Integration

The Gitea integration demonstrates a complete external service integration.

### File Structure

```
src/cr8tor/
├── services/
│   └── gitea/
│       ├── __init__.py      # Public exports
│       ├── client.py        # HTTP client + config
│       └── manager.py       # Business logic
├── models/
│   └── identity.py          # GiteaTeamConfig nested in GroupSpec
└── handlers/
    └── identity_handler.py  # Gitea hooks in user/group/project handlers
```

### Key Integration Points

#### 1. Model Definition (Optional Gitea Config)

```python
# src/cr8tor/models/identity.py

class GiteaTeamConfig(CRDSpec):
    """Gitea team configuration for a group."""

    team_name: Optional[str] = Field(
        default=None,
        description="Team name in Gitea organisations",
    )
    permission: str = Field(
        default="write",
        description="Team permission level: read, write, or admin",
    )


@CRDRegistry.register("identity.karectl.io", "v1alpha1", "Group", "groups")
class GroupSpec(CRDSpec):
    # ... other fields ...
    gitea: Optional[GiteaTeamConfig] = Field(
        default=None,
        description="Gitea team configuration for this group",
    )
```

#### 2. Service Client

```python
# src/cr8tor/services/gitea/client.py

def is_gitea_enabled():
    """Check if Gitea integration is enabled."""
    return bool(os.environ.get("GITEA_ADMIN_TOKEN"))

class GiteaClient:
    def __init__(self):
        self.base_url = os.environ.get("GITEA_URL", "http://gitea-http.gitea.svc.cluster.local:3000")
        self.token = os.environ.get("GITEA_ADMIN_TOKEN")
        # ... async HTTP methods ...
```

#### 3. Service Manager

```python
# src/cr8tor/services/gitea/manager.py

async def ensure_organisation(org_name, description="", visibility="private"):
    """Create Gitea organisation if not exists."""
    client = get_gitea_client()
    # ... implementation ...

async def ensure_team(org_name, team_name, permission="write"):
    """Create team in organisation if not exists."""
    # ... implementation ...

async def add_user_to_team(team_id, username):
    """Add user to team."""
    # ... implementation ...
```

#### 4. Handler Integration

```python
# src/cr8tor/handlers/identity_handler.py

from cr8tor.services.gitea import (
    is_gitea_enabled,
    ensure_organisation as gitea_ensure_organisation,
    ensure_team as gitea_ensure_team,
    add_user_to_team as gitea_add_user_to_team,
)

@kopf.on.create("research.karectl.io", "v1alpha1", "project")
async def project_create_update(body, spec, meta, patch, **kwargs):
    # ... other logic ...
    
    # Gitea organisation setup
    if is_gitea_enabled():
        org_name = f"project-{project_name}"
        try:
            await gitea_ensure_organisation(org_name, description)
            await gitea_ensure_team(org_name, "admins", "admin")
            await gitea_ensure_team(org_name, "members", "read")
            patch.status["gitea"] = {"organisation": org_name, "status": "ready"}
        except Exception as e:
            patch.status["gitea"] = {"status": "error", "error": str(e)}
```

#### 5. Helm Configuration

```yaml
# values.yaml
gitea:
  enabled: false
  adminSecretName: "gitea-api-credentials"

# deployment.yaml
{{- if .Values.gitea.enabled }}
- name: GITEA_URL
  valueFrom:
    configMapKeyRef:
      name: {{ .Values.servicesConfigMapName }}
      key: gitea-url
- name: GITEA_ADMIN_TOKEN
  valueFrom:
    secretKeyRef:
      name: {{ .Values.gitea.adminSecretName }}
      key: api-token
{{- end }}
```

---

## Testing Your Extension

### Local Development

1. **Run the operator locally:**
```bash
# Export required environment variables
export KEYCLOAK_ADMIN=admin
export KEYCLOAK_ADMIN_PASSWORD=admin
export YOUR_SERVICE_API_TOKEN=your-token

# Run with kopf
kopf run src/cr8tor/main.py --verbose
```

2. **Apply test CRD:**
```yaml
# test-resource.yaml
apiVersion: yourdomain.karectl.io/v1alpha1
kind: YourResource
metadata:
  name: test-resource
  namespace: default
spec:
  name: test
  description: "Test resource"
```

```bash
kubectl apply -f test-resource.yaml
```

3. **Check status:**
```bash
kubectl get yourresources -A
kubectl describe yourresource test-resource
```

### Unit Testing

```python
# tests/test_your_handler.py

import pytest
from unittest.mock import patch, AsyncMock

@pytest.mark.asyncio
async def test_resource_create():
    from cr8tor.handlers.your_handler import resource_create_update
    
    with patch('cr8tor.services.your_service.ensure_resource', new_callable=AsyncMock) as mock_ensure:
        mock_ensure.return_value = {"created": True, "resource": {}}
        
        patch_obj = type('Patch', (), {'status': {}})()
        
        await resource_create_update(
            body={},
            spec={"name": "test"},
            meta={"name": "test"},
            patch=patch_obj,
        )
        
        mock_ensure.assert_called_once()
        assert patch_obj.status["externalResource"]["synced"] is True
```

---

## Best Practices

### 1. Keep Services Stateless

Services should be pure functions that take inputs and return outputs. Don't store state.

```python
# Good
async def ensure_resource(name, description):
    client = get_client()  # New client per call
    return await client.post(...)

# Bad
_client = None
async def ensure_resource(name, description):
    global _client
    if not _client:
        _client = get_client()  # Shared state
    return await _client.post(...)
```

### 2. Use Async for External Calls

All HTTP calls to external services should be async:

```python
@kopf.on.create(...)
async def handler(spec, **kwargs):  # async handler
    result = await ensure_resource(...)  # await async service
```

### 3. Handle Idempotency

Handlers should be idempotent — running multiple times should produce the same result:

```python
async def ensure_resource(name):
    try:
        existing = await client.get(f"/resources/{name}")
        return {"created": False, "resource": existing}  # Already exists
    except NotFound:
        pass
    
    return {"created": True, "resource": await client.post(...)}
```

### 4. Update Status Appropriately

Always update CRD status to reflect current state:

```python
@kopf.on.create(...)
async def handler(spec, patch, **kwargs):
    try:
        result = await do_operation()
        patch.status["phase"] = "Ready"
        patch.status["lastSync"] = datetime.now().isoformat()
    except Exception as e:
        patch.status["phase"] = "Error"
        patch.status["error"] = str(e)
```

### 5. Use Kopf Events

Use `kopf.info()` and `kopf.warn()` to emit Kubernetes events:

```python
kopf.info(meta, reason="Created", message="Resource created successfully")
kopf.warn(meta, reason="Failed", message=f"Operation failed: {error}")
```

### 6. Feature Flags

Use environment variables to enable/disable features:

```python
def is_feature_enabled():
    return bool(os.environ.get("FEATURE_API_TOKEN"))

@kopf.on.create(...)
async def handler(spec, **kwargs):
    if is_feature_enabled():
        await do_external_operation()
    else:
        logger.info("Feature not enabled, skipping")
```

### 7. Graceful Error Handling

Don't let one failure break the entire handler:

```python
@kopf.on.create(...)
async def handler(spec, patch, **kwargs):
    errors = []
    
    # Operation 1
    try:
        await operation_1()
    except Exception as e:
        errors.append(f"op1: {e}")
    
    # Operation 2 (continues even if op1 failed)
    try:
        await operation_2()
    except Exception as e:
        errors.append(f"op2: {e}")
    
    if errors:
        patch.status["errors"] = errors
        kopf.warn(meta, reason="PartialFailure", message=f"Some operations failed")
```

---

## Troubleshooting

### CRD Not Appearing

1. Check model is imported in `models/__init__.py`
2. Check `@CRDRegistry.register` decorator is applied
3. Check operator logs for CRD generation errors
4. Verify with `kubectl get crd`

### Handler Not Triggering

1. Check handler module is imported in `handlers/__init__.py`
2. Check plugin's `register_handlers()` imports the handler
3. Verify decorator has correct group/version/kind (lowercase kind!)
4. Check operator logs for registration messages

### External Service Errors

1. Check environment variables are set correctly
2. Verify network connectivity from operator pod
3. Check service credentials are valid
4. Look for HTTP errors in logs

### Status Not Updating

1. Ensure RBAC includes `*/status` permission for your API group
2. Check `patch.status[...]` is used correctly
3. Verify no exceptions before status update

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `CRD not found` | Model not registered | Check `@CRDRegistry.register` |
| `Handler not called` | Not imported | Import in `handlers/__init__.py` |
| `403 Forbidden` | Missing RBAC | Add to `rbac.yaml` |
| `Connection refused` | Service not reachable | Check service URL and network |

---

## Summary

To add a new custom resource to the cr8tor operator:

1. **Define model** in `src/cr8tor/models/` with `@CRDRegistry.register`
2. **Create service** in `src/cr8tor/services/` for external integrations
3. **Create handler** in `src/cr8tor/handlers/` with Kopf decorators
4. **Create plugin** in `src/cr8tor/plugins/` inheriting from `PluginBase`
5. **Register plugin** in `src/cr8tor/plugins/registry.py`
6. **Update Helm** with values, env vars, and RBAC permissions
7. **Test** locally and with unit tests

The Gitea integration provides a complete reference implementation for external service integrations.
