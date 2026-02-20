# Architecture & Components

Cr8tor consists of three main components that work together to provide a complete TRE data orchestration solution.

## 1. CR8TOR CLI App

A Python-based command-line interface built with Typer that orchestrates the data access workflow.

**Key Features:**

- Project lifecycle management (initiate, create, validate, sign-off, stage, disclose, publish)
- GitHub integration for repository and team management
- BagIt and RO-Crate package building
- LinkML YAML file manipulation and validation
- Integration with Publisher microservices

**Installation:**

```bash
# Using uv (recommended)
uv pip install cr8tor

# Or clone and install locally
git clone https://github.com/lsc-sde-crates/cr8tor.git
cd cr8tor
uv pip install -e .
```

**Core Commands:**

| Command           | Purpose                                    | Phase      |
| ----------------- | ------------------------------------------ | ---------- |
| `initiate`        | Create new DAR project from template       | Initiation |
| `create`          | Initialize project with unique identifiers | Validation |
| `build`           | Build RO-Crate package                     | Validation |
| `validate`        | Validate connections and retrieve metadata | Validation |
| `sign-off`        | Record approval action                     | Approval   |
| `stage-transfer`  | Extract and stage data                     | Staging    |
| `disclosure`      | Record disclosure approval                 | Disclosure |
| `publish`         | Publish data to production                 | Publication |

## 2. CR8TOR Publisher Services

A microservices platform consisting of three FastAPI-based services deployed to Kubernetes.

### Approval Service

**Purpose**: API gateway coordinating data access operations

**Key Endpoints:**

- `POST /project/validate` - Validates connections and retrieves metadata
- `POST /project/package` - Initiates data packaging to staging
- `POST /project/publish` - Publishes data to production storage

**Responsibilities:**

- Request routing to Metadata and Publish services
- Centralized authentication and authorization
- Request validation and error handling
- Response formatting and logging

### Metadata Service

**Purpose**: Fetches dataset metadata without exposing actual data

**Key Endpoints:**

- `POST /metadata/project` - Retrieves and validates dataset metadata

**Supported Data Sources:**

- SQL Server
- MySQL
- PostgreSQL
- Databricks Unity Catalog

**Responsibilities:**

- Connection validation for source and destination systems
- Schema introspection and metadata extraction
- Table and column-level metadata retrieval
- Data type mapping and validation

### Publish Service

**Purpose**: Handles data extraction, staging, and publication

**Key Endpoints:**

- `POST /data-publish/validate` - Validates source/destination connections
- `POST /data-publish/package` - Packages data to staging storage
- `POST /data-publish/publish` - Publishes data to production storage

**Supported Data Sources:**

- SQL Server
- MySQL
- PostgreSQL
- Databricks Unity Catalog

**Destination Types:**

1. **PostgreSQL**: Loads data directly into PostgreSQL, creates OPAL projects with DataSHIELD permissions
2. **Filestore**: Packages data as CSV or DuckDB files in BagIt format, stores in Azure Storage

**Responsibilities:**

- Data extraction from source databases
- Format conversion (CSV, DuckDB)
- Two-stage publishing (staging → production)
- BagIt packaging with checksum calculation
- OPAL/DataSHIELD integration for PostgreSQL destinations

## 3. CR8TOR Operator

A Kubernetes operator that manages infrastructure provisioning based on deployment model definitions.

**Managed Custom Resources:**

- `users.identity.karectl.io` - User account management
- `groups.identity.karectl.io` - Group and role management
- `keycloakclients.identity.karectl.io` - Keycloak client configuration
- `projects.research.karectl.io` - Research project resources
- `vdiinstances.karectl.io` - Virtual Desktop Infrastructure instances

**Key Features:**

- Declarative infrastructure management via CRDs
- Integration with Keycloak for identity management
- Automated VDI provisioning for research workspaces
- Project-specific resource isolation
- Kubernetes-native resource lifecycle management

**Operator Pattern Benefits:**

- **Automation**: Automatically reconciles desired state from CR8TOR deployment models
- **Self-healing**: Detects and corrects configuration drift
- **Extensibility**: New resource types can be added via CRDs
- **Kubernetes-native**: Leverages existing K8s RBAC, networking, and storage
