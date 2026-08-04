# Gitea Integration — Completion Plan

Branch: `feature/ss-cr8tor-gitea-int`
Status: **implemented** — see "Notes for the PR description" below.

---

## Notes for the PR description

Carry these into the PR body; they are behaviour changes and known gaps that should be
visible to reviewers rather than left to be discovered.

### Behaviour changes

- **Gitea team membership is now reconciled from actual state, not from a spec diff.** The
  Group handler lists the team's real members and converges them to `Group.spec.members`.
  This means a user added to a project team **directly in Gitea**, who is not in
  `spec.members`, will be removed on the next reconcile. Reads that fail leave membership
  untouched rather than removing anyone.
- **The User handler now joins Gitea teams as well as pre-provisioning accounts.** Without
  this, a `Project -> Group -> User` apply order left users with a Gitea account but no team
  membership, because the Group handler had already run before the account existed.
  `Group.spec.members` remains the only source of truth for who belongs to what.
- **A project with no Gitea resource entry no longer gets an organisation.** Previously a
  missing `spec.gitea` block defaulted to enabled. Gitea config now lives on the `Gitea`
  entry in `spec.resources` and an absent entry means it was never requested.
- **Gitea network rules are only emitted when the integration is enabled**, and now support
  an external or ingress-fronted Gitea by FQDN rather than only an in-cluster service on
  port 3000.

### Deferred, deliberately not fixed in this pass

- `get_group_crd()` in `identity_handler.py` no longer has any callers. Left in place as a
  general-purpose helper rather than removed as unrelated churn.
- The `spec.get("storage")` fallbacks in `storage_manager.py` (`resolve_notebook_storage_config`,
  `resolve_vdi_storage_config`, `resolve_project_storage_config`) are now unreachable: a
  top-level `spec.storage` does not exist in the metamodel schema and `additionalProperties:
  false` would reject it. Harmless, but dead.

---

## Governing constraint

Per the PR reviewer:

> This will override everything that we have from the metamodel-generated CRD models.
> We don't create the models now in the cr8tor repo directly. It is being created by the
> metamodels automatically from the LinkML schemas (`../cr8tor-metamodel/src/cr8tor_metamodel`).
> You can add the new gitea blocks to the deployment model and the sync-metamodel.yaml
> should regenerate the correct models based on that.

`cr8tor-metamodel` is the single source of truth for CRD models. `cr8tor` consumes generated
Pydantic models and must not hand-write competing ones.

## Design decision (settled)

Gitea project config lives **on the `Gitea` Resource subclass**, following the `Keycloak`
precedent (which carries `realm` and `clients` on the subclass), *not* as a top-level
`ProjectSpec.gitea` block.

This matches what `cli/deploy.py:160-165` already emits (a `Gitea` entry inside
`spec.resources`). Consequently **the handler changes to read it, not the emitter**.

---

## ⚠️ Discrepancies between the agreed plan and the current code

Four items in the plan as stated do not hold against the code. Details and recommendations
below; each needs a decision before or during implementation.

### D1. `Group.name` does not exist — and the User→Gitea path is dead code

The plan says: *"the handler adapts to read `.name` off each group object."*

`governance_model.yaml:219-248` defines `Group` with exactly four attributes — `value`, `ref`,
`display`, `type` — all `required: false` and all annotated `mutability: readOnly`. There is
no `name`.

- `value` — "The unique identifier of the group, typically used as the group ID for
  referencing and access control" → this is the correct field for a CRD-name lookup.
- `display` — "A human-readable display name … used for UI and reporting" → not an identifier.

**Recommendation:** read `.get("value")`, with a guard, since every field is optional and a
`Group` object may legitimately carry no identifier at all.

**The larger problem:** `cli/deploy.py:341-350` constructs `User(...)` and **never sets
`groups`**. The comment at `deploy.py:356-357` is explicit:

> project binding is managed entirely via Group CRDs, not the User CRD.

So for every generated User CRD, `spec.groups` is empty. The Gitea team-assignment block in
`user_create_update` (`identity_handler.py:335-383`), which iterates `user_groups`, is
**unreachable in practice**. Adapting it to read `.value` would correct the field name but
leave the code just as dead.

**Recommendation:** treat `Group.spec.members` as the authoritative user↔team linkage (the
group handler at `identity_handler.py:512-534` already works this way) and reduce the
User-handler Gitea block to pre-provisioning only (step 3). This also makes step 4
(membership drift) the single reconciliation point rather than one of two competing ones.

### D2. `default_repo_permission` is missing from the proposed Gitea attributes

The plan lists `visibility` and `create_template_repo`. The handler also reads
`gitea_config.get("default_repo_permission", "read")` at `identity_handler.py:778` to set the
`members` team permission.

If it is not added to the schema it will be pruned from the CRD (`additionalProperties: false`),
and the members team will silently always be `read` — a quieter version of the exact bug this
work exists to fix.

**Recommendation:** add it. Included in the schema below.

### D3. `GiteaTeamConfig` multivalued vs. singular

The plan says *"multivalued/inlined_as_list, mirroring KeycloakClientConfig."*

The hand-written model it replaces is singular (`gitea: Optional[GiteaTeamConfig]`), and the
handler reads it as a single dict (`identity_handler.py:512`, `:575`). The current semantic is
*one team name per group, applied across each of that group's projects* — the handler already
loops over `group_projects` and creates the same team in each project's org.

Multivalued would mean N teams × M orgs, and requires the membership add/remove logic in step 4
to iterate a second dimension.

**Recommendation:** keep it **singular** (`inlined: true`, not `inlined_as_list`). The
Keycloak parallel is imperfect — a Keycloak deployment genuinely hosts many clients, whereas a
group maps to one logical team. Singular is also a smaller diff and matches the handler as
written. Schema below reflects the singular form; say the word and I'll switch it.

### D4. `source_id` for OIDC pre-provisioning is not configured anywhere

Step 3 requires pointing the created Gitea account at the Keycloak OIDC auth source via
`source_id`. That is a Gitea *instance-level* identifier (the row ID of the configured auth
source), and it is currently exposed nowhere — not in `services/gitea/client.py`, not as an env
var, not as a chart value.

`GiteaClient` also has no user-creation method; it exposes only generic `get`/`post`/`put`/
`delete`, so `POST /api/v1/admin/users` is straightforward to add.

**Recommendation:** add a `GITEA_OIDC_SOURCE_ID` env var plumbed from a new
`gitea.oidcSourceId` chart value, and skip pre-provisioning with a warning when it is unset
rather than creating local-password accounts that bypass SSO.

---

## Step 1 — Schema changes (`cr8tor-metamodel`)

All edits in `src/cr8tor_metamodel/schema/deployment_model.yaml`.

### 1a. Flesh out the bare `Gitea` class

Replace the current stub (`deployment_model.yaml:145-148`):

```yaml
  Gitea:
    is_a: Resource
    description: >-
      Gitea git repository resource for cr8tor project. The operator provisions a
      per-project organisation, teams and an optional template repository.
    attributes:
      visibility:
        range: GiteaVisibility
        required: false
        ifabsent: "string(private)"
        description: Organisation visibility.
      create_template_repo:
        range: boolean
        required: false
        ifabsent: "true"
        description: Create a template repository when the organisation is created.
      default_repo_permission:
        range: GiteaPermission
        required: false
        ifabsent: "string(read)"
        description: Default repository permission granted to organisation members.
```

`name`, `url` and `enabled` are inherited from `Resource`. **`enabled` is what resolves the
`Gitea(enabled=False)` mismatch** — once the handler reads the resource entry, the emitter's
`enabled=False` is respected with no further change.

### 1b. Add `GiteaTeamConfig` and reference it from `GroupSpec`

```yaml
  GiteaTeamConfig:
    description: >-
      Gitea team configuration for a group. The operator maintains a team of this name in
      each organisation belonging to the group's projects.
    attributes:
      team_name:
        range: string
        required: false
        description: Team name in the Gitea organisation. Defaults to the group name.
      permission:
        range: GiteaPermission
        required: false
        ifabsent: "string(write)"
        description: Team permission level.
```

Added to `GroupSpec` (singular per D3):

```yaml
      gitea:
        range: GiteaTeamConfig
        required: false
        inlined: true
        description: Gitea team configuration for this group.
```

### 1c. Add `resource_quota` to `ProjectSpec`

Genuinely missing (confirmed in Stage 1 — not an override artifact), while
`identity_handler.py:656` reads it.

```yaml
  ResourceQuotaConfig:
    description: Aggregate resource quota for the project namespace.
    attributes:
      requests_cpu:
        range: string
        required: false
        description: Total CPU requests allowed.
      requests_memory:
        range: string
        required: false
        description: Total memory requests allowed.
      limits_cpu:
        range: string
        required: false
        description: Total CPU limits allowed.
      limits_memory:
        range: string
        required: false
        description: Total memory limits allowed.
      pods:
        range: string
        required: false
        description: Maximum number of pods.
      services:
        range: string
        required: false
        description: Maximum number of services.
      persistentvolumeclaims:
        range: string
        required: false
        description: Maximum number of PVCs.
      requests_storage:
        range: string
        required: false
        description: Total storage requests allowed.
```

Referenced from `ProjectSpec`:

```yaml
      resource_quota:
        range: ResourceQuotaConfig
        required: false
        inlined: true
        description: Aggregate resource quota for the project namespace.
```

> Note: the hand-written version carried non-null defaults (`requests_cpu: "4"`,
> `limits_memory: "16Gi"`, …). Those are **deliberately not** reproduced as `ifabsent` — the
> handler treats a missing quota as "no quota", and baking in defaults would silently start
> applying quotas to projects that never requested one. Flagging as a judgment call.

### 1d. Supporting enums

```yaml
  GiteaVisibility:
    description: Gitea organisation visibility levels.
    permissible_values:
      private:
      limited:
      public:

  GiteaPermission:
    description: Gitea team / repository permission levels.
    permissible_values:
      read:
      write:
      admin:
```

### 1e. Explicitly out of scope

`User.groups` stays `range: Group` (inlined objects) — the deliberate post-`fb05bdb` shape.
Not reverted. See D1 for how the handler adapts.

`storage` and `scheduling` are **not** added to `ProjectSpec`. Stage 1 confirmed they already
exist at resource level (`Jupyter.storage`, `VDI.storage`, `VDI.scheduling`) and that
`storage_manager.py:357` already prefers that placement. `current-issue.md`'s claim that they
are missing was an artifact of the hand-written override.

## Step 2 — Regenerate

```bash
cd ../cr8tor-metamodel
uv run gen-project -d src/cr8tor_metamodel/datamodel -I python \
  src/cr8tor_metamodel/schema/cr8tor_metamodel.yaml
uv run gen-pydantic src/cr8tor_metamodel/schema/cr8tor_metamodel.yaml \
  > src/cr8tor_metamodel/datamodel/cr8tor_metamodel_pydantic.py
```

(Equivalent to `just gen-python`; `just` is not installed locally — `uv tool install rust-just`
if the recipe form is preferred.)

Then, for local iteration in `cr8tor`:

```bash
cd ../cr8tor && uv pip install -e ../cr8tor-metamodel
```

per the existing hint at `pyproject.toml:59-61`. This is **temporary** — `pyproject.toml` pins
`cr8tor-metamodel @ git+…@main` and `uv.lock` pins rev `7e98ba0`. Final state requires the
metamodel change merged to `main`, `auto-generate.yaml` committing regenerated models, and
`sync-metamodel.yml` re-resolving the lock.

**Verify before proceeding:** confirm the regenerated `ProjectSpec` carries `description`,
`resources`, `limit_range`, `approved_egress_rules`, `resource_quota`; that `Gitea` carries
`visibility`, `create_template_repo`, `default_repo_permission`, `enabled`; and that
`GroupSpec` carries `gitea`.

## Step 3 — Remove the override

1. Delete `src/cr8tor/models/identity.py`, restoring the `fb05bdb` state this branch regressed.
2. Confirm `models/registry_config.py` alone registers all five CRDs. It already imports
   `User`, `GroupSpec`, `KeycloakClientConfig`, `ProjectSpec`, `VDI` from the generated module
   and registers each — no edit expected, but verify by re-running the registry dump used in
   Stage 1 and checking every entry resolves to `cr8tor_metamodel.datamodel…`.
3. Re-generate CRD YAML and confirm `spec.resources`, `spec.approved_egress_rules` and
   `spec.resource_quota` all survive a round trip.

This also restores `approved_egress_rules`, which the override was silently dropping — breaking
the per-FQDN multi-port egress feature merged in #54, three commits before this branch's tip.

## Step 4 — Update consumers

`identity_handler.py`:

- Read Gitea project config via `_get_resource_entry(spec, "Gitea")` (promote the helper out of
  `storage_manager.py` to a shared location, or import it — it is currently private there).
  Replace `spec.get("gitea", {})` at `:752`. Honour the entry's `enabled` field, ANDed with the
  operator-level `is_gitea_enabled()`.
- Read group Gitea config via the new `GroupSpec.gitea` block (shape unchanged if D3 resolves
  to singular).
- Per D1: reduce the User-handler Gitea block to pre-provisioning; drop the unreachable
  `user_groups` iteration.

`services/gitea/manager.py`: unchanged signatures; callers pass values sourced from the
regenerated models.

`cli/deploy.py`: no change to the resources list. Populate the new `Gitea` fields if the
generated defaults are not the desired emission.

## Step 5 — Gitea user pre-provisioning

Add `create_user` to `services/gitea/client.py` / `manager.py` wrapping
`POST /api/v1/admin/users` with `source_id` set to the Keycloak OIDC auth source, so the
account exists before first login and team assignment no longer races SSO.

Call it in `user_create_update` at the same point `sync_keycloak_user()` runs. Requires the
`GITEA_OIDC_SOURCE_ID` config knob from D4; skip with a warning when unset. Set
`must_change_password: false` (OIDC-backed accounts have no local password to rotate).

Idempotency: treat HTTP 422 "user already exists" as success.

## Step 6 — Membership drift

In `group_create_update`, diff old vs. new `spec.members` and both add **and** remove against
the corresponding Gitea team. Kopf supplies the `diff` argument for this (the same mechanism
already used for password-reset detection at `identity_handler.py:285-291`).

Currently only additions are handled (`:534`), so removing a user from `Group.spec.members`
leaves their Gitea access intact.

## Step 7 — Async / blocking

Wrap sync calls in `asyncio.to_thread()` inside each `async def` handler. Confirmed blocking
callers:

| Handler | Blocking calls |
|---|---|
| `user_create_update` | `ensure_realm_exists`, `sync_keycloak_user`, `get_user_projects`, `ensure_user_notebook_pvc` |
| `user_delete` | `delete_keycloak_user`, `cleanup_user_notebook_pvcs` |
| `group_create_update` / `group_delete` | `get_group_crd`, `get_group_members`, Keycloak group sync |
| `project_create_update` | `ensure_proj_namespace`, `ensure_resource_quota`, `ensure_limit_range`, `ensure_jupyter_rolebind`, `create_project_network_policy`, `resolve_project_storage_config`, `ensure_project_pvc` |
| `project_delete` | namespace deletion |

The Gitea manager functions are already `async` over `httpx.AsyncClient` and must **not** be
wrapped.

## Step 8 — Cleanup

- Remove the dangling `project_sync` registration: `plugins/registry.py:59` references
  `cr8tor.plugins.project_sync`, which does not exist. Delete that entry, delete
  `handlers/project_sync_handler.py`, and drop it from `handlers/__init__.py:6,8`. The handler
  registers a **cluster-wide** ConfigMap watch whose plugin can never resolve.
- Declare `httpx` in `pyproject.toml` dependencies (used in `services/gitea/client.py`,
  `services/gitea/manager.py`, and pre-existing `airlock/api_client.py`).
- Make the Gitea network policy port configurable in
  `services/network_policy_manager.py` — currently hardcoded to `3000`, blocking
  ingress-fronted Gitea on `443`. Source from chart config alongside `GITEA_URL`.
- Bound the init container's secret-wait loop in `charts/cr8tor-operator/templates/deployment.yaml`
  with a timeout and non-zero exit; it currently loops `until … sleep 5` forever against a
  secret marked optional.
- The `Gitea(enabled=False)` mismatch needs no separate fix — resolved by steps 1a + 4.

## Step 9 — Tests

`cr8tor` has **no test suite at all** (only `scripts/test-system.py`). This pass adds
`tests/` with pytest, covering at minimum:

1. **CRD field preservation** — a generated Project CRD round-trips `spec.resources`,
   `spec.approved_egress_rules`, `spec.resource_quota` without pruning. This is the regression
   test for the bug that motivated the review.
2. **Storage resolution** — notebook and VDI storage resolve from resource-level config rather
   than falling back to Helm defaults.
3. **Project → org/team/repo creation**, with the Gitea client mocked.
4. **Pre-provisioning** — a Gitea account is created without a prior SSO login.
5. **Membership reconciliation** — both addition and removal.
6. **Disabled Gitea** — `Gitea(enabled=False)` provisions nothing.

`cr8tor-metamodel` has an existing suite (`just test` → `_test-schema`, `_test-python`,
`_test-examples`); schema changes must keep it green.

## Order of operations

1. Schema edits in `cr8tor-metamodel` (step 1)
2. Regenerate + verify generated models (step 2)
3. `uv pip install -e ../cr8tor-metamodel` in `cr8tor`
4. Delete `models/identity.py`, verify registry resolves to generated models (step 3)
5. Update consumers — handlers, deploy.py (step 4)
6. Feature fixes — pre-provisioning, membership drift (steps 5–6)
7. Async unblocking (step 7)
8. Cleanup (step 8)
9. Tests, both repos (step 9)
10. Push metamodel to `main`, let `auto-generate.yaml` + `sync-metamodel.yml` re-resolve the
    lock, drop the editable install

Steps 4–5 are the risky pair: between deleting the override and updating the handlers, the
operator will not run. Best done as one commit.

## Deferred / not in scope

Per your Stage 2 instruction, these `current-issue.md` items are noted but not actioned:

- Deployment examples and operator-chart upgrade documentation.
- `identity_handler.py` merge-conflict resolution — **already resolved**; Stage 1 confirmed
  `diff` and the first-login password-reset path survive at `identity_handler.py:274,285-291`.
