import os
from keycloak import KeycloakAdmin
from keycloak.exceptions import KeycloakGetError


def get_client():
    """ Get a Keycloak client.
    """
    return KeycloakAdmin(
        server_url=os.environ.get("KEYCLOAK_URL", "http://keycloak.keycloak/"),
        username=os.environ["KEYCLOAK_ADMIN"],
        password=os.environ["KEYCLOAK_ADMIN_PASSWORD"],
        realm_name=os.environ.get("KEYCLOAK_REALM", "karectl-app"),
        user_realm_name="master",
        verify=True,
    )


def ensure_realm_exists(realm_name=None, display_name=None):
    """ Ensure a realm exists in Keycloak.
    """
    realm_name = realm_name or os.environ.get("KEYCLOAK_REALM", "karectl-app")
    admin_client = KeycloakAdmin(
        server_url=os.environ.get("KEYCLOAK_URL", "http://keycloak.keycloak/"),
        username=os.environ["KEYCLOAK_ADMIN"],
        password=os.environ["KEYCLOAK_ADMIN_PASSWORD"],
        realm_name="master",
        user_realm_name="master",
        verify=True,
    )

    realms = admin_client.get_realms()
    if any(r['realm'] == realm_name for r in realms):
        return 

    payload = {
        "realm": realm_name,
        "displayName": display_name or realm_name,
        "enabled": True,
        "loginWithEmailAllowed": True,
        "duplicateEmailsAllowed": False,
        "resetPasswordAllowed": True,
        "verifyEmail": False,
        "requiredCredentials": ["password"],
        "defaultRoles": ["offline_access", "uma_authorization", "user"],
    }
    admin_client.create_realm(payload=payload)
    print(f"[Keycloak] Realm '{realm_name}' created.")