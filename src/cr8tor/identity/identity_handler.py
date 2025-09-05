"""Module that provides the identity handler for the operator."""

import kopf
from .user_manager import sync_keycloak_user, delete_keycloak_user
from .group_manager import sync_keycloak_group, delete_keycloak_group
from .client_manager import sync_keycloak_client, delete_keycloak_client
from .client import ensure_realm_exists


# https://www.reddit.com/r/kubernetes/comments/1dge5qk/writing_an_operator_with_kopf/
# Note: Startup configuration is now handled in main.py to avoid conflicts


@kopf.on.create("identity.karectl.io", "v1alpha1", "user")
@kopf.on.update("identity.karectl.io", "v1alpha1", "user")
def user_create_update(body, spec, meta, **kwargs):
    """Operator function for creating and updating users."""
    username = spec["username"]
    ensure_realm_exists()
    sync_keycloak_user(username, spec)
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
def client_create_update(body, spec, meta, **kwargs):
    client_id = spec["clientId"]
    sync_keycloak_client(client_id, spec)
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
