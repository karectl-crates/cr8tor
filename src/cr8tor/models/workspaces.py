"""Workspace-related CRD models."""

from pydantic import Field
from typing import List, Optional, Dict, Any

from cr8tor.crd.registry import CRDRegistry
from cr8tor.crd.base import CRDSpec


class EnvironmentVariable(CRDSpec):
    """Environment variable specification."""

    name: str = Field(..., description="Environment variable name")
    value: str = Field(..., description="Environment variable value")


class VDIStorageConfig(CRDSpec):
    """Storage configuration for a VDI instance."""

    home_size: Optional[str] = Field(
        default=None, description="PVC size for home directory"
    )
    storage_class: Optional[str] = Field(
        default=None, description="Override project default StorageClass"
    )
    persist: bool = Field(
        default=False, description="Whether to persist storage across VDI restarts"
    )


class VDITolerationConfig(CRDSpec):
    """Kubernetes toleration configuration for VDI."""

    key: str = Field(..., description="Toleration key")
    operator: str = Field(default="Equal", description="Operator (Equal or Exists)")
    value: Optional[str] = Field(default=None, description="Toleration value")
    effect: Optional[str] = Field(default=None, description="Effect (NoSchedule, PreferNoSchedule, NoExecute)")
    toleration_seconds: Optional[int] = Field(default=None, description="Toleration seconds for NoExecute")


class VDIResourceConfig(CRDSpec):
    """Resource requests and limits for VDI instance."""

    requests_cpu: Optional[str] = Field(default=None, description="CPU request")
    requests_memory: Optional[str] = Field(default=None, description="Memory request")
    limits_cpu: Optional[str] = Field(default=None, description="CPU limit")
    limits_memory: Optional[str] = Field(default=None, description="Memory limit")


class VDISchedulingConfig(CRDSpec):
    """Scheduling configuration for a VDI instance (overrides project defaults)."""

    node_selector: Dict[str, str] = Field(
        default_factory=dict, description="Node selector labels"
    )
    tolerations: List[VDITolerationConfig] = Field(
        default_factory=list, description="Pod tolerations"
    )
    affinity: Optional[Dict[str, Any]] = Field(
        default=None, description="Pod affinity/anti-affinity rules"
    )
    resources: Optional[VDIResourceConfig] = Field(
        default=None, description="Resource requests/limits for this VDI"
    )
    labels: Dict[str, str] = Field(
        default_factory=dict, description="Additional labels for this VDI pod"
    )
    annotations: Dict[str, str] = Field(
        default_factory=dict, description="Additional annotations for this VDI pod"
    )


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
    storage: Optional[VDIStorageConfig] = Field(
        default=None, description="Storage configuration for persistent home directory"
    )
    scheduling: Optional[VDISchedulingConfig] = Field(
        default=None, description="Scheduling configuration overrides"
    )
    networking: Optional[Dict[str, Any]] = Field(
        default=None, description="Networking configuration"
    )
