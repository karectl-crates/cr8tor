import os
import typer
import asyncio
import uuid

from pathlib import Path
from typing import Annotated
from datetime import datetime

import cr8tor.airlock.api_client as api
import cr8tor.airlock.schema as schemas
import cr8tor.airlock.linkml_ops as linkml_ops
import cr8tor.airlock.crate_graph as proj_graph
import cr8tor.cli.utils as cli_utils

# Import LinkML Pydantic models
from cr8tor_metamodel.datamodel.cr8tor_metamodel_pydantic import (
    Governance,
    Ingress,
    Dataset,
)


app = typer.Typer()


@app.command(name="stage-transfer")
def stage_transfer(
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
    Stages the data by transferring it from the specified source to the sink TRE.

    Args:
        agent (str): The agent label triggering the validation. Defaults to None.
        bagit_dir (Path): Path to the Bagit directory containing the RO-Crate data directory.
                          Defaults to "./bagit".
        resources_dir (Path): Path to the directory containing resources to include in the RO-Crate.
                              Defaults to "./resources".

    This function prepares the data transfer for the specified CR8 project by:
    - Validating the current RO-Crate graph.
    - Ensuring that all necessary resources are included.

    Example usage:
        cr8tor stage-transfer -a agent_label -b path-to-bagit-dir -i path-to-resources-dir
    """

    if agent is None:
        agent = os.getenv("AGENT_USER")

    exit_msg = "Staging transfer complete"
    exit_code = schemas.Cr8torReturnCode.SUCCESS
    staging_results = []
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
        command_type=schemas.Cr8torCommandType.SIGN_OFF,
        action_type=schemas.RoCrateActionType.ASSESS,
        project_id=project_id,
    ):
        cli_utils.close_create_action_command(
            command_type=schemas.Cr8torCommandType.STAGE_TRANSFER,
            start_time=start_time,
            project_id=project_id,
            agent=agent,
            governance_path=governance_path,
            resources_dir=resources_dir,
            exit_msg="The data project must have sign-off before staging the data transfer",
            exit_code=schemas.Cr8torReturnCode.ACTION_WORKFLOW_ERROR,
            instrument=os.getenv("PUBLISH_NAME"),
        )

    # Process each dataset in the ingress configuration
    if ingress.datasets:
        for dataset in ingress.datasets:
            try:
                # Convert LinkML Dataset to old schema format for API compatibility
                dataset_meta_dict = {
                    "name": dataset.name,
                    "schema_name": dataset.schema_name,
                    "description": dataset.description if hasattr(dataset, 'description') else None,
                    "tables": [],
                }
                
                if dataset.tables:
                    for table in dataset.tables:
                        table_dict = {
                            "name": table.name,
                            "description": table.description if hasattr(table, 'description') else None,
                            "columns": [],
                        }
                        if table.columns:
                            for col in table.columns:
                                col_dict = {
                                    "name": col.name,
                                    "datatype": col.datatype,
                                }
                                if hasattr(col, 'description') and col.description:
                                    col_dict["description"] = col.description
                                table_dict["columns"].append(col_dict)
                        dataset_meta_dict["tables"].append(table_dict)
                
                dataset_props = schemas.DatasetMetadata(**dataset_meta_dict)
                
                # Build source data from ingress model
                source_data = {}
                if ingress.source:
                    if hasattr(ingress.source, 'type') and ingress.source.type:
                        source_data["type"] = ingress.source.type
                    if hasattr(ingress.source, 'url') and ingress.source.url:
                        source_data["host_url"] = ingress.source.url
                    if hasattr(ingress.source, 'name') and ingress.source.name:
                        source_data["database"] = ingress.source.name
                    
                    source_data["port"] = 5432  # Default port
                    
                    if hasattr(ingress.source, 'credentials') and ingress.source.credentials:
                        source_data["credentials"] = {
                            "provider": ingress.source.credentials.provider,
                            "password_key": ingress.source.credentials.password_key,
                            "username_key": ingress.source.credentials.username_key,
                        }
                    else:
                        source_data["credentials"] = {
                            "provider": "",
                            "password_key": "",
                            "username_key": "",
                        }
                
                # Build access contract for transfer
                access_contract = schemas.DataContractTransferRequest(
                    project_name=project_info.name,
                    project_start_time=project_info.start_time if project_info.start_time else datetime.now().isoformat(),
                    destination={
                        "type": ingress.destination.type.value if hasattr(ingress.destination.type, 'value') else str(ingress.destination.type),
                        "url": ingress.destination.url if ingress.destination.url else "",
                    },
                    source=source_data if source_data else {},
                    dataset=dataset_props,
                )

                resp_dict = asyncio.run(api.stage_transfer(access_contract))
                resp_dict["destination_type"] = ingress.destination.type.value if hasattr(ingress.destination.type, 'value') else str(ingress.destination.type)
                validate_resp = schemas.StageTransferPayload(**resp_dict)

                # TODO: Handle multiple staging locations
                # TODO: Add error response handler for action error property

                if validate_resp.data_retrieved:
                    staging_location_dict = validate_resp.data_retrieved[0].model_dump()
                    staging_location_dict["@id"] = str(uuid.uuid4())

                    staging_results.append(staging_location_dict)

                    # Update the dataset in the ingress YAML with staging location
                    # TODO: Add staging_path to LinkML Dataset model when needed
                    # For now, we'll skip updating the YAML since staging_path isn't in the model

            except Exception as e:
                cli_utils.close_create_action_command(
                    command_type=schemas.Cr8torCommandType.STAGE_TRANSFER,
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
        command_type=schemas.Cr8torCommandType.STAGE_TRANSFER,
        start_time=start_time,
        project_id=project_id,
        agent=agent,
        governance_path=governance_path,
        resources_dir=resources_dir,
        exit_msg=exit_msg,
        exit_code=exit_code,
        instrument=os.getenv("PUBLISH_NAME"),
        result=staging_results,
    )

    # if staging_results:
    #     status = schemas.ActionStatusType.COMPLETED
    # else:
    #     # TODO: Is no path in response for datasets a failure?
    #     status = schemas.ActionStatusType.FAILED

    # create_transfer_action_props = schemas.CreateActionProps(
    #     id=f"stage-transfer-action-{project_info['project']['id']}",
    #     name="Stage Data Transfer Action",
    #     start_time=start_time,
    #     end_time=datetime.now(),
    #     action_status=status,
    #     agent=agent,
    #     error=None,
    #     instrument=os.getenv("PUBLISH_NAME"),
    #     result=staging_results,
    # )

    # project_resources.delete_resource_entity(
    #     project_resource_path,
    #     "actions",
    #     "id",
    #     f"stage-transfer-action-{project_info['project']['id']}",
    # )
    # project_resources.update_resource_entity(
    #     project_resource_path, "actions", create_transfer_action_props.model_dump()
    # )

    # ro_crate_builder.build(resources_dir)
