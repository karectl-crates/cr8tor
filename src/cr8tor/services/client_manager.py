import os
import re
import base64
from kubernetes import client, config
from .client import get_client


def expand_env_vars(value):
    """Expand environment variables in the format ${VAR_NAME}"""
    if not isinstance(value, str):
        return value

    def replacer(match):
        var_name = match.group(1)
        env_value = os.environ.get(var_name)
        if env_value is None:
            print(f"Warning: Environment variable '{var_name}' not found, keeping placeholder")
            return match.group(0)  # Return original ${VAR_NAME} if not found
        return env_value

    return re.sub(r'\$\{([^}]+)\}', replacer, value)


def assign_client_scopes(kc, client_uuid, scope_names, scope_type="default"):
    """Assign client scopes to a client"""
    available_scopes = kc.get_client_scopes()
    realm_name = kc.connection.realm_name

    success_count = 0
    failed_scopes = []

    for scope_name in scope_names:
        scope_obj = next(
            (s for s in available_scopes if s["name"] == scope_name), None
        )

        if scope_obj:
            try:
                payload = {
                    "realm": realm_name,
                    "client": client_uuid,
                    "clientScopeId": scope_obj["id"]
                }
                if scope_type == "default":
                    kc.add_client_default_client_scope(client_uuid, scope_obj["id"], payload)
                else:
                    kc.add_client_optional_client_scope(client_uuid, scope_obj["id"], payload)
                print(f"Assigned {scope_type} scope '{scope_name}' to client")
                success_count += 1
            except Exception as scope_error:
                print(f"Error assigning scope '{scope_name}': {scope_error}")
                failed_scopes.append(scope_name)
        else:
            print(f"Warning: Scope '{scope_name}' not found in realm")
            failed_scopes.append(scope_name)

    print(f"Scope assignment complete: {success_count}/{len(scope_names)} successful")
    if failed_scopes:
        print(f"Failed scopes: {failed_scopes}")


def create_protocol_mappers(kc, client_uuid, mappers):
    """Create or update protocol mappers for a client"""
    if not mappers:
        print("No protocol mappers to configure")
        return

    print(f"Attempting to configure {len(mappers)} protocol mappers")
    success_count = 0
    failed_mappers = []

    # Get existing mappers
    try:
        existing_mappers = kc.get_mappers_from_client(client_uuid)
        existing_mapper_dict = {m["name"]: m for m in existing_mappers}
    except Exception as e:
        print(f"Error getting existing mappers: {e}")
        existing_mapper_dict = {}

    for mapper in mappers:
        try:
            mapper_config = mapper.get("config", {})
            config_str = {k: str(v) for k, v in mapper_config.items()} if isinstance(mapper_config, dict) else {}
            mapper_payload = {
                "name": mapper["name"],
                "protocol": mapper.get("protocol", "openid-connect"),
                "protocolMapper": mapper.get("protocol_mapper", mapper.get("protocolMapper", "")),
                "consentRequired": mapper.get("consent_required", mapper.get("consentRequired", False)),
                "config": config_str,
            }

            mapper_name = mapper["name"]
            if mapper_name in existing_mapper_dict:
                # Delete and recreate mapper
                try:
                    existing_mapper_id = existing_mapper_dict[mapper_name]["id"]
                    kc.remove_client_mapper(client_uuid, existing_mapper_id)
                    kc.add_mapper_to_client(client_uuid, mapper_payload)
                    print(f"Recreated protocol mapper '{mapper_name}'")
                    success_count += 1
                except Exception as recreate_error:
                    print(f"Error updating mapper '{mapper_name}': {recreate_error}")
                    failed_mappers.append(mapper_name)
            else:
                # Create new mapper
                try:
                    kc.add_mapper_to_client(client_uuid, mapper_payload)
                    print(f"Created protocol mapper '{mapper_name}'")
                    success_count += 1
                except Exception as create_error:
                    print(f"Error creating mapper '{mapper_name}': {create_error}")
                    failed_mappers.append(mapper_name)

        except Exception as e:
            print(f"Error configuring mapper '{mapper.get('name', 'unknown')}': {e}")
            failed_mappers.append(mapper.get("name", "unknown"))

    print(f"Protocol mapper configuration complete: {success_count}/{len(mappers)} successful")
    if failed_mappers:
        print(f"Failed mappers: {failed_mappers}")


def sync_keycloak_client(client_id, spec, namespace=None):
    """ Sync a Keycloak client."""
    kc = get_client()
    clients = kc.get_clients()
    client_obj = next((c for c in clients if c["clientId"] == client_id), None)

    # Support both snake_case (LinkML) and camelCase (legacy) field names
    def get_field(snake, camel, default=None):
        return spec.get(snake, spec.get(camel, default))

    secret_value = None
    secret_ref = get_field("secret_ref", "secretRef")
    if secret_ref:
        try:
            config.load_incluster_config()
            v1 = client.CoreV1Api()
            secret_namespace = namespace or os.environ.get("KUBERNETES_NAMESPACE", "keycloak")

            secret = v1.read_namespaced_secret(
                name=secret_ref["name"], namespace=secret_namespace
            )
            secret_key = secret_ref.get("key", "client-secret")
            secret_value = base64.b64decode(secret.data[secret_key]).decode("utf-8")
            print(f"Retrieved secret for {client_id} from {secret_ref['name']} in namespace {secret_namespace}")

        except Exception as e:
            print(f"Error reading secretRef for {client_id}: {e}")
            secret_value = spec.get("secret")
    elif "secret" in spec:
        secret_value = expand_env_vars(spec["secret"])
        print(f"Expanded secret value for {client_id}")

    if not secret_value:
        print(f"No secret found for client {client_id}")
        return

    payload = {
        "clientId": get_field("client_id", "clientId"),
        "name": spec.get("name"),
        "enabled": spec.get("enabled", True),
        "secret": secret_value,
        "redirectUris": get_field("redirect_uris", "redirectUris", []),
        "webOrigins": get_field("web_origins", "webOrigins", []),
        "protocol": "openid-connect",
        "publicClient": False,
        "standardFlowEnabled": True,
        "directAccessGrantsEnabled": True,
    }

    try:
        if client_obj:
            kc.update_client(client_obj["id"], payload)
            client_uuid = client_obj["id"]
            print(f"Updated Keycloak client {client_id}")
        else:
            client_uuid = kc.create_client(payload)
            print(f"Created Keycloak client {client_id}")

        # Handle client scope assignments
        default_scopes = get_field("default_client_scopes", "defaultClientScopes")
        if default_scopes:
            assign_client_scopes(kc, client_uuid, default_scopes, scope_type="default")

        optional_scopes = get_field("optional_client_scopes", "optionalClientScopes")
        if optional_scopes:
            assign_client_scopes(kc, client_uuid, optional_scopes, scope_type="optional")

        # Handle protocol mappers
        mappers = get_field("protocol_mappers", "protocolMappers")
        if mappers:
            create_protocol_mappers(kc, client_uuid, mappers)

    except Exception as e:
        print(f"Error syncing client {client_id}: {e}")
        raise


def delete_keycloak_client(client_id):
    """Delete a client from keycloak."""
    kc = get_client()
    clients = kc.get_clients()
    client_obj = next((c for c in clients if c["clientId"] == client_id), None)

    if client_obj:
        kc.delete_client(client_obj["id"])
        print(f"Deleted Keycloak client {client_id}")
    else:
        print(f"Client {client_id} not found for deletion")
