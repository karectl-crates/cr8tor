from keycloak.exceptions import KeycloakGetError, KeycloakPutError, KeycloakDeleteError
from .client import get_client
from .utils import generate_temp_password, write_passwords


def sync_keycloak_user(username, spec, force_password_reset=False):
    """Sync a user to Keycloak."""
    keycloak_client = get_client()
    email = spec.get("email")
    enabled = spec.get("enabled", True)
    password = spec.get("password")
    first_name = spec.get("given_name", "")
    last_name = spec.get("family_name", "")
    user_created = False
    temp_password = None

    attributes = {}
    for key in ("expiry_date", "start_date", "affiliation"):
        value = spec.get(key)
        if value:
            attributes[key] = [str(value)]

    user_payload = {
        "username": username,
        "email": email,
        "enabled": enabled,
        "firstName": first_name,
        "lastName": last_name,
        "attributes": attributes,
    }

    # Try to get the user first
    user_id = keycloak_client.get_user_id(username)

    if user_id is None:
        print(f"[INFO] User {username} not found, creating.")
        user_id = keycloak_client.create_user(user_payload)
        user_created = True
    else:
        try:
            # Preserve existing requiredActions
            existing = keycloak_client.get_user(user_id)
            payload = {**user_payload, "requiredActions": existing.get("requiredActions", [])}
            keycloak_client.update_user(user_id, payload)
        except KeycloakPutError as err:
            if "User not found" in str(err):
                print(f"[INFO] User {username} not found on update, creating instead.")
                user_id = keycloak_client.create_user(user_payload)
                user_created = True
            else:
                raise

    # Self-heal: an existing account with zero credentials needs a password just like a new one.
    needs_password = user_created or len(keycloak_client.get_credentials(user_id)) == 0
    if needs_password and not user_created:
        print(f"[INFO] User {username} exists with no credentials, setting password.")

    # Set a temp password if the user was just created or needs to be healed
    if needs_password or force_password_reset:
        if password:
            keycloak_client.set_user_password(user_id, password, temporary=True)
            temp_password = password
            print(f"[INFO] Set password for {username} from spec")
        else:
            temp_password = generate_temp_password()
            keycloak_client.set_user_password(user_id, temp_password, temporary=True)
            write_passwords(username, temp_password)

    print(f"[INFO] Synced user {username} to Keycloak")

    return {"password": temp_password} if temp_password else {}


def delete_keycloak_user(username):
    """Delete a user from Keycloak."""
    keycloak_client = get_client()
    try:
        user_id = keycloak_client.get_user_id(username)
        keycloak_client.delete_user(user_id)
        print(f"Deleted user {username}")
    except (KeycloakGetError, KeycloakDeleteError) as err:
        if "User not found" in str(err):
            print(f"User {username} already deleted. Treating as success.")
            return
        else:
            print(f"Error deleting user {username}: {err}")
            raise
