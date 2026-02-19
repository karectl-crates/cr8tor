import os
import re
import typer
import yaml
import jsonschema
from pathlib import Path
from typing import Annotated, Optional
from datetime import datetime
from cr8tor.utils import log


def _sanitise_label(value: str) -> str:
    """ Sanitise a string to be a valid k8s label value.
    """
    value = re.sub(r'https?://', '', value)
    value = re.sub(r'[^A-Za-z0-9._-]', '-', value)
    value = value.strip('-_.')
    return value[:63] or "unknown"

import cr8tor.airlock.linkml_ops as linkml_ops
import cr8tor.airlock.schema as schemas

# LinkML metamodels
from cr8tor_metamodel.datamodel.cr8tor_metamodel_pydantic import (
    Governance,
    GroupSpec,
    User,
    ProjectSpec,
    Jupyter,
    Keycloak,
    RStudio,
    Gitea,
    ProfileConfig,
    KubespawnerOverride,
    EnvironmentVariable,
)

app = typer.Typer()


@app.command(name="create-deployment")
def create_deployment(
    resources_dir: Annotated[
        Path,
        typer.Option(
            default="-i", help="Directory containing resources to include in deployment."
        ),
    ] = "./resources",
    output_dir: Annotated[
        Path,
        typer.Option(
            default="-o", help="Output directory for generated CRD YAML files."
        ),
    ] = "./generated-crds",
    crd_schema_dir: Annotated[
        Path,
        typer.Option(
            default="-s", help="Directory containing CRD schema definitions."
        ),
    ] = "./crds/generated",
    argocd_dir: Annotated[
        Optional[Path],
        typer.Option(
            help="Output directory for argocd Application YAML."
        ),
    ] = None,
    repo_url: Annotated[
        Optional[str],
        typer.Option(
            help="Git repo URL for argocd source (for --argocd-dir)."
        ),
    ] = None,
    source_path: Annotated[
        Optional[str],
        typer.Option(
            help="Path within the git repo to the CRDs directory (for --argocd-dir)."
        ),
    ] = None,
):
    """
    Create Kubernetes deployment CRDs from project resources.

    This command performs the following:
    - Reads project metadata from resources/governance/project.toml
    - Creates ProjectSpec Pydantic model from the data
    - Validates the generated CRD against the Project CRD schema
    - Writes the validated CRD YAML to the generated-crds directory

    Args:
        resources_dir (Path): Directory containing resources. Defaults to "./resources".
        output_dir (Path): Output directory for generated CRDs. Defaults to "./generated-crds".
        crd_schema_dir (Path): Directory containing CRD schemas. Defaults to "./crds/generated".

    Example usage:
        cr8tor create-deployment -i ./resources -o ./generated-crds
    """

    # Ensure resources directory exists
    if not resources_dir.exists():
        log.info(f"✗ Resources directory not found: {resources_dir}", err=True)
        raise typer.Exit(1)

    # Load governance YAML
    governance_path = resources_dir.joinpath("governance", "cr8-governance.yaml")
    if not governance_path.exists():
        log.info(
            f"✗ Governance file not found: {governance_path}", err=True
        )
        raise typer.Exit(1)

    log.info(f"Reading project metadata from {governance_path}")

    # Read project data using linkml_ops
    try:
        governance = linkml_ops.load_yaml_as_pydantic(governance_path, Governance)
        project_props = governance.project
    except Exception as e:
        log.info(f"✗ Failed to read project metadata: {e}", err=True)
        raise typer.Exit(1)

    log.info(
        f"✓ Loaded project: {project_props.name} (ID: {project_props.id or 'N/A'})"
    )

    # Create ProjectSpec Pydantic model
    try:
        project_name = (project_props.reference or project_props.id or "unnamed-project").lower()

        # Build resources list for each resource type carries its own config
        project_resources = [
            Jupyter(
                name="jupyterhub",
                resource_type="Jupyter",
                url=f"https://jupyter.{project_name}.example.com",
                enabled=True,
                auth="oidc",
                profiles=[
                    ProfileConfig(
                        display_name=f"{project_name.replace('-', ' ').title()} Workspace 1",
                        slug=f"{project_name}-ws1",
                        description="A TRE workspace for federated analysis with Python",
                        kubespawner_override=KubespawnerOverride(
                            image="ghcr.io/karectl/marimo-notebook-workspace:latest",
                            env=[
                                EnvironmentVariable(name="PROJECT_NAME", value=project_name),
                                EnvironmentVariable(name="WORKSPACE", value=f"/{project_name}/ws1"),
                            ],
                        ),
                    ),
                    ProfileConfig(
                        display_name="R Statistical Computing",
                        slug="r-stats",
                        description="R environment for statistical analysis",
                        kubespawner_override=KubespawnerOverride(
                            image="rocker/tidyverse:latest",
                            env=[
                                EnvironmentVariable(name="DISABLE_AUTH", value="true"),
                            ],
                        ),
                    ),
                ],
            ),
            Keycloak(
                name="keycloak",
                resource_type="Keycloak",
                url=f"https://auth.{project_name}.example.com",
                enabled=True,
                realm=project_name,
            ),
            RStudio(
                name="rstudio",
                resource_type="RStudio",
                url=f"https://rstudio.{project_name}.example.com",
                enabled=True,
            ),
            Gitea(
                name="gitea",
                resource_type="Gitea",
                url=f"https://gitea.{project_name}.example.com",
                enabled=True,
            ),
        ]

        project_spec = ProjectSpec(
            description=project_props.name or "CR8TOR Project",
            resources=project_resources,
        )

        log.info(
            f"Created ProjectSpec with {len(project_spec.resources)} resources"
        )

    except Exception as e:
        log.info(f"Failed to create ProjectSpec: {e}", err=True)
        raise typer.Exit(1)

    # Create full Project CRD
    # Serialize resources individually to preserve subclass-specific fields
    project_name = (project_props.reference or project_props.id or "unnamed-project").lower()
    spec_dict = {
        "description": project_spec.description,
        "resources": [
            r.model_dump(exclude_none=True) for r in project_spec.resources
        ],
    }
    project_crd = {
        "apiVersion": "research.karectl.io/v1alpha1",
        "kind": "Project",
        "metadata": {
            "name": project_name,
            "labels": {
                "cr8tor.io/project-id": _sanitise_label(project_props.id or "unknown"),
                "cr8tor.io/created-at": datetime.now().strftime("%Y%m%d"),
            },
        },
        "spec": spec_dict,
    }

    # Validate against CRD schema
    crd_schema_file = crd_schema_dir.joinpath("projects.research.karectl.io.yaml")
    if not crd_schema_file.exists():
        log.info(
            f"⚠ CRD schema file not found: {crd_schema_file}, skipping validation"
        )
    else:
        try:
            # Load CRD schema
            with open(crd_schema_file) as f:
                crd_definition = yaml.safe_load(f)

            # Extract OpenAPI schema
            openapi_schema = crd_definition["spec"]["versions"][0]["schema"][
                "openAPIV3Schema"
            ]

            # Validate the CRD instance
            jsonschema.validate(instance=project_crd, schema=openapi_schema)
            log.info(f"✓ Project CRD validation passed")

        except jsonschema.ValidationError as e:
            log.info(f"✗ CRD validation failed: {e.message}", err=True)
            log.info(f"  Path: {' -> '.join(str(p) for p in e.path)}", err=True)
            raise typer.Exit(1)
        except Exception as e:
            log.info(f"✗ Validation error: {e}", err=True)
            raise typer.Exit(1)

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write CRD to file
    output_file = output_dir.joinpath(f"project-{project_name}.yaml")
    try:
        with open(output_file, "w") as f:
            yaml.dump(project_crd, f, default_flow_style=False, sort_keys=False)

        log.info(f"✓ Project CRD written to {output_file}")

    except Exception as e:
        log.info(f"✗ Failed to write CRD file: {e}", err=True)
        raise typer.Exit(1)

    log.info(f"\n✓ Deployment creation complete")
    log.info(f"  Project: {project_name}")
    log.info(f"  Output: {output_file}")

    ###############################################################################
    # Create User CRD from requesting_agent
    ###############################################################################

    # Read requesting_agent data from governance
    if not governance.users:
        log.info(f"⚠ No requesting_agent (users) in governance metadata")
        log.info(f"  Skipping User CRD generation")
        return

    # Use the first user as the requesting agent
    requesting_agent = governance.users[0]
    log.info(f"\n✓ Loaded requesting agent: {requesting_agent.username}")

    # Create UserSpec from requesting_agent
    try:
        user_spec = User(
            id=requesting_agent.id,
            username=requesting_agent.username,
            email=requesting_agent.email,
            enabled=True,
            given_name=requesting_agent.given_name,
            family_name=requesting_agent.family_name,
            affiliation=requesting_agent.affiliation,
            groups=requesting_agent.groups if requesting_agent.groups else None,
        )

        log.info(f"✓ Created UserSpec for {user_spec.username}")

    except Exception as e:
        log.info(f"✗ Failed to create UserSpec: {e}", err=True)
        raise typer.Exit(1)

    # Create full User CRD
    user_crd = {
        "apiVersion": "identity.karectl.io/v1alpha1",
        "kind": "User",
        "metadata": {
            "name": requesting_agent.username,
            "labels": {
                "cr8tor.io/project-id": _sanitise_label(project_props.id or "unknown"),
                "cr8tor.io/created-at": datetime.now().strftime("%Y%m%d"),
            },
        },
        "spec": user_spec.model_dump(exclude_none=True),
    }

    # Validate against User CRD schema
    user_crd_schema_file = crd_schema_dir.joinpath("users.identity.karectl.io.yaml")
    if not user_crd_schema_file.exists():
        log.info(
            f"⚠ User CRD schema file not found: {user_crd_schema_file}, skipping validation"
        )
    else:
        try:
            # Load CRD schema
            with open(user_crd_schema_file) as f:
                user_crd_definition = yaml.safe_load(f)

            # Extract OpenAPI schema
            user_openapi_schema = user_crd_definition["spec"]["versions"][0]["schema"][
                "openAPIV3Schema"
            ]

            # Validate the CRD instance
            jsonschema.validate(instance=user_crd, schema=user_openapi_schema)
            log.info(f"✓ User CRD validation passed")

        except jsonschema.ValidationError as e:
            log.info(f"✗ User CRD validation failed: {e.message}", err=True)
            log.info(f"  Path: {' -> '.join(str(p) for p in e.path)}", err=True)
            raise typer.Exit(1)
        except Exception as e:
            log.info(f"✗ User validation error: {e}", err=True)
            raise typer.Exit(1)

    # Write User CRD to file
    user_output_file = output_dir.joinpath(f"user-{requesting_agent.username}.yaml")
    try:
        with open(user_output_file, "w") as f:
            yaml.dump(user_crd, f, default_flow_style=False, sort_keys=False)

        log.info(f"✓ User CRD written to {user_output_file}")

    except Exception as e:
        log.info(f"✗ Failed to write User CRD file: {e}", err=True)
        raise typer.Exit(1)

    ###############################################################################
    # Create Group CRDs for project access control
    ###############################################################################

    admin_name = f"{project_name}-admin"
    analyst_name = f"{project_name}-analyst"

    group_definitions = [
        (project_name, GroupSpec(
            description=f"Main group for {project_name}",
            members=[requesting_agent.username],
            projects=[project_name],
            subgroups=[admin_name, analyst_name],
        )),
        (admin_name, GroupSpec(
            description=f"Admin subgroup for {project_name}",
            members=[],
            projects=[project_name],
            subgroups=[],
        )),
        (analyst_name, GroupSpec(
            description=f"Analyst subgroup for {project_name}",
            members=[requesting_agent.username],
            projects=[project_name],
            subgroups=[],
        )),
    ]

    group_output_files = []
    for group_name, group_spec in group_definitions:
        group_crd = {
            "apiVersion": "identity.karectl.io/v1alpha1",
            "kind": "Group",
            "metadata": {
                "name": group_name,
                "labels": {
                    "cr8tor.io/project-id": _sanitise_label(project_props.id or "unknown"),
                    "cr8tor.io/created-at": datetime.now().strftime("%Y%m%d"),
                },
            },
            "spec": group_spec.model_dump(exclude_none=True),
        }

        # Validate against Group CRD schema
        group_crd_schema_file = crd_schema_dir.joinpath("groups.identity.karectl.io.yaml")
        if not group_crd_schema_file.exists():
            log.info(
                f"Group CRD schema file not found: {group_crd_schema_file}, skipping validation"
            )
        else:
            try:
                with open(group_crd_schema_file) as f:
                    group_crd_definition = yaml.safe_load(f)

                group_openapi_schema = group_crd_definition["spec"]["versions"][0]["schema"][
                    "openAPIV3Schema"
                ]

                jsonschema.validate(instance=group_crd, schema=group_openapi_schema)
                log.info(f"Group CRD validation passed for {group_name}")

            except jsonschema.ValidationError as e:
                log.info(f"Group CRD validation failed for {group_name}: {e.message}", err=True)
                log.info(f"  Path: {' -> '.join(str(p) for p in e.path)}", err=True)
                raise typer.Exit(1)
            except Exception as e:
                log.info(f"Group validation error for {group_name}: {e}", err=True)
                raise typer.Exit(1)

        # Write file for each group
        group_output_file = output_dir.joinpath(f"group-{group_name}.yaml")
        try:
            with open(group_output_file, "w") as f:
                yaml.dump(group_crd, f, default_flow_style=False, sort_keys=False)

            log.info(f"Group CRD written to {group_output_file}")
            group_output_files.append(group_output_file)

        except Exception as e:
            log.info(f"Failed to write Group CRD file: {e}", err=True)
            raise typer.Exit(1)

    log.info(f"\n✓ All deployment CRDs created successfully")
    log.info(f"  - Project CRD: {output_file}")
    log.info(f"  - User CRD: {user_output_file}")
    for gf in group_output_files:
        log.info(f"  - Group CRD: {gf}")

    ###############################################################################
    # Generate ArgoCD ApplicationSet YAML (app-per-project)
    ###############################################################################

    if argocd_dir is not None:
        if not repo_url:
            log.info(f"--repo-url is required when using --argocd-dir", err=True)
            raise typer.Exit(1)
        if not source_path:
            log.info(f"--source-path is required when using --argocd-dir", err=True)
            raise typer.Exit(1)

        argocd_app = {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "ApplicationSet",
            "metadata": {
                "name": f"cr8tor-{project_name}",
                "namespace": "argocd",
                "labels": {
                    "cr8tor.io/project-id": _sanitise_label(project_props.id or "unknown"),
                    "cr8tor.io/managed-by": "cr8tor",
                    "app.kubernetes.io/part-of": "cr8tor-projects",
                },
                "annotations": {
                    "cr8tor.io/dar-reference": project_props.reference or project_props.id or "unnamed-project",
                    "cr8tor.io/created-at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                },
            },
            "spec": {
                "goTemplate": True,
                "goTemplateOptions": ["missingkey=error"],
                "generators": [
                    {
                        "clusters": {
                            "selector": {
                                "matchExpressions": [
                                    {
                                        "key": "environment",
                                        "operator": "In",
                                        "values": ["dev", "stg", "prd"],
                                    },
                                    {
                                        "key": f"skip-cr8tor-{project_name}",
                                        "operator": "NotIn",
                                        "values": ["true"],
                                    },
                                ],
                            },
                        },
                    },
                ],
                "template": {
                    "metadata": {
                        "name": f"cr8tor-{project_name}-{{{{.nameNormalized}}}}",
                        "namespace": "argocd",
                        "labels": {
                            "cr8tor.io/project-id": _sanitise_label(project_props.id or "unknown"),
                            "cr8tor.io/managed-by": "cr8tor",
                            "app.kubernetes.io/part-of": "cr8tor-projects",
                        },
                    },
                    "spec": {
                        "project": "default",
                        "source": {
                            "repoURL": repo_url,
                            "targetRevision": "main",
                            "path": source_path,
                        },
                        "destination": {
                            "server": "{{.server}}",
                            "namespace": "keycloak",
                        },
                        "syncPolicy": {
                            "automated": {
                                "prune": True,
                                "selfHeal": True,
                            },
                            "syncOptions": [
                                "CreateNamespace=false",
                                "ApplyOutOfSyncOnly=true",
                            ],
                        },
                    },
                },
            },
        }

        argocd_dir = Path(argocd_dir)
        argocd_dir.mkdir(parents=True, exist_ok=True)
        argocd_output_file = argocd_dir.joinpath(f"{project_name}.yaml")
        try:
            with open(argocd_output_file, "w") as f:
                yaml.dump(argocd_app, f, default_flow_style=False, sort_keys=False)
            log.info(f"ArgoCD ApplicationSet written to {argocd_output_file}")

        except Exception as e:
            log.info(f"Failed to write ArgoCD ApplicationSet file: {e}", err=True)
            raise typer.Exit(1)

        # Register in kustomization.yaml
        kustomization_file = argocd_dir.joinpath("kustomization.yaml")
        resource_entry = f"{project_name}.yaml"
        try:
            if kustomization_file.exists():
                with open(kustomization_file) as f:
                    kustomization = yaml.safe_load(f) or {}
            else:
                kustomization = {
                    "apiVersion": "kustomize.config.k8s.io/v1beta1",
                    "kind": "Kustomization",
                    "namespace": "argocd",
                    "resources": [],
                }

            resources = kustomization.get("resources", [])
            if resource_entry not in resources:
                resources.append(resource_entry)
                kustomization["resources"] = resources
                with open(kustomization_file, "w") as f:
                    yaml.dump(kustomization, f, default_flow_style=False, sort_keys=False)
                log.info(f"Registered {resource_entry} in kustomization.yaml")
        except Exception as e:
            log.info(f"Failed to update kustomization.yaml: {e}", err=True)
            raise typer.Exit(1)

        log.info(f"ArgoCD app: {argocd_output_file}")
    else:
        log.info(f"\n (Skipping ArgoCD application generation)")
