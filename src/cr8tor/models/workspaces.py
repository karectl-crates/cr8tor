"""Workspace-related CRD models."""

from pydantic import Field
from typing import List, Optional, Dict, Any

from cr8tor.crd.registry import CRDRegistry
from cr8tor.crd.base import CRDSpec


class EnvironmentVariable(CRDSpec):
    """Environment variable specification."""

    name: str = Field(..., description="Environment variable name")
    value: str = Field(..., description="Environment variable value")


@CRDRegistry.register("karectl.io", "v1alpha1", "VDIInstance", "vdiinstances")
class VDIInstanceSpec(CRDSpec):
    """VDI Instance CRD specification."""

    user: str = Field(..., description="Username for the VDI instance")
    project: str = Field(..., description="Project name for the VDI instance")
    image: str = Field(
        default="ghcr.io/karectl/vdi-mate:v1.0.0-light",
        description="Container image to use for the VDI",
    )
    connection: str = Field(
        default="rdp", description="Connection type (rdp, vnc, etc.)"
    )
    env: List[EnvironmentVariable] = Field(
        default_factory=list,
        description="Environment variables to set in the VDI container",
    )
    resources: Optional[Dict[str, Any]] = Field(
        default=None, description="Resource requests and limits"
    )
    storage: Optional[Dict[str, Any]] = Field(
        default=None, description="Storage configuration"
    )
    networking: Optional[Dict[str, Any]] = Field(
        default=None, description="Networking configuration"
    )
