import os
import typer
import asyncio
import cr8tor.airlock.api_client as api
import cr8tor.airlock.schema as schemas
import cr8tor.airlock.linkml_ops as linkml_ops
import cr8tor.airlock.crate_graph as proj_graph
import cr8tor.cli.utils as cli_utils

from pathlib import Path
from typing import Annotated, List, Tuple, Optional
from datetime import datetime
from cr8tor.utils import log

# Import LinkML Pydantic models
from cr8tor_metamodel.datamodel.cr8tor_metamodel_pydantic import (
    Governance,
    Ingress,
    Dataset,
    Table,
    Column,
)

app = typer.Typer()


def merge_metadata_into_dataset(
    ingress_path: Path, dataset_name: str, metadata: schemas.DatasetMetadata
) -> None:
    """Merge validated metadata into the ingress YAML file for a specific dataset."""
    # Load the ingress YAML as Pydantic model
    ingress = linkml_ops.load_yaml_as_pydantic(ingress_path, Ingress)
    
    # Find the dataset by name
    target_dataset = None
    if ingress.datasets:
        for ds in ingress.datasets:
            if ds.name == dataset_name:
                target_dataset = ds
                break
    
    if not target_dataset:
        # Dataset not found, skip merge
        return
    
    # Initialize tables if not present
    if not target_dataset.tables:
        target_dataset.tables = []
    
    table_lookup = {table.name: table for table in target_dataset.tables}
    
    # Merge metadata tables into the dataset
    for meta_table in metadata.tables or []:
        if meta_table.name in table_lookup:
            existing_table = table_lookup[meta_table.name]
            if not existing_table.columns:
                existing_table.columns = []
            
            # Update description if provided
            if meta_table.description and not existing_table.description:
                existing_table.description = meta_table.description
            
            existing_col_lookup = {col.name: col for col in existing_table.columns}
            
            for meta_col in meta_table.columns or []:
                if meta_col.name not in existing_col_lookup:
                    # Add new column
                    new_col = Column(
                        name=meta_col.name,
                        datatype=meta_col.datatype or "string",
                        description=meta_col.description
                    )
                    existing_table.columns.append(new_col)
                else:
                    # Update existing column if fields are missing
                    existing_col = existing_col_lookup[meta_col.name]
                    if meta_col.description and not existing_col.description:
                        existing_col.description = meta_col.description
                    if meta_col.datatype and not existing_col.datatype:
                        existing_col.datatype = meta_col.datatype
        else:
            # Add new table
            new_columns = []
            if meta_table.columns:
                for col in meta_table.columns:
                    new_columns.append(
                        Column(
                            name=col.name,
                            datatype=col.datatype or "string",
                            description=col.description
                        )
                    )
            
            new_table = Table(
                name=meta_table.name,
                description=meta_table.description,
                columns=new_columns if new_columns else None
            )
            target_dataset.tables.append(new_table)
    
    # Update dataset description if provided
    if metadata.description and not target_dataset.description:
        target_dataset.description = metadata.description
    
    # Save the updated ingress model back to YAML
    linkml_ops.save_pydantic_as_yaml(ingress_path, ingress)


def verify_tables_metadata(
    remote_metadata: List[schemas.TableMetadata],
    local_metadata: Optional[List[Table]],
) -> Tuple[bool, Optional[str]]:
    """Verify that local table metadata matches remote schema."""
    remote_lookup = {
        table.name: {col.name for col in table.columns} for table in remote_metadata
    }

    if local_metadata is not None:
        for local_table in local_metadata:
            table_name = local_table.name
            if table_name not in remote_lookup:
                return (
                    False,
                    f"Validation Error: Table '{table_name}' is missing from target schema metadata.",
                )

            remote_table_columns = remote_lookup[table_name]
            if local_table.columns is None:
                continue

            for filter_col in local_table.columns:
                if filter_col.name not in remote_table_columns:
                    return (
                        False,
                        f"Validation Error: Column '{filter_col.name}' is missing from target schema table '{table_name}' metadata.",
                    )

    return True, None


@app.command(name="validate")
def validate(
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
    Validate the contents of a Bagit directory containing an RO-Crate data directory.

    Args:
        agent (str): The agent label triggering the validation. Defaults to None.
        bagit_dir (Path): The Bagit directory containing the RO-Crate data directory.
                          Defaults to "./bagit".
        resources_dir (Path): The directory containing resources to include in the RO-Crate.
                              Defaults to "./resources".

    This function performs the following:
    - Validates the contents of the specified Bagit directory and its RO-Crate data directory.
    - Validates access and governance metadata resources.
    - Rebuilds the Bagit contents, including the RO-Crate metadata.

    Example usage:
        cr8tor validate -b <path-to-bagit-dir> -i <path-to-resources-dir>
    """

    if agent is None:
        agent = os.getenv("AGENT_USER")

    exit_msg = "Validation complete"
    exit_code = schemas.Cr8torReturnCode.SUCCESS

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

    current_rocrate_graph = proj_graph.ROCrateGraph(bagit_dir)
    if not current_rocrate_graph.is_project_action_complete(
        command_type=schemas.Cr8torCommandType.CREATE,
        action_type=schemas.RoCrateActionType.CREATE,
        project_id=project_id,
    ):
        cli_utils.close_assess_action_command(
            command_type=schemas.Cr8torCommandType.VALIDATE,
            start_time=start_time,
            project_id=project_id,
            agent=agent,
            governance_path=governance_path,
            resources_dir=resources_dir,
            exit_msg="The create command must be run on the target project before validation",
            exit_code=schemas.Cr8torReturnCode.ACTION_WORKFLOW_ERROR,
            instrument=os.getenv("METADATA_NAME"),
        )

    # Validate each dataset in the ingress configuration
    if ingress.datasets:
        for dataset in ingress.datasets:
            try:
                # Build the validation request from LinkML models
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
                
                # Build source data from ingress model
                source_data = {}
                if ingress.source:
                    # Add required fields for discriminated union
                    if hasattr(ingress.source, 'type') and ingress.source.type:
                        source_data["type"] = ingress.source.type
                    if hasattr(ingress.source, 'url') and ingress.source.url:
                        source_data["host_url"] = ingress.source.url  # Map url to host_url for compatibility
                    if hasattr(ingress.source, 'name') and ingress.source.name:
                        source_data["database"] = ingress.source.name  # Map name to database for SQL sources
                    
                    # Add default port if not specified (required field)
                    source_data["port"] = 5432  # Default PostgreSQL port, adjust based on type if needed
                    
                    # Add credentials if present
                    if hasattr(ingress.source, 'credentials') and ingress.source.credentials:
                        source_data["credentials"] = {
                            "provider": ingress.source.credentials.provider,
                            "password_key": ingress.source.credentials.password_key,
                            "username_key": ingress.source.credentials.username_key,
                        }
                    else:
                        # Provide default empty credentials if not present (required field)
                        source_data["credentials"] = {
                            "provider": "",
                            "password_key": "",
                            "username_key": "",
                        }
                
                # Build access contract for validation
                access_contract = schemas.DataContractValidateRequest(
                    project_name=project_info.name,
                    project_start_time=project_info.start_time if project_info.start_time else datetime.now().isoformat(),
                    destination={
                        "type": ingress.destination.type if hasattr(ingress.destination.type, 'value') else str(ingress.destination.type),
                        "url": ingress.destination.url if ingress.destination.url else "",
                    },
                    source=source_data if source_data else {},
                    extract_config=None,
                    dataset=schemas.DatasetMetadata(**dataset_meta_dict),
                )
                
                metadata = asyncio.run(api.validate_access(access_contract))


                validate_dataset_info = schemas.DatasetMetadata(**metadata)

            except Exception as e:
                cli_utils.close_assess_action_command(
                    command_type=schemas.Cr8torCommandType.VALIDATE,
                    start_time=start_time,
                    project_id=project_id,
                    agent=agent,
                    governance_path=governance_path,
                    resources_dir=resources_dir,
                    exit_msg=f"{str(e)}",
                    exit_code=schemas.Cr8torReturnCode.UNKNOWN_ERROR,
                    instrument=os.getenv("METADATA_NAME"),
                )

            is_valid, err = verify_tables_metadata(
                validate_dataset_info.tables, dataset.tables
            )
            if not is_valid:
                exit_msg = err
                exit_code = schemas.Cr8torReturnCode.VALIDATION_ERROR
                break

            merge_metadata_into_dataset(ingress_path, dataset.name, validate_dataset_info)
    #
    # This assumes validate can be run multiple times on a project
    # Ensures previous run entities for this action are cleared in "actions" before
    # actions is updated with the new action entity
    #

    cli_utils.close_assess_action_command(
        command_type=schemas.Cr8torCommandType.VALIDATE,
        start_time=start_time,
        project_id=project_id,
        agent=agent,
        governance_path=governance_path,
        resources_dir=resources_dir,
        exit_msg=exit_msg,
        exit_code=exit_code,
        instrument=os.getenv("METADATA_NAME"),
        additional_type="Semantic Validation",
    )
