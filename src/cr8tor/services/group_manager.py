import logging

from keycloak.exceptions import KeycloakGetError, KeycloakDeleteError, KeycloakPutError
from .client import get_client

logger = logging.getLogger(__name__)


def sync_keycloak_group(groupname, spec):
    """Sync a group to Keycloak."""
    keycloak_client = get_client()
    description = spec.get("description", "")
    members = spec.get("members", [])
    groups = keycloak_client.get_groups()
    group = [group for group in groups if group["name"] == groupname]

    attributes = {"description": [description]}

    if group:
        group_id = group[0]["id"]
        keycloak_client.update_group(
            group_id=group_id, payload={"name": groupname, "attributes": attributes}
        )
    else:
        group_id = keycloak_client.create_group(
            {"name": groupname, "attributes": attributes}
        )

    desired_usernames = set(members)

    # Remove users no longer in spec (project access revocation).
    try:
        current_kc_members = keycloak_client.get_group_members(group_id)
    except KeycloakGetError as e:
        logger.warning(f"Could not fetch current members of {groupname}: {e}")
        current_kc_members = []

    for kc_member in current_kc_members:
        if kc_member.get("username") not in desired_usernames:
            member_id = kc_member["id"]
            try:
                keycloak_client.group_user_remove(member_id, group_id)
                logger.info(f"Removed {kc_member.get('username')} (user_id={member_id}) from {groupname} (group_id={group_id})")
            except KeycloakDeleteError as e:
                logger.warning(f"Could not remove {kc_member.get('username')} (user_id={member_id}) from {groupname} (group_id={group_id}): {e}")

    for username in members:
        try:
            user_id = keycloak_client.get_user_id(username)
            keycloak_client.group_user_add(user_id, group_id)
        except KeycloakGetError as e:
            logger.warning(f"Could not resolve user {username} for group {groupname} (group_id={group_id}): {e}")
        except KeycloakPutError as e:
            logger.warning(f"Could not add {username} to {groupname} (group_id={group_id}): {e}")

    logger.info(f"Synced group {groupname}")


def delete_keycloak_group(groupname):
    """Delete a group from Keycloak."""
    keycloak_client = get_client()
    groups = keycloak_client.get_groups()
    group = [group for group in groups if group["name"] == groupname]

    if group:
        keycloak_client.delete_group(group[0]["id"])
        logger.info(f"Deleted group {groupname}")
    else:
        logger.warning(f"Group {groupname} not found")
