"""Module that provides the identity handler for the operator."""

import kopf
from kubernetes import client, config
from cr8tor.services.user_manager import sync_keycloak_user, delete_keycloak_user
from cr8tor.services.group_manager import sync_keycloak_group, delete_keycloak_group
from cr8tor.services.client_manager import sync_keycloak_client, delete_keycloak_client
from cr8tor.services.gitea_manager import sync_gitea_oauth_source, delete_gitea_oauth_source
from cr8tor.services.gitea_org_manager import sync_project_to_gitea, delete_project_from_gitea
from cr8tor.services.client import ensure_realm_exists


# https://www.reddit.com/r/kubernetes/comments/1dge5qk/writing_an_operator_with_kopf/
# Note: Startup configuration is now handled in main.py to avoid conflicts


@kopf.on.create("identity.karectl.io", "v1alpha1", "user")
@kopf.on.update("identity.karectl.io", "v1alpha1", "user")
def user_create_update(body, spec, meta, status, patch, **kwargs):
    """Operator function for creating and updating users."""
    username = spec["username"]
    ensure_realm_exists()
    result = sync_keycloak_user(username, spec)

    if result and "password" in result:
        patch.status["initialPassword"] = result["password"]

    kopf.info(meta, reason="UserSynced", message=f"User {username} synced.")


@kopf.on.delete("identity.karectl.io", "v1alpha1", "user")
def user_delete(body, spec, meta, **kwargs):
    """Operator function for deleting users."""
    username = spec["username"]
    delete_keycloak_user(username)
    kopf.info(meta, reason="UserDeleted", message=f"User {username} deleted.")


@kopf.on.create("identity.karectl.io", "v1alpha1", "group")
@kopf.on.update("identity.karectl.io", "v1alpha1", "group")
def group_create_update(body, spec, meta, **kwargs):
    """Operator function for creating and updating groups."""
    groupname = meta["name"]
    ensure_realm_exists()
    sync_keycloak_group(groupname, spec)
    kopf.info(meta, reason="GroupSynced", message=f"Group {groupname} synced.")


@kopf.on.delete("identity.karectl.io", "v1alpha1", "group")
def group_delete(body, spec, meta, **kwargs):
    """Operator function for deleting groups."""
    groupname = meta["name"]
    delete_keycloak_group(groupname)
    kopf.info(meta, reason="GroupDeleted", message=f"Group {groupname} deleted.")


@kopf.on.create("identity.karectl.io", "v1alpha1", "keycloakclient")
@kopf.on.update("identity.karectl.io", "v1alpha1", "keycloakclient")
@kopf.on.resume("identity.karectl.io", "v1alpha1", "keycloakclient")
def client_create_update(body, spec, meta, **kwargs):
    """Handle KeycloakClient create, update, and resume (on operator restart).
    """
    client_id = spec["clientId"]
    namespace = meta.get("namespace", "keycloak")
    sync_keycloak_client(client_id, spec, namespace=namespace)
    kopf.info(
        meta, reason="ClientSynced", message=f"Keycloak client {client_id} synced."
    )


@kopf.on.delete("identity.karectl.io", "v1alpha1", "keycloakclient")
def client_delete(body, spec, meta, **kwargs):
    client_id = spec["clientId"]
    delete_keycloak_client(client_id)
    kopf.info(
        meta, reason="ClientDeleted", message=f"Keycloak client {client_id} deleted."
    )

@kopf.on.create("research.karectl.io", "v1alpha1", "project")
@kopf.on.update("research.karectl.io", "v1alpha1", "project")
@kopf.on.resume("research.karectl.io", "v1alpha1", "project")
def project_create_update(body, spec, meta, **kwargs):
    """Handle Project resource creation, updates, and resume."""
    project_name = meta["name"]

    description = spec.get("description", "")
    apps = spec.get("apps", [])
    profiles = spec.get("profiles", [])

    # Extract gitea config from apps
    gitea_app = next((app for app in apps if app.get("type") == "gitea"), None)
    gitea_config = gitea_app.get("config") if gitea_app else None

    # Validate project
    kopf.info(
        meta,
        reason="ProjectSynced",
        message=f"Project {project_name} validated ({len(apps)} apps, {len(profiles)} profiles)",
    )

    # Sync to Gitea if enabled
    if gitea_config and gitea_config.get("enabled", False):
        try:
            try:
                config.load_incluster_config()
            except config.ConfigException:
                config.load_kube_config()

            # Get all Users
            custom_api = client.CustomObjectsApi()
            users = custom_api.list_cluster_custom_object(
                group="identity.karectl.io",
                version="v1alpha1",
                plural="users"
            )
            all_users = users.get("items", [])

            # Sync to Gitea
            sync_project_to_gitea(project_name, spec, all_users)

            kopf.info(
                meta,
                reason="GiteaSynced",
                message=f"Project {project_name} synced to Gitea"
            )
        except Exception as e:
            kopf.exception(
                meta,
                reason="GiteaSyncFailed",
                message=f"Failed to sync project {project_name} to Gitea: {e}"
            )
            raise


@kopf.on.delete("research.karectl.io", "v1alpha1", "project")
def project_delete(body, spec, meta, **kwargs):
    """Handle Project resource deletion."""
    project_name = meta["name"]

    # Extract gitea config
    apps = spec.get("apps", [])
    gitea_app = next((app for app in apps if app.get("type") == "gitea"), None)
    gitea_config = gitea_app.get("config") if gitea_app else None

    # Delete Gitea organisation
    if gitea_config and gitea_config.get("enabled", False):
        try:
            delete_project_from_gitea(project_name)
            kopf.info(
                meta,
                reason="GiteaDeleted",
                message=f"Deleted Gitea for project {project_name}"
            )
        except Exception as e:
            kopf.warning(
                meta,
                reason="GiteaDeleteFailed",
                message=f"Failed to delete Gitea: {e}"
            )

    kopf.info(
        meta,
        reason="ProjectDeleted",
        message=f"Project {project_name} cleanup completed",
    )


@kopf.on.create("identity.karectl.io", "v1alpha1", "giteaclient")
@kopf.on.update("identity.karectl.io", "v1alpha1", "giteaclient")
@kopf.on.resume("identity.karectl.io", "v1alpha1", "giteaclient")
def gitea_client_create_update(body, spec, meta, **kwargs):
    """Handle GiteaClient create, update, and resume (on operator restart)."""
    source_name = spec["name"]
    namespace = meta.get("namespace", "gitea")

    try:
        sync_gitea_oauth_source(source_name, spec, namespace=namespace)
        kopf.info(
            meta,
            reason="GiteaClientSynced",
            message=f"Gitea OAuth source '{source_name}' synced successfully"
        )
    except Exception as e:
        kopf.exception(
            meta,
            reason="GiteaClientSyncFailed",
            message=f"Failed to sync Gitea OAuth source '{source_name}': {e}"
        )
        raise


@kopf.on.delete("identity.karectl.io", "v1alpha1", "giteaclient")
def gitea_client_delete(body, spec, meta, **kwargs):
    """Handle GiteaClient deletion."""
    source_name = spec["name"]
    gitea_url = spec["giteaUrl"]
    admin_secret_ref = spec["adminSecretRef"]
    namespace = meta.get("namespace", "gitea")

    try:
        delete_gitea_oauth_source(
            source_name, gitea_url, admin_secret_ref, namespace=namespace
        )
        kopf.info(
            meta,
            reason="GiteaClientDeleted",
            message=f"Gitea OAuth source '{source_name}' deleted successfully"
        )
    except Exception as e:
        kopf.exception(
            meta,
            reason="GiteaClientDeleteFailed",
            message=f"Failed to delete Gitea OAuth source '{source_name}': {e}"
        )
        raise
