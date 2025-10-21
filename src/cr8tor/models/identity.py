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
    attributes: Dict[str, Any] = Field(
        default_factory=dict, description="Additional client attributes"
    )

class AppConfig(CRDSpec):
    """Application configuration within a project."""

    name: str = Field(..., description="Application name")
    type: str = Field(..., description="Application type (e.g., jupyterhub, vdi)")
    url: str = Field(..., description="URL endpoint for the application")
    config: Dict[str, Any] = Field(
        default_factory=dict, description="Application-specific configuration"
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
