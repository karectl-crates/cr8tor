## Gitea integration is not production-ready and introduces a silent CRD regression

The `feature/ss-cr8tor-gitea-int` branch adds genuine Gitea organisation, repository, team and membership management, but it cannot safely be merged in its current state.

### Primary release blocker

`src/cr8tor/models/identity.py` re-registers the `User`, `Group`, `KeycloakClient` and `Project` CRDs using the same registry keys as the generated models in `registry_config.py`. Because the handwritten models are imported later, they silently replace the `cr8tor-metamodel` models as the active CRD schema source.

The replacement `ProjectSpec` defines `apps` but does not define `resources`. However, `cr8tor create-deployment` still writes application configuration to:

```yaml
spec:
  resources:
```

When this manifest is applied, Kubernetes silently removes `spec.resources` because it is absent from the generated Project CRD schema. The deployment passes validation, but the operator subsequently cannot find the Jupyter or VDI resource entries. As a result, notebook and VDI storage configuration silently falls back to Helm defaults instead of using the project’s requested settings.

This means merging the Gitea branch can break existing non-Gitea functionality without producing a validation or deployment error.

### Required fix

There must be one authoritative model layer:

1. Add `gitea`, `resource_quota`, `storage`, `scheduling` and the other required fields to `cr8tor-metamodel`, regenerate the models and remove the duplicate handwritten CRD registrations; or
2. Formally replace the metamodel-backed models, remove `registry_config.py`, and update all producers and consumers—including `deploy.py`, storage resolution and examples—to use `apps` consistently.

The first option is preferable because the repository already treats `cr8tor-metamodel` as the schema source of truth.

### Other merge blockers

* The Gitea handlers were changed to `async def` but still make synchronous Keycloak and Kubernetes calls. These calls block Kopf’s event loop and can stall the entire operator.
* Removed `project_sync` code is still imported and registered, creating startup warnings and a cluster-wide watch that cannot resolve its plugin.
* The `identity_handler.py` merge conflict must preserve the existing `diff` argument and first-login password-reset behaviour.
* Users are not provisioned in Gitea. Team assignment only works after the user already exists, normally following their first OIDC login.
* Removing a user from `Group.spec.members` does not remove them from the corresponding Gitea team, creating access-control drift.
* `deploy.py` emits `Gitea(enabled=False)`, while the operator defaults missing `spec.gitea.enabled` to enabled, so a supposedly disabled project may still receive a Gitea organisation.
* Network policy only supports an in-cluster Gitea service on port `3000`; external or ingress-fronted Gitea endpoints on port `443` remain blocked.
* `httpx` is used but is not declared as a direct dependency.
* The Gitea init container can wait indefinitely for a secret that is simultaneously marked optional.
* There are no Gitea integration tests, deployment examples or operator-chart documentation.

### Acceptance criteria

The branch is ready to merge only when:

* Applying a generated Project CRD preserves every field emitted by `create-deployment`, particularly `spec.resources`.
* Notebook and VDI storage resolution is covered by a regression test.
* Async handlers no longer execute blocking calls on the event loop.
* Existing password-reset behaviour survives the merge.
* Gitea membership changes reconcile both additions and removals.
* Disabled Gitea configuration is respected consistently.
* Supported Gitea network locations and ports are configurable.
* Gitea dependencies, tests, examples and upgrade documentation are included.

Until these issues are resolved, the branch should be treated as functional Gitea groundwork rather than a production-ready integration.
