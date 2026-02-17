import os
import sys
import uuid
import typer
import cr8tor.airlock.schema as schemas

from pathlib import Path
from typing import Annotated
from datetime import datetime
import cr8tor.airlock.resourceops as project_resources
import cr8tor.airlock.linkml_ops as linkml_ops
import cr8tor.airlock.crate_graph as proj_graph
import cr8tor.cli.utils as cli_utils
from cr8tor.utils import log

from cr8tor_metamodel.datamodel.cr8tor_metamodel_pydantic import (
    Cr8tor,
    Governance,
    Ingress,
    Deployment,
    Project,
)

app = typer.Typer()

@app.command(name="create")
def create(
    agent: Annotated[
        str,
        typer.Option("-a", help="The agent label triggering the validation."),
    ] = None,
    resources_dir: Annotated[
        Path,
        typer.Option(
            "-i", help="Directory containing resources to include in RO-Crate."
        ),
    ] = "./resources",
    bagit_dir: Annotated[
        Path,
        typer.Option(
            "-b", help="Bagit directory containing RO-Crate data directory"
        ),
    ] = "./bagit",
    config_file: Annotated[
        Path, typer.Option("-c", help="Location of configuration TOML file.")
    ] = "./config.toml",
    dryrun: Annotated[bool, typer.Option("--dryrun")] = False,
):
    """
    Generates the initial RO-Crate data crate within the target Cr8tor project from the specified metadata resources.

    This command performs the following actions:
    - Loads and validates the LinkML-based project structure (governance, ingress, deployment)
    - Generates a UUID for the project
    - Builds an RO-Crate along with an RO-Crate knowledge graph
    - Packages the crate as a non-serialized BagIt Archive in the "bagit/" directory
    - If the `dryrun` option is provided, prints the crate details without writing to the "crate/" directory

    Args:
        agent (str): The agent label triggering the validation. Defaults to None.
        resources_dir (Path): Directory containing resources to include in the RO-Crate. Defaults to "./resources".
        bagit_dir (Path): Bagit directory containing the RO-Crate data directory. Defaults to "./bagit".
        config_file (Path): Location of the configuration TOML file. Defaults to "./config.toml".
        dryrun (bool): If True, prints the crate details without writing to the "crate/" directory. Defaults to False.

    Example usage:
        cr8tor create -a agent_label -i path-to-resources-dir -b path-to-bagit-dir -c path-to-config-file --dryrun
    """

    if agent is None:
        agent = os.getenv("AGENT_USER")

    exit_msg = "Create complete"
    exit_code = schemas.Cr8torReturnCode.SUCCESS

    create_start_dt = datetime.now()
    project_uuid: Annotated[
        str,
        "Project UUID is a unique auto-generated identifier on creation of the project",
    ] = os.getenv("PROJECT_UUID", str(uuid.uuid4()))

    log.info(f"{resources_dir}")

    if not resources_dir.exists():
        cli_utils.exit_command(
            schemas.Cr8torCommandType.CREATE,
            schemas.Cr8torReturnCode.ACTION_EXECUTION_ERROR,
            f"Missing resources directory at: {resources_dir}",
        )

    # Define paths to the three LinkML YAML resource files
    governance_path = resources_dir.joinpath("governance", "cr8-governance.yaml")
    ingress_path = resources_dir.joinpath("data", "cr8-ingress.yaml")
    deployment_path = resources_dir.joinpath("deployment", "cr8-deployment.yaml")

    # Validate that all required resource files exist
    for path, name in [
        (governance_path, "governance"),
        (ingress_path, "ingress"),
        (deployment_path, "deployment"),
    ]:
        if not path.exists():
            cli_utils.exit_command(
                schemas.Cr8torCommandType.CREATE,
                schemas.Cr8torReturnCode.ACTION_EXECUTION_ERROR,
                f"Missing {name} resource file at: {path}",
            )

    # Load and validate the LinkML-based resources using Pydantic models
    try:
        governance = linkml_ops.load_yaml_as_pydantic(governance_path, Governance)
        ingress = linkml_ops.load_yaml_as_pydantic(ingress_path, Ingress)
        deployment = linkml_ops.load_yaml_as_pydantic(deployment_path, Deployment)
    except Exception as e:
        cli_utils.exit_command(
            schemas.Cr8torCommandType.CREATE,
            schemas.Cr8torReturnCode.ACTION_EXECUTION_ERROR,
            f"Error loading or validating resources: {str(e)}",
        )

    # Create the complete Cr8tor project instance
    try:
        cr8tor_project = Cr8tor(
            governance=governance,
            ingress=ingress,
            deployment=deployment,
        )
    except Exception as e:
        cli_utils.exit_command(
            schemas.Cr8torCommandType.CREATE,
            schemas.Cr8torReturnCode.ACTION_EXECUTION_ERROR,
            f"Error creating Cr8tor project instance: {str(e)}",
        )

    # Check if project has already been created (assuming project has id attribute)
    if bagit_dir.exists():
        if governance.project and governance.project.id:
            current_rocrate_graph = proj_graph.ROCrateGraph(bagit_dir)
            if current_rocrate_graph.is_project_action_complete(
                command_type=schemas.Cr8torCommandType.CREATE,
                action_type=schemas.RoCrateActionType.CREATE,
                project_id=governance.project.id,
            ):
                cli_utils.exit_command(
                    schemas.Cr8torCommandType.CREATE,
                    schemas.Cr8torReturnCode.ACTION_EXECUTION_ERROR,
                    "Create command can only be run once on a project",
                )

    # Initialize project if not already present
    if not governance.project:
        governance.project = Project(
            name="default-project",
            description="",
            reference=""
        )

    # Set project ID and start time (assuming these fields exist in the Project model)
    if governance.project.id is None:
        linkml_ops.update_yaml_field(governance_path, "project.id", project_uuid)
    
    if governance.project.start_time is None:
        linkml_ops.update_yaml_field(
            governance_path,
            "project.start_time",
            create_start_dt.strftime("%Y%m%d_%H%M%S")
        )

    # Initialize actions list if it doesn't exist (assuming actions field exists in Project model)
    if not hasattr(governance.project, 'actions'):
        linkml_ops.update_yaml_field(governance_path, "project.actions", [])

    cli_utils.close_create_action_command(
        command_type=schemas.Cr8torCommandType.CREATE,
        start_time=create_start_dt,
        project_id=project_uuid,
        agent=agent,
        governance_path=governance_path,
        resources_dir=resources_dir,
        exit_msg=exit_msg,
        exit_code=exit_code,
        instrument=os.getenv("APP_NAME"),
        result=[{"@id": project_uuid}],
        dryrun=dryrun,
        config_file=config_file,
    )
