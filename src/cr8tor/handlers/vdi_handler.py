"""VDI Handler for managing VDIInstance custom resources using Kopf."""

import logging

import kopf
import kubernetes
from kubernetes.client.exceptions import ApiException
import datetime
import yaml
import jinja2


def patch_kopf_filter():
    """Patch the specific filter method that's causing the TypeError"""
    from kopf._core.engines.posting import K8sPoster

    original_filter = K8sPoster.filter

    def patched_filter(self, record):
        try:
            settings = getattr(record, "settings", None)
            if (
                settings is not None
                and hasattr(settings, "posting")
                and hasattr(settings.posting, "level")
            ):
                if isinstance(settings.posting.level, str):
                    settings.posting.level = getattr(
                        logging, settings.posting.level.upper(), logging.INFO
                    )
            return original_filter(self, record)
        except Exception:
            return False

    K8sPoster.filter = patched_filter


patch_kopf_filter()


# Note: Startup configuration is now handled in main.py to avoid conflicts
# kubernetes.config is loaded in main.py


def ensure_init_scripts_configmap(namespace):
    """ Ensure vdi-init-scripts exists in the target namespace.
    """
    api = kubernetes.client.CoreV1Api()
    try:
        api.read_namespaced_config_map(name="vdi-init-scripts", namespace=namespace)
        print(f"vdi-init-scripts already exists in {namespace}", flush=True)
        return
    except ApiException as e:
        if e.status != 404:
            raise

    # Read the ConfigMap from the operator's namespace (cr8tor)
    try:
        source_cm = api.read_namespaced_config_map(name="vdi-init-scripts", namespace="cr8tor")
        new_cm = kubernetes.client.V1ConfigMap(
            metadata=kubernetes.client.V1ObjectMeta(
                name="vdi-init-scripts",
                namespace=namespace,
                labels={"managed-by": "cr8tor-operator"}
            ),
            data=source_cm.data
        )

        api.create_namespaced_config_map(namespace=namespace, body=new_cm)
        print(f"Created vdi-init-scripts in {namespace}", flush=True)
    except ApiException as e:
        print(f"Failed to copy vdi-init-scripts: {e}", flush=True)
        raise


def render_pod_template(
    name, namespace, user, project, image, connection, password, env_vars=None
):
    if env_vars is None:
        env_vars = []

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader("/app/templates"),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("vdi-pod-template.yaml.j2")
    return template.render(
        name=name,
        namespace=namespace,
        user=str(user),
        project=str(project),
        image=image,
        password=password,
        connection=connection,
        env_vars=env_vars,
    )


@kopf.on.create("karectl.io", "v1alpha1", "vdiinstances")
def create_vdi(spec, name, namespace, patch, body, **kwargs):
    from secrets import token_urlsafe

    patch.status["phase"] = "Pending"
    ensure_init_scripts_configmap(namespace)

    user = spec["user"]
    project = spec["project"]
    image = spec.get("image", "ghcr.io/alwin-k-thomas/vdi-mate:dev")
    connection = spec.get("connection", "rdp")
    env_vars = spec.get("env", [])

    print(f"Spec keys: {list(spec.keys())}", flush=True)
    print(f"Full spec: {spec}", flush=True)
    print(f"Environment variables from spec: {env_vars}", flush=True)

    # Generate and store password in CRD status
    status = body.get("status", {})
    if "password" not in status or not status["password"]:
        generated_password = token_urlsafe(24)
        patch.status["password"] = generated_password
        print(f"Generated VDI password for {name}", flush=True)
    else:
        generated_password = status["password"]
        print(f"Using existing VDI password for {name}", flush=True)

    print(f"About to patch status: {dict(patch.status)}", flush=True)

    pod_yaml = render_pod_template(
        name, namespace, user, project, image, connection, generated_password, env_vars
    )

    resources = list(yaml.safe_load_all(pod_yaml))
    api = kubernetes.client.CoreV1Api()

    owner_ref = {
        "apiVersion": "karectl.io/v1alpha1",
        "kind": "VDIInstance",
        "name": name,
        "uid": body["metadata"]["uid"],
        "controller": True,
        "blockOwnerDeletion": True,
    }
    created_resources = []
    for resource in resources:
        if resource is None:
            continue

        resource.setdefault("metadata", {}).setdefault("ownerReferences", []).append(
            owner_ref
        )

        try:
            if resource["kind"] == "Pod":
                api.create_namespaced_pod(namespace=namespace, body=resource)
                print(f"Created VDI pod: vdi-{name}", flush=True)
                created_resources.append(f"Pod:vdi-{name}")
            elif resource["kind"] == "Service":
                api.create_namespaced_service(namespace=namespace, body=resource)
                print(f"Created VDI service: vdi-{user}-{project}", flush=True)
                created_resources.append(f"Service:vdi-{user}-{project}")
        except ApiException as e:
            if e.status == 409:
                print(
                    f"Resource already exists: {resource['kind']} {resource['metadata']['name']}",
                    flush=True,
                )
            else:
                print(f"Failed to create {resource['kind']}: {e}", flush=True)
                raise

    patch.status["phase"] = "Running"
    print(
        f"SSO VDI created: {name} with {len(created_resources)} resources", flush=True
    )
    print(f"Created resources: {created_resources}", flush=True)


@kopf.on.delete("karectl.io", "v1alpha1", "vdiinstances")
def delete_vdi(spec, name, namespace, patch, **kwargs):
    print(f"Deleting VDI: {name}", flush=True)
    user = spec["user"]
    project = spec["project"]

    pod_name = f"vdi-{name}"
    service_name = f"vdi-{user}-{project}"

    api = kubernetes.client.CoreV1Api()

    try:
        api.delete_namespaced_pod(name=pod_name, namespace=namespace)
        print(f"Deleted pod {pod_name}", flush=True)

    except ApiException as e:
        if e.status != 404:
            print(f"Failed to delete pod {pod_name}: {e}", flush=True)

    # Delete service
    try:
        api.delete_namespaced_service(name=service_name, namespace=namespace)
        print(f"Deleted service {service_name}", flush=True)
    except ApiException as e:
        if e.status != 404:
            print(f"Failed to delete service {service_name}: {e}", flush=True)

    patch.status["phase"] = "Terminated"


@kopf.on.update("karectl.io", "v1alpha1", "vdiinstances")
def update_vdi(spec, name, namespace, patch, body, **kwargs):
    """Handle VDI updates, particularly for token refresh"""
    print(f"Updating VDI: {name}", flush=True)

    # Check if environment variables changed (token refresh)
    old_env = body.get("status", {}).get("env_vars", [])
    new_env = spec.get("env", [])

    if old_env != new_env:
        print(f"Environment variables updated for VDI: {name}", flush=True)

        api = kubernetes.client.CoreV1Api()
        pod_name = f"vdi-{name}"

        try:
            api.delete_namespaced_pod(name=pod_name, namespace=namespace)
            print(f"Deleted pod for restart with new tokens: {pod_name}", flush=True)

            # Update status to track env vars
            patch.status["env_vars"] = new_env
            patch.status["last_updated"] = datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat()

        except ApiException as e:
            if e.status != 404:
                print(f"Failed to delete pod for update: {e}", flush=True)
