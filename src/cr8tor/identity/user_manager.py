from keycloak.exceptions import KeycloakGetError, KeycloakPutError
from .client import get_client
from .utils import generate_temp_password, write_passwords


def sync_keycloak_user(username, spec):
    """ Sync a user to Keycloak. 
    """
    keycloak_client = get_client()
    email = spec.get("email")
    enabled = spec.get("enabled", True)
    groups = spec.get("groups", [])
    user_created = False

    # Try to get the user first
    try:
        user_id = keycloak_client.get_user_id(username)
        try:
            # Try updating the user
            keycloak_client.update_user(
                user_id,
                {"email": email, "enabled": enabled, "username": username}
            )
        except KeycloakPutError as err:
            if "User not found" in str(err):
                print(f"[INFO] User {username} not found on update, creating instead.")
                user_id = keycloak_client.create_user(
                    {"username": username, "email": email, "enabled": enabled}
                )
                user_created = True
            else:
                raise

    except KeycloakGetError:
        # If user does not exist, create them
        print(f"[INFO] User {username} not found, creating.")
        user_id = keycloak_client.create_user(
            {"username": username, "email": email, "enabled": enabled}
        )
        user_created = True

    # Always get the actual user_id (in case it was just created)
    user_id = keycloak_client.get_user_id(username)

    for group in keycloak_client.get_user_groups(user_id):
        keycloak_client.group_user_remove(user_id, group['id'])

    for groupname in groups:
        group = [grp for grp in keycloak_client.get_groups() if grp['name'] == groupname]
        if group:
            keycloak_client.group_user_add(user_id, group[0]['id'])
        else:
            print(f"[WARN] Group {groupname} not found")

    # Set a temp password if the user was just created
    if user_created:
        temp_password = generate_temp_password()
        keycloak_client.set_user_password(user_id, temp_password, temporary=True)
        write_passwords(username, temp_password)

    print(f"[INFO] Synced user {username} to Keycloak")


def delete_keycloak_user(username):
    """ Delete a user from Keycloak.
    """
    keycloak_client = get_client()
    try:
        user_id = keycloak_client.get_user_id(username)
        keycloak_client.delete_user(user_id)
        print(f"Deleted user {username}")
    except KeycloakGetError as err:
        if "User not found" in str(err):
            print(f"User {username} already deleted. Treating as success.")
            return
        else:
            print(f"Error deleting user {username}: {err}")
            raise