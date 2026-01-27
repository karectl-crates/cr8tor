# cr8tor-operator Helm Chart

Kubernetes operator for cr8tor to manages Users, Groups, Projects, VDI instances, and Keycloak integration for the karectl platform.

## Prerequisites

- The following resources must exist in the target namespace before installation:

| Resource | Kind | Description |
|----------|------|-------------|
| `keycloak-admin-credentials` | Secret | Must contain `username` and `password` keys for Keycloak admin access |
| `karectl-realm-config` | ConfigMap | Must contain `realm-name`, `keycloak-url`, and `keycloak-verify-tls` keys |

## Installation

### From OCI Registry

```bash
helm install cr8tor-operator oci://ghcr.io/karectl-crates/charts/cr8tor-operator \
  --namespace cr8tor \
  --create-namespace \
  --version 0.0.1
```

### From Source

```bash
git clone https://github.com/karectl-crates/cr8tor.git
cd cr8tor
helm install cr8tor-operator charts/cr8tor-operator \
  --namespace cr8tor \
  --create-namespace
```

## Configuration

### Key Values

| Parameter | Description | Default |
|-----------|-------------|---------|
| `image.registry` | Container image registry | `ghcr.io` |
| `image.repository` | Container image repository | `karectl-crates/cr8tor-operator` |
| `image.tag` | Image tag (defaults to `appVersion`) | `""` |
| `image.pullPolicy` | Image pull policy | `IfNotPresent` |
| `replicaCount` | Number of operator replicas | `1` |
| `config.logLevel` | Operator log level | `INFO` |
| `config.workerLimit` | Concurrent worker limit | `5` |
| `config.postingEnabled` | Enable posting | `false` |
| `config.serverTimeout` | Server timeout in seconds | `60` |
| `config.manageCrds` | Operator manages CRDs | `true` |
| `config.generateCrdFiles` | Generate CRD files | `false` |
| `keycloak.adminSecretName` | Secret name for Keycloak admin credentials | `keycloak-admin-credentials` |
| `keycloak.realmConfigMapName` | ConfigMap name for Keycloak realm config | `karectl-realm-config` |
| `resources.requests.cpu` | CPU request | `100m` |
| `resources.requests.memory` | Memory request | `128Mi` |
| `resources.limits.cpu` | CPU limit | `500m` |
| `resources.limits.memory` | Memory limit | `512Mi` |
| `vdiTemplates.enabled` | Deploy VDI pod templates ConfigMap | `true` |
| `serviceAccount.create` | Create a ServiceAccount | `true` |
| `rbac.create` | Create RBAC resources | `true` |

### Example: Development Environment

```yaml
image:
  tag: "develop"
  pullPolicy: Always

config:
  logLevel: "DEBUG"

keycloak:
  adminSecretName: "keycloak-admin-credentials"
  realmConfigMapName: "karectl-realm-config"
```

### Example: Production Environment

```yaml
image:
  tag: "v0.0.1"
  pullPolicy: IfNotPresent

config:
  logLevel: "INFO"

keycloak:
  adminSecretName: "keycloak-admin-credentials"
  realmConfigMapName: "karectl-realm-config"
```

## Managed CRDs

The operator manages the following Custom Resource Definitions:

- `users.identity.karectl.io`
- `groups.identity.karectl.io`
- `keycloakclients.identity.karectl.io`
- `projects.research.karectl.io`
- `vdiinstances.karectl.io`

## Uninstalling

```bash
helm uninstall cr8tor-operator --namespace cr8tor
```

Note: CRDs created by the operator are not removed on uninstall. Remove them manually if needed:

```bash
kubectl delete crd users.identity.karectl.io groups.identity.karectl.io \
  keycloakclients.identity.karectl.io projects.research.karectl.io \
  vdiinstances.karectl.io
```
