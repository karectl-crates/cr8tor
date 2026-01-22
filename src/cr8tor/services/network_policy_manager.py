""" Network policy manager for creating project isolation policies.
"""

import kubernetes
from kubernetes.client.exceptions import ApiException

# Target namespace where VDI pods run (TBD)
VDI_NAMESPACE = "jupyterhub"

# CiliumNetworkPolicy template for project isolation
NETWORK_POLICY_TEMPLATE = """
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: project-{project_name}-isolation
  namespace: {namespace}
  labels:
    karectl.io/project: "{project_name}"
    karectl.io/managed-by: cr8tor
spec:
  endpointSelector:
    matchLabels:
      karectl.io/project: "{project_name}"

  ingress:
    # Allow from same project
    - fromEndpoints:
        - matchLabels:
            karectl.io/project: "{project_name}"
    # Allow from kube-system
    - fromEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: kube-system
    # Allow from keycloak namespace
    - fromEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: keycloak
    # Allow from cr8tor namespace
    - fromEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: cr8tor
    # Allow from backend namespace
    - fromEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: backend
    # Allow from infrastructure pods without project label (hub, proxy, etc. within jupyterhub)
    - fromEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: {namespace}
          matchExpressions:
            - key: karectl.io/project
              operator: DoesNotExist

  ingressDeny:
    # Deny from OTHER projects
    - fromEndpoints:
        - matchExpressions:
            - key: karectl.io/project
              operator: Exists
            - key: karectl.io/project
              operator: NotIn
              values:
                - "{project_name}"

  egress:
    # Allow to same project
    - toEndpoints:
        - matchLabels:
            karectl.io/project: "{project_name}"
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
    - toEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: keycloak
    # Allow to cr8tor namespace
    - toEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: cr8tor
    # Allow to backend namespace
    - toEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: backend
    # Allow to infrastructure pods without project label (hub, proxy, etc.)
    # Restricted to jupyterhub namespace only
    - toEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: {namespace}
          matchExpressions:
            - key: karectl.io/project
              operator: DoesNotExist
    # Allow external/internet access
    - toEntities:
        - world

  egressDeny:
    # Deny to OTHER projects
    - toEndpoints:
        - matchExpressions:
            - key: karectl.io/project
              operator: Exists
            - key: karectl.io/project
              operator: NotIn
              values:
                - "{project_name}"
"""


def create_project_network_policy(project_name, namespace=VDI_NAMESPACE):
    """ Create a CiliumNetworkPolicy for project isolation.

    Args:
        project_name: Name of the project
        namespace: Namespace where VDI pods run (default: jupyterhub)

    Returns:
        dict with status of the operation
    """
    import yaml

    api = kubernetes.client.CustomObjectsApi()
    policy_name = f"project-{project_name}-isolation"

    # Render the template
    policy_yaml = NETWORK_POLICY_TEMPLATE.format(
        project_name=project_name,
        namespace=namespace
    )
    policy_body = yaml.safe_load(policy_yaml)

    try:
        # Check if policy already exists
        existing = api.get_namespaced_custom_object(
            group="cilium.io",
            version="v2",
            namespace=namespace,
            plural="ciliumnetworkpolicies",
            name=policy_name
        )

        # Update existing policy
        policy_body["metadata"]["resourceVersion"] = existing["metadata"]["resourceVersion"]
        api.replace_namespaced_custom_object(
            group="cilium.io",
            version="v2",
            namespace=namespace,
            plural="ciliumnetworkpolicies",
            name=policy_name,
            body=policy_body
        )
        print(f"Updated CiliumNetworkPolicy: {policy_name} in {namespace}", flush=True)
        return {"status": "updated", "name": policy_name, "namespace": namespace}

    except ApiException as e:
        if e.status == 404:
            # Create new one
            api.create_namespaced_custom_object(
                group="cilium.io",
                version="v2",
                namespace=namespace,
                plural="ciliumnetworkpolicies",
                body=policy_body
            )
            print(f"Created CiliumNetworkPolicy: {policy_name} in {namespace}", flush=True)
            return {"status": "created", "name": policy_name, "namespace": namespace}
        else:
            print(f"Failed to create/update CiliumNetworkPolicy {policy_name}: {e}", flush=True)
            raise


def delete_project_network_policy(project_name, namespace=VDI_NAMESPACE):
    """ Delete a CiliumNetworkPolicy for a project.

    Args:
        project_name: Name of the project
        namespace: Namespace where the policy exists (default: jupyterhub)

    Returns:
        dict with status of the operation
    """
    api = kubernetes.client.CustomObjectsApi()
    policy_name = f"project-{project_name}-isolation"

    try:
        api.delete_namespaced_custom_object(
            group="cilium.io",
            version="v2",
            namespace=namespace,
            plural="ciliumnetworkpolicies",
            name=policy_name
        )
        print(f"Deleted CiliumNetworkPolicy: {policy_name} from {namespace}", flush=True)
        return {"status": "deleted", "name": policy_name, "namespace": namespace}

    except ApiException as e:
        if e.status == 404:
            print(f"CiliumNetworkPolicy {policy_name} not found in {namespace} (already deleted)", flush=True)
            return {"status": "not_found", "name": policy_name, "namespace": namespace}
        else:
            print(f"Failed to delete CiliumNetworkPolicy {policy_name}: {e}", flush=True)
            raise
