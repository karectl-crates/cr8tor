# Cr8tor Metamodel

Cr8tor uses [LinkML](https://linkml.io/) (Linked Data Modeling Language) to define a structured, type-safe metamodel for research data projects and inherits from underlying data models (5-Safes RO-Crate (5SROC) Profile, Schema.org, SCIM, OpenAPIv3) for representing Cr8tor project governance, TRE data ingress and K8s resourcing needs.

Documentation for the Cr8tor metamodel is accessible [here](https://karectl-crates.github.io/cr8tor-metamodel/) which outlines the classes and linkages to underlying data schemas (i.e. schema.org).

## Overview

The Cr8tor metamodel is organized into three interconnected models, each represented as a YAML file in a Cr8tor project resources/ directory:

### 1. Governance Model (`cr8-governance.yaml`)

Defines project governance, user management, and 5SROC tracking.

**Key Classes:**

- **Project**: Core project information including name, description, reference
- **User**: User accounts with attributes like username, email, affiliation, group membership
- **Group**: Organizational groupings for role-based access control
- **Action**: Tracks operations performed on the project (CreateAction, AssessAction) with timestamps, status, agent, and results

**Example:**

```yaml
project:
  name: linkmlproj
  description: Example linkml cr8tor project for demonstration
  reference: CR8TOR-002
users:
- id: https://example.org/users/alice
  username: hardingm
  given_name: Mike
  family_name: Harding
  affiliation: Lancaster University
  email: m.harding@lancaster.ac.uk
  groups:
  - value: researchers
    display: Research Group
    type: Manual
  start_date: '2024-01-01T00:00:00Z'
  expiry_date: '2026-01-01T00:00:00Z'
```

### 2. Data Model (`cr8-ingress.yaml`)

Describes data ingress information including source systems, destinations (e.g. Opal database), and dataset schemas.

**Key Classes:**

- **Source**: Connection details for source data systems (PostgreSQL, MySQL, SQL Server, Databricks)
- **Destination**: Target environment for data publication
- **Dataset**: Logical grouping of tables with schema information
- **Table**: Individual table definitions with column schemas
- **Column**: Column-level metadata including name and datatype

**Example:**

```yaml
source:
  name: opal-resource-db
  type: postgresql
  url: datashield-postgres-cluster-rw.datashield.svc.cluster.local
  credentials:
    provider: AzureKeyVault
    password_key: opal-resource-db-password
    username_key: opal-resource-db-username
destination:
  type: postgresql
datasets:
- name: myXYZDataset
  schema_name: public
  tables:
  - name: xyz_source
    columns:
    - name: id
      datatype: UUID
    - name: value
      datatype: VARCHAR
```

### 3. Deployment Model (`cr8-deployment.yaml`)

Specifies TRE infrastructure resources to be provisioned.

**Key Classes:**

- **Environment**: Target TRE environment (e.g., dev-tre, prod-tre)
- **Resource**: Infrastructure components like JupyterHub, Keycloak, VDI instances
- **Jupyter**: Jupyter notebook environment configuration
- **Keycloak**: Identity and access management configuration

**Example:**

```yaml
environment:
  name: dev-tre

resources:
  - name: jupyterhub-main
    resource_type: Jupyter
    url: https://jupyter.example.org
    enabled: true
    auth: oidc

  - name: keycloak-main
    resource_type: Keycloak
    url: https://auth.example.org
    enabled: true
    realm: dev-tre
```

## Benefits of LinkML

Definition of Cr8tor's metamodel in LinkML provides a series of key benefits going forward:

- **Type Safety**: Pydantic models generated from LinkML schemas provide runtime validation
- **Extensibility**: Easy to extend with new attributes without breaking existing projects
- **Interoperability**: LinkML supports JSON-LD, RDF, and other linked data formats
- **Documentation**: Auto-generated documentation from schema definitions
- **Tooling**: Rich ecosystem for validation, conversion, and visualization
