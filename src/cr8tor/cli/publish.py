import os
import typer
import asyncio
import uuid
from pathlib import Path
from typing import Annotated
import cr8tor.core.schema as schemas
import cr8tor.core.resourceops as project_resources
import cr8tor.core.crate_graph as proj_graph
import cr8tor.cli.utils as cli_utils

from datetime import datetime

import cr8tor.core.api_client as api

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

    project_resource_path = resources_dir.joinpath("governance", "project.toml")
    project_info = project_resources.read_resource(project_resource_path)

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
        project_id=project_info["project"]["id"],
    ):
        cli_utils.close_create_action_command(
            command_type=schemas.Cr8torCommandType.PUBLISH,
            start_time=start_time,
            project_id=project_info["project"]["id"],
            agent=agent,
            project_resource_path=project_resource_path,
            resources_dir=resources_dir,
            exit_msg="The data project must have disclosure completed before publishing",
            exit_code=schemas.Cr8torReturnCode.ACTION_WORKFLOW_ERROR,
            instrument=os.getenv("PUBLISH_NAME"),
        )

    dataset_meta_file = None

    # TODO: Discuss with Piotr whether the publish function should be called per dataset or per project?
    # Currently assumes 1 dataset file in metadata

    try:
        for f in resources_dir.joinpath("metadata").glob("dataset*.toml"):
            dataset_meta_file = f
            break

        publish_req = schemas.DataContractPublishRequest(
            project_name=project_info["project"]["project_name"],
            project_start_time=project_info["project"]["project_start_time"],
            destination=project_info["project"]["destination"],
        )

        resp_dict = asyncio.run(api.publish(publish_req))
        resp_dict["destination_type"] = project_info["project"]["destination"]["type"]
        validate_resp = schemas.PublishPayload(**resp_dict)
        if validate_resp.data_published:
            publish_location_dict = validate_resp.data_published[0].model_dump()
            publish_location_dict["@id"] = str(uuid.uuid4())

            publish_results.append(publish_location_dict)

            project_resources.create_resource_entity(
                dataset_meta_file, "publish_path", publish_location_dict
            )

    except Exception as e:
        cli_utils.close_create_action_command(
            command_type=schemas.Cr8torCommandType.PUBLISH,
            start_time=start_time,
            project_id=project_info["project"]["id"],
            agent=agent,
            project_resource_path=project_resource_path,
            resources_dir=resources_dir,
            exit_msg=f"{str(e)}",
            exit_code=schemas.Cr8torReturnCode.UNKNOWN_ERROR,
            instrument=os.getenv("PUBLISH_NAME"),
        )

    cli_utils.close_create_action_command(
        command_type=schemas.Cr8torCommandType.PUBLISH,
        start_time=start_time,
        project_id=project_info["project"]["id"],
        agent=agent,
        project_resource_path=project_resource_path,
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
