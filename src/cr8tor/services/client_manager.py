import os
import base64
from kubernetes import client, config
from .client import get_client


def assign_client_scopes(kc, client_uuid, scope_names, scope_type="default"):
    """Assign client scopes to a client"""
    available_scopes = kc.get_client_scopes()

    success_count = 0
    failed_scopes = []

    for scope_name in scope_names:
        scope_obj = next(
            (s for s in available_scopes if s["name"] == scope_name), None
        )

        if scope_obj:
            try:
                if scope_type == "default":
                    kc.add_client_default_client_scope(client_uuid, scope_obj["id"])
                else:
                    kc.add_client_optional_client_scope(client_uuid, scope_obj["id"])
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
    """Create protocol mappers for a client"""
    if not mappers:
        print("No protocol mappers to configure")
        return

    print(f"Attempting to configure {len(mappers)} protocol mappers")
    success_count = 0
    failed_mappers = []

    for mapper in mappers:
        try:
            mapper_payload = {
                "name": mapper["name"],
                "protocol": mapper.get("protocol", "openid-connect"),
                "protocolMapper": mapper["protocolMapper"],
                "consentRequired": mapper.get("consentRequired", False),
                "config": mapper.get("config", {}),
            }

            existing_mappers = kc.get_client_protocol_mappers(client_uuid)
            existing_mapper = next(
                (m for m in existing_mappers if m["name"] == mapper["name"]), None
            )

            if existing_mapper:
                kc.update_client_protocol_mapper(
                    client_uuid, existing_mapper["id"], mapper_payload
                )
                print(f"Updated protocol mapper '{mapper['name']}'")
                success_count += 1
            else:
                kc.create_client_protocol_mapper(client_uuid, mapper_payload)
                print(f"Created protocol mapper '{mapper['name']}'")
                success_count += 1

        except Exception as e:
            print(f"Error configuring mapper '{mapper.get('name', 'unknown')}': {e}")
            failed_mappers.append(mapper.get("name", "unknown"))

    print(f"Protocol mapper configuration complete: {success_count}/{len(mappers)} successful")
    if failed_mappers:
        print(f"Failed mappers: {failed_mappers}")


def sync_keycloak_client(client_id, spec, namespace=None):
    kc = get_client()
    clients = kc.get_clients()
    client_obj = next((c for c in clients if c["clientId"] == client_id), None)

    secret_value = None
    if "secretRef" in spec:
        try:
            config.load_incluster_config()
            v1 = client.CoreV1Api()
            secret_namespace = namespace or os.environ.get("KUBERNETES_NAMESPACE", "keycloak")

            secret = v1.read_namespaced_secret(
                name=spec["secretRef"]["name"], namespace=secret_namespace
            )
            secret_key = spec["secretRef"].get("key", "client-secret")
            secret_value = base64.b64decode(secret.data[secret_key]).decode("utf-8")
            print(f"Retrieved secret for {client_id} from {spec['secretRef']['name']} in namespace {secret_namespace}")

        except Exception as e:
            print(f"Error reading secretRef for {client_id}: {e}")
            secret_value = spec.get("secret")
    elif "secret" in spec:
        secret_value = spec["secret"]

    if not secret_value:
        print(f"No secret found for client {client_id}")
        return

    payload = {
        "clientId": spec["clientId"],
        "name": spec.get("name"),
        "enabled": spec.get("enabled", True),
        "secret": secret_value,
        "redirectUris": spec.get("redirectUris", []),
        "webOrigins": spec.get("webOrigins", []),
        "protocol": "openid-connect",
        "publicClient": False,
        "standardFlowEnabled": True,
        "directAccessGrantsEnabled": True,
    }

    if "additionalConfig" in spec:
        payload.update(spec["additionalConfig"])

    try:
        if client_obj:
            kc.update_client(client_obj["id"], payload)
            client_uuid = client_obj["id"]
            print(f"Updated Keycloak client {client_id}")
        else:
            client_uuid = kc.create_client(payload)
            print(f"Created Keycloak client {client_id}")

        # Handle client scope assignments
        if "defaultClientScopes" in spec:
            assign_client_scopes(
                kc, client_uuid, spec["defaultClientScopes"], scope_type="default"
            )

        if "optionalClientScopes" in spec:
            assign_client_scopes(
                kc, client_uuid, spec["optionalClientScopes"], scope_type="optional"
            )

        # Handle protocol mappers
        if "protocolMappers" in spec:
            create_protocol_mappers(kc, client_uuid, spec["protocolMappers"])

    except Exception as e:
        print(f"Error syncing client {client_id}: {e}")
        raise


def delete_keycloak_client(client_id):
    kc = get_client()
    clients = kc.get_clients()
    client_obj = next((c for c in clients if c["clientId"] == client_id), None)

    if client_obj:
        kc.delete_client(client_obj["id"])
        print(f"Deleted Keycloak client {client_id}")
    else:
        print(f"Client {client_id} not found for deletion")
