"""Module to create, read, update and delete LinkML-based resources using Pydantic models.

This module provides operations for working with YAML files that conform to the cr8tor
LinkML metamodel, using auto-generated Pydantic models for validation and type safety.
"""

import yaml
from pathlib import Path
from typing import TypeVar, Type, Any, Dict
from pydantic import BaseModel, ValidationError

from cr8tor.utils import log

# Type variable for generic Pydantic model types
T = TypeVar('T', bound=BaseModel)


def load_yaml_as_pydantic(yaml_path: Path, model_class: Type[T]) -> T:
    """
    Load a YAML file and instantiate it as a Pydantic model with validation.
    
    Args:
        yaml_path: Path to the YAML file to load
        model_class: The Pydantic model class to instantiate
        
    Returns:
        An instance of the specified Pydantic model
        
    Raises:
        FileNotFoundError: If the YAML file doesn't exist
        ValidationError: If the YAML data doesn't conform to the model schema
    """
    try:
        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)
        
        if data is None:
            data = {}
            
        return model_class(**data)
    
    except FileNotFoundError:
        log.info(
            f"[red]Resource file missing[/red] - [bold red]{yaml_path}[/bold red]"
        )
        raise
    
    except ValidationError as e:
        log.info(
            f"[red]Validation error in[/red] - [bold red]{yaml_path}[/bold red]"
        )
        log.info(f"[red]{str(e)}[/red]")
        raise


def save_pydantic_as_yaml(
    yaml_path: Path, 
    model_instance: BaseModel,
    exclude_none: bool = True,
    by_alias: bool = True
) -> None:
    """
    Save a Pydantic model instance to a YAML file.
    
    Args:
        yaml_path: Path where the YAML file should be saved
        model_instance: The Pydantic model instance to serialize
        exclude_none: Whether to exclude None values from output
        by_alias: Whether to use field aliases in output
    """
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    
    data = model_instance.model_dump(
        exclude_none=exclude_none,
        by_alias=by_alias,
        mode='python'
    )
    
    with open(yaml_path, 'w') as f:
        yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False, allow_unicode=True)
    
    log.info(
        f"[cyan]Saved model to YAML file:[/cyan] - [bold magenta]{yaml_path}[/bold magenta]"
    )


def read_yaml_raw(yaml_path: Path) -> Dict[str, Any]:
    """
    Read a YAML file and return raw dictionary data without model validation.
    
    Args:
        yaml_path: Path to the YAML file to load
        
    Returns:
        Dictionary containing the YAML data
    """
    try:
        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)
        return data if data is not None else {}
    
    except FileNotFoundError:
        log.info(
            f"[red]Resource file missing[/red] - [bold red]{yaml_path}[/bold red]"
        )
        return {"Error": f"The resource file '{yaml_path}' is missing."}


def write_yaml_raw(yaml_path: Path, data: Dict[str, Any]) -> None:
    """
    Write raw dictionary data to a YAML file using safe_dump for consistency.
    
    Args:
        yaml_path: Path where the YAML file should be saved
        data: Dictionary data to write to YAML
    """
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(yaml_path, 'w') as f:
        yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False, allow_unicode=True)
    
    log.info(
        f"[cyan]Saved YAML file:[/cyan] - [bold magenta]{yaml_path}[/bold magenta]"
    )


def update_yaml_field(
    yaml_path: Path,
    field_path: str,
    value: Any,
    create_if_missing: bool = True
) -> None:
    """
    Update a specific field in a YAML file using dot notation for nested fields.
    
    Args:
        yaml_path: Path to the YAML file
        field_path: Dot-separated path to the field (e.g., "project.name")
        value: New value to set
        create_if_missing: Whether to create the field if it doesn't exist
        
    Example:
        update_yaml_field(path, "project.id", "12345")
        update_yaml_field(path, "project.start_date", datetime.now())
    """
    data = read_yaml_raw(yaml_path)
    
    # Navigate to the nested field
    keys = field_path.split('.')
    current = data
    
    for key in keys[:-1]:
        if key not in current:
            if create_if_missing:
                current[key] = {}
            else:
                raise KeyError(f"Field path '{field_path}' not found in {yaml_path}")
        current = current[key]
    
    # Set the value
    current[keys[-1]] = value
    
    # Save back to file
    with open(yaml_path, 'w') as f:
        yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False, allow_unicode=True)
    
    log.info(
        f"[cyan]Updated field '{field_path}' in:[/cyan] - [bold magenta]{yaml_path}[/bold magenta]"
    )


def merge_pydantic_updates(
    yaml_path: Path,
    model_class: Type[T],
    updates: Dict[str, Any]
) -> T:
    """
    Load a Pydantic model from YAML, merge updates, validate, and save.
    
    Args:
        yaml_path: Path to the YAML file
        model_class: The Pydantic model class
        updates: Dictionary of field updates to apply
        
    Returns:
        Updated and validated Pydantic model instance
    """
    # Load existing model
    model = load_yaml_as_pydantic(yaml_path, model_class)
    
    # Convert to dict, update, and recreate model for validation
    model_dict = model.model_dump()
    model_dict.update(updates)
    
    updated_model = model_class(**model_dict)
    
    # Save updated model
    save_pydantic_as_yaml(yaml_path, updated_model)
    
    return updated_model


def append_to_list_field(
    yaml_path: Path,
    field_path: str,
    item: Any
) -> None:
    """
    Append an item to a list field in a YAML file.
    
    Args:
        yaml_path: Path to the YAML file
        field_path: Dot-separated path to the list field
        item: Item to append to the list
    """
    data = read_yaml_raw(yaml_path)
    
    # Navigate to the nested field
    keys = field_path.split('.')
    current = data
    
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    
    # Ensure the field is a list and append
    if keys[-1] not in current:
        current[keys[-1]] = []
    
    if not isinstance(current[keys[-1]], list):
        raise TypeError(
            f"Field '{field_path}' is not a list in {yaml_path}"
        )
    
    current[keys[-1]].append(item)
    
    # Save back to file using centralized write function
    write_yaml_raw(yaml_path, data)
    
    log.info(
        f"[cyan]Appended to list field '{field_path}' in:[/cyan] - [bold magenta]{yaml_path}[/bold magenta]"
    )


def validate_yaml_against_model(yaml_path: Path, model_class: Type[T]) -> bool:
    """
    Validate a YAML file against a Pydantic model without loading it.
    
    Args:
        yaml_path: Path to the YAML file
        model_class: The Pydantic model class to validate against
        
    Returns:
        True if valid, False otherwise
    """
    try:
        load_yaml_as_pydantic(yaml_path, model_class)
        return True
    except (ValidationError, FileNotFoundError):
        return False
