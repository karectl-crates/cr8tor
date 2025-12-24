""" Service for managing Gitea OAuth sources.
"""

import os
import base64
import requests
from kubernetes import client, config


def get_gitea_admin_credentials(secret_ref, namespace):
    """ Get admin credentials from secret.

    Args:
        secret_ref: Dict with 'name', 'usernameKey', and 'passwordKey'
        namespace: Kubernetes namespace containing the secret
    """
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()

    v1 = client.CoreV1Api()
    secret_name = secret_ref["name"]
    username_key = secret_ref.get("usernameKey", "username")
    password_key = secret_ref.get("passwordKey", "password")

    secret = v1.read_namespaced_secret(name=secret_name, namespace=namespace)
    username = base64.b64decode(secret.data[username_key]).decode("utf-8")
    password = base64.b64decode(secret.data[password_key]).decode("utf-8")

    return username, password


def get_oidc_credentials(secret_ref, namespace):
    """Get OIDC credentials from secret.

    Args:
        secret_ref: Dict with 'name', 'clientIdKey', and 'clientSecretKey'
        namespace: Kubernetes namespace containing the secrets
    """
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()

    v1 = client.CoreV1Api()
    secret_name = secret_ref["name"]
    client_id_key = secret_ref.get("clientIdKey", "client-id")
    client_secret_key = secret_ref.get("clientSecretKey", "client-secret")

    secret = v1.read_namespaced_secret(name=secret_name, namespace=namespace)
    client_id = base64.b64decode(secret.data[client_id_key]).decode("utf-8")
    client_secret = base64.b64decode(secret.data[client_secret_key]).decode("utf-8")

    return client_id, client_secret


def wait_for_gitea(gitea_url, timeout=300):
    """Wait for gitea to become available.

    Args:
        gitea_url: Base URL of gitea instance
        timeout: Maximum time to wait in seconds
    """
    import time

    version_url = f"{gitea_url}/api/v1/version"
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            response = requests.get(version_url, timeout=5)
            if response.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            pass

        time.sleep(5)

    print(f"Timeout waiting for gitea at {gitea_url}")
    return False


def get_existing_oauth_source(gitea_url, admin_username, admin_password, source_name):
    """Get existing OAuth source from gitea.

    Args:
        gitea_url: Base URL of gitea instance
        admin_username: gitea admin username
        admin_password: gitea admin password
        source_name: Name of the OAuth source
    """
    auth_url = f"{gitea_url}/api/v1/admin/auth"

    try:
        response = requests.get(
            auth_url,
            auth=(admin_username, admin_password),
            timeout=10
        )
        response.raise_for_status()
        auth_sources = response.json()
        for source in auth_sources:
            if source.get("name") == source_name:
                return source

        return None

    except requests.exceptions.RequestException as e:
        print(f"Error fetching OAuth sources from gitea: {e}")
        return None


def sync_gitea_oauth_source(source_name, spec, namespace=None):
    """Create or update a gitea OAuth source.

    Args:
        source_name: Name of the OAuth source in gitea
        spec: GiteaClient spec from CRD
        namespace: namespace (defaults from metadata)
    """
    gitea_url = spec["giteaUrl"]
    keycloak_url = spec["keycloakUrl"]
    realm = spec.get("realm", "karectl-app")
    admin_secret_ref = spec["adminSecretRef"]
    oidc_secret_ref = spec["oidcSecretRef"]
    scopes = spec.get("scopes", ["openid", "profile", "email", "groups"])
    group_claim_name = spec.get("groupClaimName", "groups")
    skip_local_2fa = spec.get("skipLocalTwoFA", False)
    enabled = spec.get("enabled", True)

    # Default namespace if not provided
    if not namespace:
        namespace = os.environ.get("KUBERNETES_NAMESPACE", "gitea")

    print(f"Syncing gitea OAuth source '{source_name}' in namespace {namespace}")

    # Wait for gitea to be ready
    if not wait_for_gitea(gitea_url):
        raise Exception(f"Gitea not available at {gitea_url}")

    # Get cred from secrets
    try:
        admin_username, admin_password = get_gitea_admin_credentials(
            admin_secret_ref, namespace
        )
        client_id, client_secret = get_oidc_credentials(
            oidc_secret_ref, namespace
        )
    except Exception as e:
        print(f"Error retrieving credentials: {e}")
        raise

    # Check if OAuth source already exists
    existing_source = get_existing_oauth_source(
        gitea_url, admin_username, admin_password, source_name
    )

    # Build OAuth source configuration
    openid_config_url = f"{keycloak_url}/realms/{realm}/.well-known/openid-configuration"
    oauth_config = {
        "type": "oauth2",
        "name": source_name,
        "cfg": {
            "provider": "openidConnect",
            "clientID": client_id,
            "clientSecret": client_secret,
            "autoDiscoverURL": openid_config_url,
            "scopes": scopes,
            "groupClaimName": group_claim_name,
            "skipLocalTwoFA": skip_local_2fa
        }
    }

    # Create or update OAuth source
    try:
        if existing_source:
            source_id = existing_source["id"]
            update_url = f"{gitea_url}/api/v1/admin/auth/{source_id}"

            response = requests.patch(
                update_url,
                json=oauth_config,
                auth=(admin_username, admin_password),
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            response.raise_for_status()
            print(f"Updated Gitea OAuth source '{source_name}' (ID: {source_id})")

        else:
            # Create new source
            create_url = f"{gitea_url}/api/v1/admin/auth"

            response = requests.post(
                create_url,
                json=oauth_config,
                auth=(admin_username, admin_password),
                headers={"Content-Type": "application/json"},
                timeout=10
            )

            if response.status_code in [200, 201]:
                print(f"Created Gitea OAuth source '{source_name}'")
            else:
                print(f"Failed to create OAuth source. HTTP {response.status_code}: {response.text}")
                response.raise_for_status()

    except requests.exceptions.RequestException as e:
        print(f"Error syncing Gitea OAuth source: {e}")
        raise


def delete_gitea_oauth_source(source_name, gitea_url, admin_secret_ref, namespace=None):
    """Delete a gitea OAuth source.

    Args:
        source_name: Name of the OAuth source in gitea
        gitea_url: Base URL of gitea instance
        admin_secret_ref: Reference to admin credentials secret
        namespace: namespace
    """
    if not namespace:
        namespace = os.environ.get("KUBERNETES_NAMESPACE", "gitea")

    print(f"Deleting gitea OAuth source '{source_name}'")

    try:
        # Get admin credentials
        admin_username, admin_password = get_gitea_admin_credentials(
            admin_secret_ref, namespace
        )

        # Get OAuth source
        existing_source = get_existing_oauth_source(
            gitea_url, admin_username, admin_password, source_name
        )

        if not existing_source:
            print(f"OAuth source '{source_name}' not found, nothing to delete")
            return

        # Delete the source
        source_id = existing_source["id"]
        delete_url = f"{gitea_url}/api/v1/admin/auth/{source_id}"

        response = requests.delete(
            delete_url,
            auth=(admin_username, admin_password),
            timeout=10
        )
        response.raise_for_status()

        print(f"Deleted Gitea OAuth source '{source_name}' (ID: {source_id})")

    except Exception as e:
        print(f"Error deleting Gitea OAuth source: {e}")
        raise
