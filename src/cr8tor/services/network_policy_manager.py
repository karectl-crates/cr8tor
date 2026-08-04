""" Network policy manager for project namespace isolation.

Plan for custom CiliumNetworkPolicy per project namespace:
- Allows all intra-namespace traffic (same project)
- Allows traffic from/to infrastructure namespaces (jupyterhub, backend, cr8tor, keycloak)
- Allows DNS resolution via kube-dns
- Cross-project isolation so different namespaces can't communicate
"""

import logging

import kubernetes
from kubernetes.client.exceptions import ApiException
import yaml

from cr8tor.services.gitea_client import is_gitea_enabled, get_gitea_network_target

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
            k8s:io.kubernetes.pod.namespace: keycloak

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
              protocol: ANY
          rules:
            dns:
              - matchPattern: "*"
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
            k8s:io.kubernetes.pod.namespace: keycloak
"""


def _apply_gitea_rules(policy_body):
    """ Add Gitea ingress/egress rules to a policy body, if Gitea is enabled.

    Supports both an in-cluster Gitea (namespace selector) and an external or
    ingress-fronted one (FQDN), on whatever ports are configured. Mutates policy_body.

    Args:
        policy_body: Parsed CiliumNetworkPolicy dict

    Returns:
        The Gitea FQDN when reached externally, otherwise None.
    """
    if not is_gitea_enabled():
        return None

    target = get_gitea_network_target()
    to_ports = [
        {"ports": [{"port": str(port), "protocol": "TCP"} for port in target["ports"]]}
    ]

    if target["mode"] == "cluster":
        selector = [{"matchLabels": {"k8s:io.kubernetes.pod.namespace": target["namespace"]}}]
        policy_body["spec"]["ingress"].append({"fromEndpoints": selector})
        policy_body["spec"]["egress"].append(
            {"toEndpoints": selector, "toPorts": to_ports}
        )
        return None

    if target["fqdn"]:
        policy_body["spec"]["egress"].append(
            {"toFQDNs": [{"matchName": target["fqdn"]}], "toPorts": to_ports}
        )
        return target["fqdn"]

    logger.warning("Gitea is enabled but GITEA_URL has no resolvable host; no egress rule added")
    return None


def create_project_network_policy(project_name, namespace, approved_egress_rules=None):
    """ Create a CiliumNetworkPolicy in the project namespace.

    Args:
        project_name: Name of the project
        namespace: Project namespace
        approved_egress_rules: Optional list with fqdn and optional ports

    Returns:
        dict with status of the operation
    """
    api = kubernetes.client.CustomObjectsApi()
    policy_name = "project-isolation"
    policy_yaml = NAMESPACE_NETWORK_POLICY_TEMPLATE.format(
        project_name=project_name,
        namespace=namespace,
    )
    policy_body = yaml.safe_load(policy_yaml)

    gitea_fqdn = _apply_gitea_rules(policy_body)

    if approved_egress_rules:
        # Restrict DNS proxy to cluster-internal names and approved FQDNs only.
        dns_matches = [
            {"matchPattern": "*.cluster.local"},
            {"matchPattern": "*.internal"},
        ]
        dns_matches.extend({"matchName": rule["fqdn"]} for rule in approved_egress_rules)
        # An external Gitea must stay resolvable, or its toFQDNs rule can never match
        if gitea_fqdn and not any(
            rule["fqdn"] == gitea_fqdn for rule in approved_egress_rules
        ):
            dns_matches.append({"matchName": gitea_fqdn})
        for egress_rule in policy_body["spec"]["egress"]:
            for ep in egress_rule.get("toEndpoints", []):
                if ep.get("matchLabels", {}).get("k8s-app") == "kube-dns":
                    egress_rule["toPorts"][0]["rules"]["dns"] = dns_matches
                    break

    for rule in (approved_egress_rules or []):
        ports = rule.get("ports") or [443]
        policy_body["spec"]["egress"].append({
            "toFQDNs": [{"matchName": rule["fqdn"]}],
            "toPorts": [{"ports": [{"port": str(port), "protocol": "TCP"} for port in ports]}],
        })

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
        logger.info(f"Updated CiliumNetworkPolicy in {namespace}")
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
            logger.info(f"Created CiliumNetworkPolicy in {namespace}")
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
