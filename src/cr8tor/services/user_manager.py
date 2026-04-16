from datetime import date
from keycloak.exceptions import KeycloakGetError, KeycloakPutError, KeycloakDeleteError
from .client import get_client
from .utils import generate_temp_password, write_passwords


def _parse_date(value):
    """Parse a date based on format"""
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _resolve_enabled(spec):
    """ Return False if start_date is in the future or expiry_date has passed"""
    enabled = spec.get("enabled", True)
    today = date.today()
    start_date = spec.get("start_date")
    expiry_date = spec.get("expiry_date")

    if start_date:
        if today < _parse_date(start_date):
            return False

    if expiry_date:
        if today > _parse_date(expiry_date):
            return False

    return enabled


def sync_keycloak_user(username, spec):
    """Sync a user to Keycloak."""
    keycloak_client = get_client()
    email = spec.get("email")
    password = spec.get("password")
    first_name = spec.get("given_name", "")
    last_name = spec.get("family_name", "")
    user_created = False
    temp_password = None

    enabled = _resolve_enabled(spec)
    if enabled != spec.get("enabled", True):
        print(f"Account {username} disabled by policy (start_date={spec.get('start_date')}, expiry_date={spec.get('expiry_date')})")

    attributes = {}
    if spec.get("start_date"):
        attributes["start_date"] = [str(_parse_date(spec["start_date"]))]
    if spec.get("expiry_date"):
        attributes["expiry_date"] = [str(_parse_date(spec["expiry_date"]))]

    user_payload = {
        "username": username,
        "email": email,
        "enabled": enabled,
        "firstName": first_name,
        "lastName": last_name,
    }
    if attributes:
        user_payload["attributes"] = attributes

    # Try to get the user first
    try:
        user_id = keycloak_client.get_user_id(username)
        try:
            # Try updating the user
            keycloak_client.update_user(user_id, user_payload)
        except KeycloakPutError as err:
            if "User not found" in str(err):
                print(f"[INFO] User {username} not found on update, creating instead.")
                user_id = keycloak_client.create_user(user_payload)
                user_created = True
            else:
                raise

    except KeycloakGetError:
        # If user does not exist, create them
        print(f"[INFO] User {username} not found, creating.")
        user_id = keycloak_client.create_user(user_payload)
        user_created = True

    # Always get the actual user_id (in case it was just created)
    user_id = keycloak_client.get_user_id(username)

    # Set a temp password if the user was just created
    if user_created:
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
