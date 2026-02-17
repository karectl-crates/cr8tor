import typer
import cr8tor.airlock.schema as schemas
import cr8tor.cli.build as ro_crate_builder
import cr8tor.airlock.resourceops as project_resources
import cr8tor.airlock.linkml_ops as linkml_ops
from pathlib import Path
from datetime import datetime
from typing import Optional

# Import LinkML Pydantic models for Actions
from cr8tor_metamodel.datamodel.cr8tor_metamodel_pydantic import (
    CreateAction,
    AssessAction,
    ActionStatusType,
)


def close_create_action_command(
    command_type: schemas.Cr8torCommandType,
    start_time: datetime,
    project_id: str,
    agent: str,
    governance_path: Path,
    resources_dir: Path,
    exit_msg: str,
    exit_code: int,
    instrument: str,
    result: Optional[list] = [],
    dryrun: Optional[bool] = False,
    config_file: Optional[Path] = "./config.toml",
):
    """
    CreateAction - updated to work with LinkML YAML resources
    """

    if exit_code == schemas.Cr8torReturnCode.SUCCESS:
        status_type = ActionStatusType.CompletedActionStatus
        err = None
    else:
        status_type = ActionStatusType.FailedActionStatus
        err = exit_msg

    action_props = CreateAction(
        id=f"{command_type}-{project_id}",
        type="CreateAction",
        name=f"{command_type} Data Project Action",
        start_time=start_time,
        end_time=datetime.now(),
        action_status=status_type,
        agent=agent,
        error=err,
        instrument=instrument,
        result=[str(r.get("@id", r)) if isinstance(r, dict) else str(r) for r in result] if result else [],
    )

    # Delete existing action with same ID, then append the new one
    # Using raw YAML operations since we're working with the actions list
    try:
        raw_data = linkml_ops.read_yaml_raw(governance_path)
        
        # Initialize project.actions if it doesn't exist
        if 'project' not in raw_data:
            raw_data['project'] = {}
        if 'actions' not in raw_data['project']:
            raw_data['project']['actions'] = []
        
        # Remove any existing action with the same ID
        raw_data['project']['actions'] = [
            action for action in raw_data['project']['actions']
            if action.get('id') != f"{command_type}-{project_id}"
        ]
        
        # Append the new action
        raw_data['project']['actions'].append(action_props.model_dump(mode='json', exclude_none=True))
        
        # Save updated data
        import yaml
        with open(governance_path, 'w') as f:
            yaml.dump(raw_data, f, sort_keys=False, default_flow_style=False, allow_unicode=True)
            
    except Exception as e:
        # Fall back to simple append if there's an error
        linkml_ops.append_to_list_field(
            governance_path,
            "project.actions",
            action_props.model_dump(mode='json', exclude_none=True)
        )

    ro_crate_builder.build(resources_dir, config_file, dryrun)
    exit_command(command_type, exit_code, exit_msg)


def close_assess_action_command(
    command_type: schemas.Cr8torCommandType,
    start_time: datetime,
    project_id: str,
    agent: str,
    governance_path: Path,
    resources_dir: Path,
    exit_msg: str,
    exit_code: int,
    instrument: str,
    additional_type: Optional[str] = None,
    result: Optional[list] = [],
):
    """
    AssessAction
    """

    if exit_code == schemas.Cr8torReturnCode.SUCCESS:
        status_type = ActionStatusType.CompletedActionStatus
        err = None
    else:
        status_type = ActionStatusType.FailedActionStatus
        err = exit_msg

    action_props = AssessAction(
        id=f"{command_type}-{project_id}",
        type="AssessAction",
        name=f"{command_type} Data Project Action",
        start_time=start_time,
        end_time=datetime.now(),
        action_status=status_type,
        agent=agent,
        error=err,
        instrument=instrument,
        additional_type=additional_type,
        result=[str(r.get("@id", r)) if isinstance(r, dict) else str(r) for r in result] if result else [],
    )

    #
    # This assumes validate can be run multiple times on a project
    # Ensures previous run entities for this action are cleared in "actions" before
    # actions is updated with the new action entity
    #

    # Delete existing action with same ID, then append the new one
    # Using raw YAML operations since we're working with the actions list
    try:
        raw_data = linkml_ops.read_yaml_raw(governance_path)
        
        # Initialize project.actions if it doesn't exist
        if 'project' not in raw_data:
            raw_data['project'] = {}
        if 'actions' not in raw_data['project']:
            raw_data['project']['actions'] = []
        
        # Remove any existing action with the same ID
        raw_data['project']['actions'] = [
            action for action in raw_data['project']['actions']
            if action.get('id') != f"{command_type}-{project_id}"
        ]
        
        # Append the new action
        raw_data['project']['actions'].append(action_props.model_dump(mode='json', exclude_none=True))
        
        # Save updated data using centralized write function
        linkml_ops.write_yaml_raw(governance_path, raw_data)
            
    except Exception as e:
        # Fall back to simple append if there's an error
        linkml_ops.append_to_list_field(
            governance_path,
            "project.actions",
            action_props.model_dump(mode='json', exclude_none=True)
        )

    ro_crate_builder.build(resources_dir)
    exit_command(command_type, exit_code, exit_msg)


def exit_command(
    command_type: schemas.Cr8torCommandType, exit_code: int, exit_msg: str
):
    """
    Exit the command with the appropriate success or error code and message
    """
    if exit_code == schemas.Cr8torReturnCode.SUCCESS:
        typer.echo(f"{exit_msg}")
    else:
        typer.echo(
            f"'{command_type}' command failed with {exit_code.name} (code {exit_code}): {exit_msg}",
            err=True,
        )
        raise typer.Exit(code=exit_code)
