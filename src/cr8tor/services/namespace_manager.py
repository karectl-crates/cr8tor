""" Namespace manager for creating and managing project namespaces.
"""

import logging

import kubernetes
from kubernetes.client.exceptions import ApiException

logger = logging.getLogger(__name__)

PROJECT_NAMESPACE_PREFIX = "project-"
STANDARD_LABELS = {
    "karectl.io/managed-by": "cr8tor",
    "karectl.io/resource-type": "project-namespace",
}

# JupyterHub ServiceAccount info for permissions in project namespaces
JUPYTERHUB_SA_NAME = "hub"
JUPYTERHUB_SA_NAMESPACE = "jupyterhub"


def get_proj_namespace(project_name, prefix=PROJECT_NAMESPACE_PREFIX):
    """ Compute the namespace name for a project.

    Args:
        project_name: The project name
        prefix: Namespace prefix (default: "project-")
    """
    return f"{prefix}{project_name}"


def ensure_proj_namespace(project_name, description="", labels=None):
    """ Create or update the project namespace.

    Args:
        project_name: Project name
        description: Project description
        labels: Additional labels to apply
    """
    api = kubernetes.client.CoreV1Api()
    ns_name = get_proj_namespace(project_name)

    ns_labels = {**STANDARD_LABELS, "karectl.io/project": project_name}
    if labels:
        ns_labels.update(labels)

    ns_annotations = {
        "karectl.io/project-description": description,
    }

    ns_body = kubernetes.client.V1Namespace(
        metadata=kubernetes.client.V1ObjectMeta(
            name=ns_name,
            labels=ns_labels,
            annotations=ns_annotations,
        )
    )
    try:
        existing = api.read_namespace(name=ns_name)
        existing.metadata.labels = ns_labels
        existing.metadata.annotations = existing.metadata.annotations or {}
        existing.metadata.annotations.update(ns_annotations)
        api.replace_namespace(name=ns_name, body=existing)
        logger.info(f"Updated namespace: {ns_name}")
        return {"status": "updated", "namespace": ns_name}

    except ApiException as e:
        if e.status == 404:
            api.create_namespace(body=ns_body)
            logger.info(f"Created namespace: {ns_name}")
            return {"status": "created", "namespace": ns_name}
        else:
            logger.error(f"Failed to ensure namespace {ns_name}: {e}")
            raise


def ensure_resource_quota(project_name, quota_config=None):
    """ Create or update a ResourceQuota in the project namespace.

    Args:
        project_name: Project name
        quota_config: Dict with quota values
    """
    api = kubernetes.client.CoreV1Api()
    ns_name = get_proj_namespace(project_name)
    quota_name = f"{project_name}-quota"

    if quota_config is None:
        quota_config = {}

    hard = {
        "requests.cpu": quota_config.get("requests_cpu", "4"),
        "requests.memory": quota_config.get("requests_memory", "8Gi"),
        "limits.cpu": quota_config.get("limits_cpu", "8"),
        "limits.memory": quota_config.get("limits_memory", "16Gi"),
        "pods": quota_config.get("pods", "20"),
        "services": quota_config.get("services", "10"),
        "persistentvolumeclaims": quota_config.get("persistentvolumeclaims", "10"),
    }

    quota_body = kubernetes.client.V1ResourceQuota(
        metadata=kubernetes.client.V1ObjectMeta(
            name=quota_name,
            namespace=ns_name,
            labels={**STANDARD_LABELS, "karectl.io/project": project_name},
        ),
        spec=kubernetes.client.V1ResourceQuotaSpec(hard=hard),
    )

    try:
        api.read_namespaced_resource_quota(name=quota_name, namespace=ns_name)
        api.replace_namespaced_resource_quota(
            name=quota_name, namespace=ns_name, body=quota_body
        )
        logger.info(f"Updated ResourceQuota {quota_name} in {ns_name}")
        return {"status": "updated", "name": quota_name}

    except ApiException as e:
        if e.status == 404:
            api.create_namespaced_resource_quota(namespace=ns_name, body=quota_body)
            logger.info(f"Created ResourceQuota {quota_name} in {ns_name}")
            return {"status": "created", "name": quota_name}
        else:
            logger.error(f"Failed to ensure ResourceQuota {quota_name}: {e}")
            raise


def ensure_limit_range(project_name, limit_config=None):
    """ Create or update a LimitRange in project namespace.

    Args:
        project_name: Project name
        limit_config: Dict with limit values
    """
    api = kubernetes.client.CoreV1Api()
    ns_name = get_proj_namespace(project_name)
    lr_name = f"{project_name}-limits"

    if limit_config is None:
        limit_config = {}

    lr_body = kubernetes.client.V1LimitRange(
        metadata=kubernetes.client.V1ObjectMeta(
            name=lr_name,
            namespace=ns_name,
            labels={**STANDARD_LABELS, "karectl.io/project": project_name},
        ),
        spec=kubernetes.client.V1LimitRangeSpec(
            limits=[
                kubernetes.client.V1LimitRangeItem(
                    type="Container",
                    default={
                        "cpu": limit_config.get("default_cpu", "500m"),
                        "memory": limit_config.get("default_memory", "1Gi"),
                    },
                    default_request={
                        "cpu": limit_config.get("default_request_cpu", "100m"),
                        "memory": limit_config.get("default_request_memory", "256Mi"),
                    },
                )
            ]
        ),
    )

    try:
        api.read_namespaced_limit_range(name=lr_name, namespace=ns_name)
        api.replace_namespaced_limit_range(
            name=lr_name, namespace=ns_name, body=lr_body
        )
        logger.info(f"Updated LimitRange {lr_name} in {ns_name}")
        return {"status": "updated", "name": lr_name}

    except ApiException as e:
        if e.status == 404:
            api.create_namespaced_limit_range(namespace=ns_name, body=lr_body)
            logger.info(f"Created LimitRange {lr_name} in {ns_name}")
            return {"status": "created", "name": lr_name}
        else:
            logger.error(f"Failed to ensure LimitRange {lr_name}: {e}")
            raise


def ensure_jupyter_rolebind(project_name):
    """ Create a Role and RoleBinding in the project namespace for the jupyterhub service account

    Args:
        project_name: Project name
    """
    rbac_api = kubernetes.client.RbacAuthorizationV1Api()
    ns_name = get_proj_namespace(project_name)
    name = "jupyterhub-hub-spawner"

    # Role with permissions needed to create it.
    role_body = kubernetes.client.V1Role(
        metadata=kubernetes.client.V1ObjectMeta(
            name=name,
            namespace=ns_name,
            labels={**STANDARD_LABELS, "karectl.io/project": project_name},
        ),
        rules=[
            kubernetes.client.V1PolicyRule(
                api_groups=[""],
                resources=["pods", "services", "persistentvolumeclaims"],
                verbs=["get", "list", "watch", "create", "update", "patch", "delete"],
            ),
            kubernetes.client.V1PolicyRule(
                api_groups=[""],
                resources=["events"],
                verbs=["create", "patch"],
            ),
            kubernetes.client.V1PolicyRule(
                api_groups=[""],
                resources=["secrets", "configmaps"],
                verbs=["get", "list", "watch", "create", "update", "patch"],
            ),
        ],
    )

    try:
        rbac_api.read_namespaced_role(name=name, namespace=ns_name)
        rbac_api.replace_namespaced_role(name=name, namespace=ns_name, body=role_body)
        logger.info(f"Updated Role {name} in {ns_name}")
    except ApiException as e:
        if e.status == 404:
            rbac_api.create_namespaced_role(namespace=ns_name, body=role_body)
            logger.info(f"Created Role {name} in {ns_name}")
        else:
            raise

    # RoleBinding for the jupyterhub hub service account
    binding_body = kubernetes.client.V1RoleBinding(
        metadata=kubernetes.client.V1ObjectMeta(
            name=name,
            namespace=ns_name,
            labels={**STANDARD_LABELS, "karectl.io/project": project_name},
        ),
        role_ref=kubernetes.client.V1RoleRef(
            api_group="rbac.authorization.k8s.io",
            kind="Role",
            name=name,
        ),
        subjects=[
            kubernetes.client.RbacV1Subject(
                kind="ServiceAccount",
                name=JUPYTERHUB_SA_NAME,
                namespace=JUPYTERHUB_SA_NAMESPACE,
            )
        ],
    )

    try:
        rbac_api.read_namespaced_role_binding(name=name, namespace=ns_name)
        rbac_api.replace_namespaced_role_binding(
            name=name, namespace=ns_name, body=binding_body
        )
        logger.info(f"Updated RoleBinding {name} in {ns_name}")
        return {"status": "updated", "name": name}

    except ApiException as e:
        if e.status == 404:
            rbac_api.create_namespaced_role_binding(namespace=ns_name, body=binding_body)
            logger.info(f"Created RoleBinding {name} in {ns_name}")
            return {"status": "created", "name": name}
        else:
            logger.error(f"Failed to ensure RoleBinding {name}: {e}")
            raise


def del_proj_namespace(project_name):
    """ Delete the project namespace with cascading deletion.

    Args:
        project_name: Project name
    """
    api = kubernetes.client.CoreV1Api()
    ns_name = get_proj_namespace(project_name)

    try:
        api.delete_namespace(name=ns_name)
        logger.info(f"Deleted namespace: {ns_name}")
        return {"status": "deleted", "namespace": ns_name}
    except ApiException as e:
        if e.status == 404:
            logger.info(f"Namespace {ns_name} not found")
            return {"status": "not_found", "namespace": ns_name}
        else:
            logger.error(f"Failed to delete namespace {ns_name}: {e}")
            raise
