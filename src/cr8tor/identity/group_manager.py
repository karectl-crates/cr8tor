from .client import get_client


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

    for username in members:
        try:
            user_id = keycloak_client.get_user_id(username)
            keycloak_client.group_user_add(user_id, group_id)
        except Exception as e:
            print(f"Could not add {username} to {groupname}: {e}")

    print(f"Synced group {groupname}")


def delete_keycloak_group(groupname):
    """Delete a group from Keycloak."""
    keycloak_client = get_client()
    groups = keycloak_client.get_groups()
    group = [group for group in groups if group["name"] == groupname]

    if group:
        keycloak_client.delete_group(group[0]["id"])
        print(f"Deleted group {groupname}")
    else:
        print(f"Group {groupname} not found")
