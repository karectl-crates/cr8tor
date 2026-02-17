import os
import typer
import asyncio
import uuid
from pathlib import Path
from typing import Annotated
import cr8tor.airlock.schema as schemas
import cr8tor.airlock.linkml_ops as linkml_ops
import cr8tor.airlock.crate_graph as proj_graph
import cr8tor.cli.utils as cli_utils

from datetime import datetime

import cr8tor.airlock.api_client as api

# Import LinkML Pydantic models
from cr8tor_metamodel.datamodel.cr8tor_metamodel_pydantic import (
    Governance,
    Ingress,
)

app = typer.Typer()


@app.command(name="publish")
def publish(
    agent: Annotated[
        str,
        typer.Option(default="-a", help="The agent label triggering the validation."),
    ] = None,
    bagit_dir: Annotated[
        Path,
        typer.Option(
            default="-b", help="Bagit directory containing RO-Crate data directory"
        ),
    ] = "./bagit",
    resources_dir: Annotated[
        Path,
        typer.Option(
            default="-i", help="Directory containing resources to include in RO-Crate."
        ),
    ] = "./resources",
):
    """
    Publishes the data by transferring it from staging to production storage, making it accessible to a TRE and/or authorised TRE workspace.

    Args:
        agent (str): The agent label triggering the validation. Defaults to None.
        bagit_dir (Path): Path to the Bagit directory containing the RO-Crate data directory. Defaults to "./bagit".
        resources_dir (Path): Path to the directory containing resources to include in the RO-Crate. Defaults to "./resources".

    This command performs the following actions:
    - Transfers the staged data to production storage.
    - Ensures the data is accessible to the TRE or authorised TRE workspace.

    Example usage:
        cr8tor publish -a <agent_label> -b <path-to-bagit-dir> -i <path-to-resources-dir>
    """
    if agent is None:
        agent = os.getenv("AGENT_USER")

    exit_msg = "Publish complete"
    exit_code = schemas.Cr8torReturnCode.SUCCESS
    publish_results = []
    start_time = datetime.now()

    # Load LinkML-based governance and ingress YAML files
    governance_path = resources_dir.joinpath("governance", "cr8-governance.yaml")
    ingress_path = resources_dir.joinpath("data", "cr8-ingress.yaml")
    
    try:
        governance = linkml_ops.load_yaml_as_pydantic(governance_path, Governance)
        ingress = linkml_ops.load_yaml_as_pydantic(ingress_path, Ingress)
    except Exception as e:
        raise ValueError(f"Error loading project resources: {str(e)}")
    
    project_info = governance.project
    project_id = project_info.id if project_info.id else project_info.reference

    if not bagit_dir.exists():
        cli_utils.exit_command(
            schemas.Cr8torCommandType.DISCLOSURE_CHECK,
            schemas.Cr8torReturnCode.ACTION_EXECUTION_ERROR,
            f"Missing bagit directory at: {bagit_dir}",
        )

    current_rocrate_graph = proj_graph.ROCrateGraph(bagit_dir)
    if not current_rocrate_graph.is_project_action_complete(
        command_type=schemas.Cr8torCommandType.DISCLOSURE_CHECK,
        action_type=schemas.RoCrateActionType.ASSESS,
        project_id=project_id,
    ):
        cli_utils.close_create_action_command(
            command_type=schemas.Cr8torCommandType.PUBLISH,
            start_time=start_time,
            project_id=project_id,
            agent=agent,
            governance_path=governance_path,
            resources_dir=resources_dir,
            exit_msg="The data project must have disclosure completed before publishing",
            exit_code=schemas.Cr8torReturnCode.ACTION_WORKFLOW_ERROR,
            instrument=os.getenv("PUBLISH_NAME"),
        )

    # TODO: Discuss with Piotr whether the publish function should be called per dataset or per project?
    # Currently publishes the entire project

    try:
        publish_req = schemas.DataContractPublishRequest(
            project_name=project_info.name,
            project_start_time=project_info.start_time if project_info.start_time else datetime.now().isoformat(),
            destination={
                "type": ingress.destination.type.value if hasattr(ingress.destination.type, 'value') else str(ingress.destination.type),
                "url": ingress.destination.url if ingress.destination.url else "",
            },
        )

        resp_dict = asyncio.run(api.publish(publish_req))
        resp_dict["destination_type"] = ingress.destination.type.value if hasattr(ingress.destination.type, 'value') else str(ingress.destination.type)
        validate_resp = schemas.PublishPayload(**resp_dict)
        if validate_resp.data_published:
            publish_location_dict = validate_resp.data_published[0].model_dump()
            publish_location_dict["@id"] = str(uuid.uuid4())

            publish_results.append(publish_location_dict)

            # Update the first dataset's locations with the publish path
            # TODO: Handle multiple datasets and their respective publish paths
            if ingress.datasets and len(ingress.datasets) > 0:
                dataset = ingress.datasets[0]
                if not dataset.locations:
                    dataset.locations = []
                dataset.locations.append(publish_location_dict)
                
                # Save updated ingress YAML with publish location
                linkml_ops.save_pydantic_as_yaml(ingress_path, ingress)

    except Exception as e:
        cli_utils.close_create_action_command(
            command_type=schemas.Cr8torCommandType.PUBLISH,
            start_time=start_time,
            project_id=project_id,
            agent=agent,
            governance_path=governance_path,
            resources_dir=resources_dir,
            exit_msg=f"{str(e)}",
            exit_code=schemas.Cr8torReturnCode.UNKNOWN_ERROR,
            instrument=os.getenv("PUBLISH_NAME"),
        )

    cli_utils.close_create_action_command(
        command_type=schemas.Cr8torCommandType.PUBLISH,
        start_time=start_time,
        project_id=project_id,
        agent=agent,
        governance_path=governance_path,
        resources_dir=resources_dir,
        exit_msg=exit_msg,
        exit_code=exit_code,
        instrument=os.getenv("PUBLISH_NAME"),
        result=publish_results,
    )

    # if publish_results:
    #     status = schemas.ActionStatusType.COMPLETED
    # else:
    #     # TODO: Is no path in response for datasets a failure?
    #     status = schemas.ActionStatusType.FAILED
    #     err = "No result"

    # create_publish_action_props = schemas.CreateActionProps(
    #     id=f"publish-action-{project_info['project']['id']}",
    #     name="Publish LSC Project Action",
    #     start_time=start_time,
    #     end_time=datetime.now(),
    #     action_status=status,
    #     agent=agent,
    #     error=err,
    #     instrument=os.getenv("PUBLISH_NAME"),
    #     result=publish_results,
    # )

    # project_resources.delete_resource_entity(
    #     project_resource_path,
    #     "actions",
    #     "id",
    #     f"publish-action-{project_info['project']['id']}",
    # )
    # project_resources.update_resource_entity(
    #     project_resource_path, "actions", create_publish_action_props.model_dump()
    # )

    # ro_crate_builder.build(resources_dir)
