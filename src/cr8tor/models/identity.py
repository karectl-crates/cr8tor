"""Identity-related CRD models."""

from pydantic import Field
from typing import List, Optional, Dict, Any
from cr8tor.crd.registry import CRDRegistry
from cr8tor.crd.base import CRDSpec


@CRDRegistry.register("identity.karectl.io", "v1alpha1", "User", "users")
class UserSpec(CRDSpec):
    """User CRD specification."""

    username: str = Field(..., description="Unique username for the user")
    email: str = Field(..., description="Email address of the user")
    enabled: bool = Field(default=True, description="Whether the user is enabled")
    password: Optional[str] = Field(
        default=None, description="User password (if not set, a temporary password will be generated)"
    )
    groups: List[str] = Field(
        default_factory=list, description="List of groups the user belongs to"
    )
    keycloak: Optional[Dict[str, Any]] = Field(
        default=None, description="Keycloak-specific configuration"
    )
    jupyterhub: Optional[Dict[str, Any]] = Field(
        default=None, description="JupyterHub-specific configuration"
    )
    karectl: Optional[Dict[str, Any]] = Field(
        default=None, description="Karectl-specific configuration"
    )


@CRDRegistry.register("identity.karectl.io", "v1alpha1", "Group", "groups")
class GroupSpec(CRDSpec):
    """Group CRD specification."""

    description: str = Field(
        default="", description="Human-readable description of the group"
    )
    attributes: Dict[str, Any] = Field(
        default_factory=dict, description="Additional attributes for the group"
    )
    members: List[str] = Field(
        default_factory=list,
        description="List of usernames that are members of this group",
    )
    projects: List[str] = Field(
        default_factory=list,
        description="List of projects that this group has access to",
    )
    subgroups: List[str] = Field(
        default_factory=list,
        description="List of subgroups belonging to this group",
    )


@CRDRegistry.register(
    "identity.karectl.io", "v1alpha1", "KeycloakClient", "keycloakclients"
)
class KeycloakClientSpec(CRDSpec):
    """Keycloak Client CRD specification."""

    clientId: str = Field(..., description="Unique client identifier")
    name: Optional[str] = Field(default=None, description="Human-readable client name")
    secret: Optional[str] = Field(
        default=None,
        description="Client secret"
    )
    secretRef: Optional[Dict[str, str]] = Field(
        default=None,
        description="Reference to Kubernetes secret containing client secret",
    )
    enabled: bool = Field(default=True, description="Whether the client is enabled")
    publicClient: bool = Field(
        default=False, description="Whether this is a public client"
    )
    redirectUris: List[str] = Field(
        default_factory=list, description="Valid redirect URIs for the client"
    )
    webOrigins: List[str] = Field(
        default_factory=list, description="Valid web origins for CORS"
    )
    protocol: str = Field(
        default="openid-connect", description="Authentication protocol"
    )
    defaultClientScopes: List[str] = Field(
        default_factory=list,
        description="List of default client scopes (openid, profile, email, groups)",
    )
    optionalClientScopes: List[str] = Field(
        default_factory=list,
        description="List of optional client scopes",
    )
    protocolMappers: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Protocol mappers configuration (audience mapper, group mapper)",
    )
    attributes: Dict[str, Any] = Field(
        default_factory=dict, description="Additional client attributes"
    )
    additionalConfig: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional Keycloak client configuration",
    )

class ResourceQuotaConfig(CRDSpec):
    """ Resource quota configuration for a project namespace."""

    requests_cpu: Optional[str] = Field(
        default="4", description="Total CPU requests allowed"
    )
    requests_memory: Optional[str] = Field(
        default="8Gi", description="Total memory requests allowed"
    )
    limits_cpu: Optional[str] = Field(
        default="8", description="Total CPU limits allowed"
    )
    limits_memory: Optional[str] = Field(
        default="16Gi", description="Total memory limits allowed"
    )
    pods: Optional[str] = Field(
        default="20", description="Maximum number of pods"
    )
    services: Optional[str] = Field(
        default="10", description="Maximum number of services"
    )
    persistentvolumeclaims: Optional[str] = Field(
        default="10", description="Maximum number of PVCs"
    )
    requests_storage: Optional[str] = Field(
        default=None, description="Total storage requests allowed"
    )


class LimitRangeConfig(CRDSpec):
    """ Default limit range for containers in a project namespace. """

    default_cpu: Optional[str] = Field(
        default="500m", description="Default CPU limit per container"
    )
    default_memory: Optional[str] = Field(
        default="1Gi", description="Default memory limit per container"
    )
    default_request_cpu: Optional[str] = Field(
        default="100m", description="Default CPU request per container"
    )
    default_request_memory: Optional[str] = Field(
        default="256Mi", description="Default memory request per container"
    )


class AppConfig(CRDSpec):
    """Application configuration within a project."""

    name: str = Field(..., description="Application name")
    type: str = Field(..., description="Application type (e.g., jupyterhub, vdi)")
    url: str = Field(..., description="URL endpoint for the application")
    config: Dict[str, Any] = Field(
        default_factory=dict, description="Application-specific configuration"
    )

class StorageConfig(CRDSpec):
    """Storage configuration for a project namespace."""

    storage_class: Optional[str] = Field(
        default=None, description="StorageClass to use for PVCs"
    )
    default_vdi_size: Optional[str] = Field(
        default=None, description="Default PVC size for VDI instances"
    )
    default_notebook_size: Optional[str] = Field(
        default=None, description="Default PVC size for Jupyter notebooks"
    )


class TolerationConfig(CRDSpec):
    """Kubernetes toleration configuration."""

    key: str = Field(..., description="Toleration key")
    operator: str = Field(default="Equal", description="Operator (Equal or Exists)")
    value: Optional[str] = Field(default=None, description="Toleration value")
    effect: Optional[str] = Field(default=None, description="Effect (NoSchedule, PreferNoSchedule, NoExecute)")
    toleration_seconds: Optional[int] = Field(default=None, description="Toleration seconds for NoExecute")


class ResourceRequirementsConfig(CRDSpec):
    """Resource requests and limits configuration."""

    requests_cpu: Optional[str] = Field(default=None, description="CPU request")
    requests_memory: Optional[str] = Field(default=None, description="Memory request")
    limits_cpu: Optional[str] = Field(default=None, description="CPU limit")
    limits_memory: Optional[str] = Field(default=None, description="Memory limit")


class SchedulingConfig(CRDSpec):
    """Scheduling configuration for workspaces in a project."""

    node_selector: Dict[str, str] = Field(
        default_factory=dict, description="Node selector labels"
    )
    tolerations: List[TolerationConfig] = Field(
        default_factory=list, description="Pod tolerations"
    )
    affinity: Optional[Dict[str, Any]] = Field(
        default=None, description="Pod affinity/anti-affinity rules"
    )
    resources: Optional[ResourceRequirementsConfig] = Field(
        default=None, description="Default resource requests/limits for workspaces"
    )
    labels: Dict[str, str] = Field(
        default_factory=dict, description="Additional labels for workspace pods"
    )
    annotations: Dict[str, str] = Field(
        default_factory=dict, description="Additional annotations for workspace pods"
    )


class ProfileKubespawnerOverride(CRDSpec):
    """Kubespawner override configuration for profiles."""

    image: Optional[str] = Field(
        default=None, description="Container image for the profile"
    )
    env: Dict[str, Any] = Field(
        default_factory=dict, description="Environment variables for the profile"
    )

class ProfileConfig(CRDSpec):
    """Profile configuration for workspaces."""

    display_name: str = Field(..., description="Human-readable profile name")
    description: Optional[str] = Field(
        default=None, description="Profile description"
    )
    slug: str = Field(..., description="URL-safe profile identifier")
    kubespawner_override: Optional[ProfileKubespawnerOverride] = Field(
        default=None, description="Kubespawner-specific overrides"
    )

@CRDRegistry.register("research.karectl.io", "v1alpha1", "Project", "projects")
class ProjectSpec(CRDSpec):
    """Project CRD specification for research projects."""

    description: str = Field(..., description="Human-readable project description")
    apps: List[AppConfig] = Field(
        default_factory=list,
        description="List of applications available in this project",
    )
    profiles: List[ProfileConfig] = Field(
        default_factory=list,
        description="List of workspace profiles for this project",
    )
    resource_quota: Optional[ResourceQuotaConfig] = Field(
        default=None,
        description="Resource quota for the project namespace",
    )
    limit_range: Optional[LimitRangeConfig] = Field(
        default=None,
        description="Default limits for containers in the project namespace",
    )
    storage: Optional[StorageConfig] = Field(
        default=None,
        description="Storage configuration for the project",
    )
    scheduling: Optional[SchedulingConfig] = Field(
        default=None,
        description="Scheduling configuration for workspace pods",
    )
