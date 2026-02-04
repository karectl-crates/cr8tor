import os
import typer
import yaml
import jsonschema
from pathlib import Path
from typing import Annotated
from datetime import datetime
from cr8tor.utils import log

import cr8tor.airlock.resourceops as project_resources
import cr8tor.airlock.schema as schemas
from cr8tor.models.identity import ProjectSpec, AppConfig, ProfileConfig, UserSpec

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

    # Detect project.toml in governance directory
    project_resource_path = resources_dir.joinpath("governance", "project.toml")
    if not project_resource_path.exists():
        log.info(
            f"✗ Project metadata file not found: {project_resource_path}", err=True
        )
        raise typer.Exit(1)

    log.info(f"Reading project metadata from {project_resource_path}")

    # Read project data using resourceops API
    try:
        project_dict = project_resources.read_resource_entity(
            project_resource_path, "project"
        )
        project_props = schemas.ProjectProps(**project_dict)
    except Exception as e:
        log.info(f"✗ Failed to read project metadata: {e}", err=True)
        raise typer.Exit(1)

    log.info(
        f"✓ Loaded project: {project_props.name} (ID: {project_props.id or 'N/A'})"
    )

    # Create ProjectSpec Pydantic model
    try:
        # Build apps list with default examples
        apps = [
            AppConfig(
                name="jupyterhub",
                type="jupyterhub",
                url=f"https://jupyter.{project_props.reference or 'project'}.example.com",
                config={"enabled": True, "auth": "oauth2"},
            ),
            AppConfig(
                name="rstudio",
                type="rstudio",
                url=f"https://rstudio.{project_props.reference or 'project'}.example.com",
                config={"enabled": False},
            ),
        ]

        # Build profiles list with default examples
        profiles = [
            ProfileConfig(
                display_name="Data Science - Python",
                slug="datascience-python",
                description="Python-based data science environment with common ML libraries",
                kubespawner_override={
                    "image": "jupyter/datascience-notebook:latest",
                    "env": {"JUPYTER_ENABLE_LAB": "yes"},
                },
            ),
            ProfileConfig(
                display_name="R Statistical Computing",
                slug="r-stats",
                description="R environment for statistical analysis",
                kubespawner_override={
                    "image": "rocker/tidyverse:latest",
                    "env": {"DISABLE_AUTH": "true"},
                },
            ),
        ]

        project_spec = ProjectSpec(
            description=project_props.name or "CR8TOR Project",
            apps=apps,
            profiles=profiles,
        )

        log.info(
            f"✓ Created ProjectSpec with {len(project_spec.apps)} apps and {len(project_spec.profiles)} profiles"
        )

    except Exception as e:
        log.info(f"✗ Failed to create ProjectSpec: {e}", err=True)
        raise typer.Exit(1)

    # Create full Project CRD
    project_name = project_props.reference or project_props.id or "unnamed-project"
    project_crd = {
        "apiVersion": "research.karectl.io/v1alpha1",
        "kind": "Project",
        "metadata": {
            "name": project_name,
            "labels": {
                "cr8tor.io/project-id": project_props.id or "unknown",
                "cr8tor.io/created-at": datetime.now().strftime("%Y%m%d"),
            },
        },
        "spec": project_spec.model_dump(exclude_none=True),
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

    # Read requesting_agent data from project.toml
    try:
        requesting_agent_dict = project_resources.read_resource_entity(
            project_resource_path, "requesting_agent"
        )
        requesting_agent_props = schemas.AgentProps(**requesting_agent_dict)
    except Exception as e:
        log.info(f"⚠ Failed to read requesting_agent metadata: {e}")
        log.info(f"  Skipping User CRD generation")
        return

    log.info(f"\n✓ Loaded requesting agent: {requesting_agent_props.name}")

    # Create UserSpec from requesting_agent
    try:
        # Extract username from email or name
        username = (
            requesting_agent_props.name.lower()
            .replace(" ", ".")
            .replace("prof.", "")
            .replace("dr.", "")
            .strip()
        )

        # Generate email if not present in name
        email = f"{username}@{requesting_agent_props.affiliation.name.lower().replace(' ', '')}.com"

        user_spec = UserSpec(
            username=username,
            email=email,
            enabled=True,
            groups=[project_name],  # Add user to project group
            keycloak={"firstName": requesting_agent_props.name.split()[0] if " " in requesting_agent_props.name else requesting_agent_props.name, "lastName": requesting_agent_props.name.split()[-1] if " " in requesting_agent_props.name else ""},
            jupyterhub={"admin": False},
            karectl={"organization": requesting_agent_props.affiliation.name},
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
            "name": username,
            "labels": {
                "cr8tor.io/project-id": project_props.id or "unknown",
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
    user_output_file = output_dir.joinpath(f"user-{username}.yaml")
    try:
        with open(user_output_file, "w") as f:
            yaml.dump(user_crd, f, default_flow_style=False, sort_keys=False)

        log.info(f"✓ User CRD written to {user_output_file}")

    except Exception as e:
        log.info(f"✗ Failed to write User CRD file: {e}", err=True)
        raise typer.Exit(1)

    log.info(f"\n✓ All deployment CRDs created successfully")
    log.info(f"  - Project CRD: {output_file}")
    log.info(f"  - User CRD: {user_output_file}")
