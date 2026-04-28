""" Network policy manager for project namespace isolation.

Plan for custom CiliumNetworkPolicy per project namespace:
- Allows all intra-namespace traffic (same project)
- Allows traffic from/to infrastructure namespaces (jupyterhub, backend, cr8tor, keycloak)
- Allows DNS resolution via kube-dns
- Allows external/internet access
- Cross-project isolation so different namespaces can't communicate
- Datashield namespace access granted only to projects with a Datashield resource
"""

import logging

import kubernetes
from kubernetes.client.exceptions import ApiException
import yaml

logger = logging.getLogger(__name__)

# CiliumNetworkPolicy template for project isolation
# endpointSelector: {} selects ALL pods in the namespace.
NAMESPACE_NETWORK_POLICY_TEMPLATE = """
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: project-isolation
  namespace: {namespace}
  labels:
    karectl.io/project: "{project_name}"
    karectl.io/managed-by: cr8tor
spec:
  endpointSelector: {{}}

  ingress:
    # Allow all intra-namespace traffic
    - fromEndpoints:
        - {{}}
    # Allow from kube-system
    - fromEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: kube-system
    # Allow from jupyterhub namespace (hub, proxy, auth-proxy)
    - fromEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: jupyterhub
    # Allow from backend namespace (portal)
    - fromEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: backend
    # Allow from cr8tor namespace (operator)
    - fromEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: cr8tor
    # Allow from keycloak namespace
    - fromEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: keycloak{datashield_ingress}

  egress:
    # Allow all intra-namespace traffic
    - toEndpoints:
        - {{}}
    # Allow DNS resolution
    - toEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: kube-system
            k8s-app: kube-dns
      toPorts:
        - ports:
            - port: "53"
              protocol: UDP
            - port: "53"
              protocol: TCP
    # Allow to jupyterhub namespace (hub callbacks, proxy)
    - toEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: jupyterhub
    # Allow to backend namespace (portal API)
    - toEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: backend
    # Allow to cr8tor namespace
    - toEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: cr8tor
    # Allow to keycloak namespace (authentication)
    - toEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: keycloak{datashield_egress}
    # Allow external/internet access
    - toEntities:
        - world
"""

# Optional rule appended to ingress/egress only for federation projects.
_DATASHIELD_INGRESS = """
    # Allow from datashield namespace (opal/datashield)
    - fromEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: datashield"""

_DATASHIELD_EGRESS = """
    # Allow to datashield namespace (opal/datashield)
    - toEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: datashield"""


def create_project_network_policy(project_name, namespace, datashield_enabled=False):
    """ Create a CiliumNetworkPolicy in the project namespace.

    Args:
        project_name: Name of the project
        namespace: Project namespace
        datashield_enabled: When True, adds ingress/egress rules for the
            datashield namespace.

    Returns:
        dict with status of the operation
    """
    api = kubernetes.client.CustomObjectsApi()
    policy_name = "project-isolation"
    policy_yaml = NAMESPACE_NETWORK_POLICY_TEMPLATE.format(
        project_name=project_name,
        namespace=namespace,
        datashield_ingress=_DATASHIELD_INGRESS if datashield_enabled else "",
        datashield_egress=_DATASHIELD_EGRESS if datashield_enabled else "",
    )
    policy_body = yaml.safe_load(policy_yaml)

    try:
        existing = api.get_namespaced_custom_object(
            group="cilium.io",
            version="v2",
            namespace=namespace,
            plural="ciliumnetworkpolicies",
            name=policy_name,
        )
        policy_body["metadata"]["resourceVersion"] = existing["metadata"]["resourceVersion"]
        api.replace_namespaced_custom_object(
            group="cilium.io",
            version="v2",
            namespace=namespace,
            plural="ciliumnetworkpolicies",
            name=policy_name,
            body=policy_body,
        )
        logger.info(f"Updated CiliumNetworkPolicy in {namespace} (datashield_enabled={datashield_enabled})")
        return {"status": "updated", "name": policy_name, "namespace": namespace}

    except ApiException as e:
        if e.status == 404:
            api.create_namespaced_custom_object(
                group="cilium.io",
                version="v2",
                namespace=namespace,
                plural="ciliumnetworkpolicies",
                body=policy_body,
            )
            logger.info(f"Created CiliumNetworkPolicy in {namespace} (datashield_enabled={datashield_enabled})")
            return {"status": "created", "name": policy_name, "namespace": namespace}
        else:
            logger.error(f"Failed to create/update CiliumNetworkPolicy in {namespace}: {e}")
            raise


def delete_project_network_policy(project_name, namespace):
    """Delete the CiliumNetworkPolicy from a project namespace.

    Args:
        project_name: Name of the project
        namespace: Project namespace

    Returns:
        dict with status of the operation
    """
    api = kubernetes.client.CustomObjectsApi()
    policy_name = "project-isolation"

    try:
        api.delete_namespaced_custom_object(
            group="cilium.io",
            version="v2",
            namespace=namespace,
            plural="ciliumnetworkpolicies",
            name=policy_name,
        )
        logger.info(f"Deleted CiliumNetworkPolicy from {namespace}")
        return {"status": "deleted", "name": policy_name, "namespace": namespace}
    except ApiException as e:
        if e.status == 404:
            logger.info(f"CiliumNetworkPolicy not found in {namespace} (already deleted)")
            return {"status": "not_found", "name": policy_name, "namespace": namespace}
        else:
            logger.error(f"Failed to delete CiliumNetworkPolicy from {namespace}: {e}")
            raise
