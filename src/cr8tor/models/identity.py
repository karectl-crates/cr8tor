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


@CRDRegistry.register(
    "identity.karectl.io", "v1alpha1", "GiteaClient", "giteaclients"
)
class GiteaClientSpec(CRDSpec):
    """Gitea Client CRD specs."""

    name: str = Field(..., description="Name of the OAuth source in Gitea")
    giteaUrl: str = Field(..., description="Gitea API URL")
    keycloakUrl: str = Field(..., description="Keycloak base URL")
    realm: str = Field(default="karectl-app", description="Keycloak realm name")
    adminSecretRef: Dict[str, str] = Field(
        ...,
        description="Reference to secret"
    )
    oidcSecretRef: Dict[str, str] = Field(
        ...,
        description="Reference to oidc secret"
    )
    scopes: List[str] = Field(
        default_factory=lambda: ["openid", "profile", "email", "groups"],
        description="OAuth scopes to request"
    )
    groupClaimName: str = Field(
        default="groups",
        description="Claim name for group mapping"
    )
    skipLocalTwoFA: bool = Field(
        default=False,
        description="Skip local authentication for OAuth users"
    )
    enabled: bool = Field(default=True, description="Whether the OAuth source is enabled")


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


class GiteaTeamConfig(CRDSpec):
    """Gitea team configuration for a project."""

    name: str = Field(..., description="Team name (e.g., 'Admins', 'Analysts')")
    groups: List[str] = Field(
        ...,
        description="Keycloak groups that should be members of this team (e.g., ['asthma-admin'])"
    )
    permission: str = Field(
        default="read",
        description="Team permission level"
    )
    description: Optional[str] = Field(
        default=None,
        description="Team description"
    )


class GiteaRepositoryConfig(CRDSpec):
    """Gitea repository configuration."""

    name: str = Field(..., description="Repository name")
    description: Optional[str] = Field(
        default="",
        description="Repository description"
    )
    private: bool = Field(
        default=True,
        description="Whether repo is private"
    )
    auto_init: bool = Field(
        default=True,
        description="Initialise repo with README"
    )


class GiteaConfig(CRDSpec):
    """Gitea configuration for a project."""

    enabled: bool = Field(
        default=False,
        description="Whether to create Gitea organisation for this project"
    )
    visibility: str = Field(
        default="private",
        description="Organisation visibility: 'public', 'limited', or 'private'"
    )
    teams: List[GiteaTeamConfig] = Field(
        default_factory=list,
        description="Teams to create in the organisation"
    )
    repositories: List[GiteaRepositoryConfig] = Field(
        default_factory=list,
        description="Initial repositories to create"
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
    gitea: Optional[GiteaConfig] = Field(
        default=None,
        description="Gitea organisation config for this project"
    )
