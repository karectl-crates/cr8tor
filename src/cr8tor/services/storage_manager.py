""" Storage manager for creating and managing PVCs for workspaces.
"""

import logging
import os
import re

import kubernetes
from kubernetes.client.exceptions import ApiException

logger = logging.getLogger(__name__)


def get_pvc_name(workspace_type, username, project):
    """Generate PVC name for a workspace.

    Args:
        workspace_type: Type of workspace ('vdi' or 'notebook')
        username: Username
        project: Project name
    """
    safe_user = re.sub(r"[^a-z0-9-]", "", username.lower())
    safe_project = re.sub(r"[^a-z0-9-]", "", project.lower())
    return f"{workspace_type}-{safe_user}-{safe_project}"


def get_bytes(size_str):
    """ Convert k8s size string to bytes for comparison.

    Args:
        size_str: Size string like '10Gi', '500Mi', '1Ti'
    """
    if size_str is None:
        return None

    size_str = str(size_str).strip()
    units = {
        "Ki": 1024,
        "Mi": 1024**2,
        "Gi": 1024**3,
        "Ti": 1024**4,
        "K": 1000,
        "M": 1000**2,
        "G": 1000**3,
        "T": 1000**4,
    }

    for suffix, multiplier in units.items():
        if size_str.endswith(suffix):
            return int(size_str[: -len(suffix)]) * multiplier

    return int(size_str)


def min_size(size1, size2):
    """ Return the smaller of two size strings.

    Args:
        size1: First size string (e.g., '50Gi')
        size2: Second size string (e.g., '100Gi')
    """
    if size1 is None:
        return size2
    if size2 is None:
        return size1

    bytes1 = get_bytes(size1)
    bytes2 = get_bytes(size2)

    return size1 if bytes1 <= bytes2 else size2


def get_helm_storage_config():
    """Get storage config from Helm values.
    """
    def get_env_or_none(key):
        value = os.environ.get(key, "")
        return value if value else None

    return {
        "maxVdiSize": get_env_or_none("STORAGE_MAX_VDI_SIZE"),
        "maxNotebookSize": get_env_or_none("STORAGE_MAX_NOTEBOOK_SIZE"),
        "defaultVdiSize": get_env_or_none("STORAGE_DEFAULT_VDI_SIZE"),
        "defaultNotebookSize": get_env_or_none("STORAGE_DEFAULT_NOTEBOOK_SIZE"),
        "defaultStorageClass": get_env_or_none("STORAGE_DEFAULT_STORAGE_CLASS"),  # None = cluster default
        "defaultPersist": os.environ.get("STORAGE_DEFAULT_PERSIST", "false").lower() == "true",
    }


def get_project_storage_config(project_name):
    """ Get storage config from Project CRD.

    Args:
        project_name: Name of the project
    """
    api = kubernetes.client.CustomObjectsApi()

    try:
        project = api.get_cluster_custom_object(
            group="research.karectl.io",
            version="v1alpha1",
            plural="projects",
            name=project_name,
        )
        return project.get("spec", {}).get("storage", {}) or {}
    except ApiException as e:
        if e.status == 404:
            logger.warning(f"Project {project_name} not found")
            return {}
        raise


def resolve_notebook_storage_config(project_name, override_size=None, override_storage_class=None):
    """ Resolve storage config for notebooks.

    Args:
        project_name: Name of the project
        override_size: Optional size override from API request
        override_storage_class: Optional storage class override
    """
    helm_config = get_helm_storage_config()
    project_config = get_project_storage_config(project_name)

    # Resolve storage class (Override > Project > Helm)
    storage_class = (
        override_storage_class
        or project_config.get("storage_class")
        or helm_config.get("defaultStorageClass")
    )

    # Resolve requested size (Override > Project > Helm default)
    requested_size = (
        override_size
        or project_config.get("default_notebook_size")
        or helm_config.get("defaultNotebookSize")
    )

    # If no size at any level, return None
    if requested_size is None:
        logger.info("No notebook storage size configured at any level")
        return None, None

    # Apply Helm max as ceiling if set
    helm_max = helm_config.get("maxNotebookSize")
    if helm_max:
        final_size = min_size(requested_size, helm_max)
        if final_size != requested_size:
            logger.info(f"Notebook storage size capped: {requested_size} -> {final_size} (max: {helm_max})")
    else:
        final_size = requested_size

    return final_size, storage_class


def resolve_vdi_storage_config(vdi_spec, project_name):
    """ Resolve storage config with priority chain.

        Priority Order: VDI > Project > Helm default

    Args:
        vdi_spec: VDI instance spec dict
        project_name: Name of the project
    """
    helm_config = get_helm_storage_config()
    project_config = get_project_storage_config(project_name)
    vdi_storage = vdi_spec.get("storage", {}) or {}

    # Resolve storage class (VDI > Project > Helm)
    storage_class = (
        vdi_storage.get("storage_class")
        or project_config.get("storage_class")
        or helm_config.get("defaultStorageClass")
    )

    # Resolve requested size (VDI > Project > Helm default)
    requested_size = (
        vdi_storage.get("home_size")
        or project_config.get("default_vdi_size")
        or helm_config.get("defaultVdiSize")
    )

    # If no size at any level, return None
    if requested_size is None:
        logger.info("No storage size configured, PVC disabled")
        return None, None, False, False

    # Apply Helm max as ceiling if set
    helm_max = helm_config.get("maxVdiSize")
    if helm_max:
        final_size = min_size(requested_size, helm_max)
        if final_size != requested_size:
            logger.info(f"Storage size capped: {requested_size} -> {final_size} (max: {helm_max})")
    else:
        final_size = requested_size

    # Persist flag
    if "persist" in vdi_storage:
        persist = vdi_storage.get("persist", False)
    else:
        persist = helm_config.get("defaultPersist", False)

    return final_size, storage_class, persist, True


def ensure_workspace_pvc(namespace, pvc_name, size, storage_class=None, labels=None):
    """ Create PVC if it doesn't exist.

    Args:
        namespace: Kubernetes namespace
        pvc_name: Name for the PVC
        size: Storage size (e.g., '20Gi')
        storage_class: StorageClass name (None = use cluster default)
        labels: Optional labels dict
    """
    api = kubernetes.client.CoreV1Api()

    if labels is None:
        labels = {}

    labels.update({
        "karectl.io/managed-by": "cr8tor",
        "karectl.io/resource-type": "workspace-storage",
    })

    # Build PVC spec
    pvc_spec = kubernetes.client.V1PersistentVolumeClaimSpec(
        access_modes=["ReadWriteOnce"],
        resources=kubernetes.client.V1ResourceRequirements(
            requests={"storage": size}
        ),
    )

    if storage_class:
        pvc_spec.storage_class_name = storage_class

    pvc_body = kubernetes.client.V1PersistentVolumeClaim(
        metadata=kubernetes.client.V1ObjectMeta(
            name=pvc_name,
            namespace=namespace,
            labels=labels,
        ),
        spec=pvc_spec,
    )

    try:
        existing = api.read_namespaced_persistent_volume_claim(
            name=pvc_name, namespace=namespace
        )
        logger.info(f"PVC {pvc_name} already exists in {namespace}")
        return {"status": "exists", "name": pvc_name, "namespace": namespace}

    except ApiException as e:
        if e.status == 404:
            api.create_namespaced_persistent_volume_claim(
                namespace=namespace, body=pvc_body
            )
            logger.info(f"Created PVC {pvc_name} in {namespace} ({size})")
            return {"status": "created", "name": pvc_name, "namespace": namespace}
        else:
            logger.error(f"Failed to check/create PVC {pvc_name}: {e}")
            raise


def delete_workspace_pvc(namespace, pvc_name):
    """ Delete a PVC.

    Args:
        namespace: Kubernetes namespace
        pvc_name: Name of the PVC
    """
    api = kubernetes.client.CoreV1Api()

    try:
        api.delete_namespaced_persistent_volume_claim(
            name=pvc_name, namespace=namespace
        )
        logger.info(f"Deleted PVC {pvc_name} from {namespace}")
        return {"status": "deleted", "name": pvc_name, "namespace": namespace}

    except ApiException as e:
        if e.status == 404:
            logger.info(f"PVC {pvc_name} not found in {namespace} (already deleted)")
            return {"status": "not_found", "name": pvc_name, "namespace": namespace}
        else:
            logger.error(f"Failed to delete PVC {pvc_name}: {e}")
            raise


def list_project_pvcs(namespace):
    """List all workspace PVCs in a project namespace.

    Args:
        namespace: Project namespace
    """
    api = kubernetes.client.CoreV1Api()

    try:
        pvcs = api.list_namespaced_persistent_volume_claim(
            namespace=namespace,
            label_selector="karectl.io/managed-by=cr8tor",
        )
        return [pvc.metadata.name for pvc in pvcs.items]

    except ApiException as e:
        logger.error(f"Failed to list PVCs in {namespace}: {e}")
        raise


def resolve_scheduling_config(vdi_spec, project_name):
    """ Resolve scheduling config based on priority.

    Args:
        vdi_spec: VDI instance spec dict
        project_name: Name of the project
    """
    project_config = get_project_storage_config(project_name)
    project_scheduling = project_config.get("scheduling", {}) if project_config else {}

    # Get from parent project spec, except storage
    api = kubernetes.client.CustomObjectsApi()
    try:
        project = api.get_cluster_custom_object(
            group="research.karectl.io",
            version="v1alpha1",
            plural="projects",
            name=project_name,
        )
        project_scheduling = project.get("spec", {}).get("scheduling", {}) or {}
    except ApiException as e:
        if e.status == 404:
            logger.warning(f"Project {project_name} not found for scheduling config")
            project_scheduling = {}
        else:
            raise

    vdi_scheduling = vdi_spec.get("scheduling", {}) or {}
    # Resolve simple fields (VDI > Project)
    resolved = {
        "node_selector": {
            **project_scheduling.get("node_selector", {}),
            **vdi_scheduling.get("node_selector", {}),
        },
        "tolerations": [
            *project_scheduling.get("tolerations", []),
            *vdi_scheduling.get("tolerations", []),
        ],
        "affinity": vdi_scheduling.get("affinity") or project_scheduling.get("affinity"),
        "labels": {
            **project_scheduling.get("labels", {}),
            **vdi_scheduling.get("labels", {}),
        },
        "annotations": {
            **project_scheduling.get("annotations", {}),
            **vdi_scheduling.get("annotations", {}),
        },
    }

    # Resolve resources (VDI > Project)
    project_resources = project_scheduling.get("resources", {}) or {}
    vdi_resources = vdi_scheduling.get("resources", {}) or {}

    resolved["resources"] = {
        "requests_cpu": vdi_resources.get("requests_cpu") or project_resources.get("requests_cpu"),
        "requests_memory": vdi_resources.get("requests_memory") or project_resources.get("requests_memory"),
        "limits_cpu": vdi_resources.get("limits_cpu") or project_resources.get("limits_cpu"),
        "limits_memory": vdi_resources.get("limits_memory") or project_resources.get("limits_memory"),
    }

    return resolved
