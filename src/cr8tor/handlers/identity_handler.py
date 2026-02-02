"""Module that provides the identity handler for the operator."""

import logging
import os

import kopf
import kubernetes
from kubernetes.client.exceptions import ApiException

from cr8tor.services.user_manager import sync_keycloak_user, delete_keycloak_user
from cr8tor.services.group_manager import sync_keycloak_group, delete_keycloak_group
from cr8tor.services.client_manager import sync_keycloak_client, delete_keycloak_client
from cr8tor.services.client import ensure_realm_exists
from cr8tor.services.network_policy_manager import (
    create_project_network_policy
)
from cr8tor.services.namespace_manager import (
    ensure_proj_namespace,
    ensure_resource_quota,
    ensure_limit_range,
    ensure_jupyter_rolebind,
    del_proj_namespace,
    get_proj_namespace,
)
from cr8tor.services.storage_manager import (
    ensure_workspace_pvc,
    delete_workspace_pvc,
    get_pvc_name,
    resolve_storage_config,
)

logger = logging.getLogger(__name__)

# Namespace where User and Group CRDs are stored
IDENTITY_NAMESPACE = os.environ.get("IDENTITY_NAMESPACE", "keycloak")


def get_user_projects(user_groups):
    """Resolve all projects from a list of group memberships.

    Args:
        user_groups: List of group names (from User CRD spec.groups)
    """
    api = kubernetes.client.CustomObjectsApi()
    projects = set()

    for group_name in user_groups:
        try:
            group_cr = api.get_namespaced_custom_object(
                group="identity.karectl.io",
                version="v1alpha1",
                namespace=IDENTITY_NAMESPACE,
                plural="groups",
                name=group_name,
            )
            group_projects = group_cr.get("spec", {}).get("projects", [])
            projects.update(group_projects)
            logger.info(f"Group {group_name} has projects: {group_projects}")
        except ApiException as e:
            if e.status == 404:
                logger.warning(f"Group {group_name} not found")
            else:
                logger.error(f"Failed to fetch group {group_name}: {e}")

    return projects


def get_group_members(group_name):
    """Get all members of a group from group CRD.

    Args:
        group_name: Name of the group
    """
    api = kubernetes.client.CustomObjectsApi()

    # Check for Group CRD's members field
    try:
        group_cr = api.get_namespaced_custom_object(
            group="identity.karectl.io",
            version="v1alpha1",
            namespace=IDENTITY_NAMESPACE,
            plural="groups",
            name=group_name,
        )
        members = group_cr.get("spec", {}).get("members", [])
        if members:
            return members
    except ApiException:
        pass

    # If N/A, get users who got this group in their groups list
    members = []
    try:
        users = api.list_namespaced_custom_object(
            group="identity.karectl.io",
            version="v1alpha1",
            namespace=IDENTITY_NAMESPACE,
            plural="users",
        )
        for user in users.get("items", []):
            user_groups = user.get("spec", {}).get("groups", [])
            if group_name in user_groups:
                username = user.get("spec", {}).get("username")
                if username:
                    members.append(username)
    except ApiException as e:
        logger.error(f"Failed to list users for group {group_name}: {e}")

    return members


def ensure_user_notebook_pvc(username, projects):
    """Ensure notebook PVCs exist for a user in the projects.

    Args:
        username: username
        projects: Set/list of project names
    """
    results = {}

    for project_name in projects:
        try:
            # Check for project namespace
            namespace = get_proj_namespace(project_name)

            # Resolve storage config for this project
            size, storage_class = resolve_storage_config(project_name)

            if size is None:
                logger.info(f"No notebook storage configured for project {project_name}, skipping PVC for {username}")
                results[project_name] = {"status": "skipped", "reason": "no_storage_config"}
                continue

            pvc_name = get_pvc_name("notebook", username, project_name)
            # Tracker labels for PVC
            labels = {
                "karectl.io/user": username,
                "karectl.io/project": project_name,
                "karectl.io/workspace-type": "notebook",
                "karectl.io/provisioned-by": "identity-handler",
            }

            # Create PVC
            result = ensure_workspace_pvc(
                namespace=namespace,
                pvc_name=pvc_name,
                size=size,
                storage_class=storage_class,
                labels=labels,
            )

            logger.info(f"Notebook PVC for {username} in {project_name}: {result['status']} ({pvc_name})")
            results[project_name] = result

        except ApiException as e:
            if e.status == 404:
                logger.warning(f"Project namespace {project_name} not found, skipping PVC for {username}")
                results[project_name] = {"status": "skipped", "reason": "namespace_not_found"}
            else:
                logger.error(f"Failed to create notebook PVC for {username} in {project_name}: {e}")
                results[project_name] = {"status": "error", "error": str(e)}
        except Exception as e:
            logger.error(f"Failed to create notebook PVC for {username} in {project_name}: {e}")
            results[project_name] = {"status": "error", "error": str(e)}

    return results


def cleanup_user_notebook_pvcs(username, projects):
    """Delete notebook PVCs for a user on removing from projects.

    Args:
        username: username
        projects: Set/list of project names to remove PVCs
    """
    results = {}

    for project_name in projects:
        try:
            namespace = get_proj_namespace(project_name)
            pvc_name = get_pvc_name("notebook", username, project_name)
            result = delete_workspace_pvc(namespace, pvc_name)
            logger.info(f"Notebook PVC cleanup for {username} in {project_name}: {result['status']}")
            results[project_name] = result

        except Exception as e:
            logger.error(f"Failed to cleanup notebook PVC for {username} in {project_name}: {e}")
            results[project_name] = {"status": "error", "error": str(e)}

    return results

# https://www.reddit.com/r/kubernetes/comments/1dge5qk/writing_an_operator_with_kopf/
# Note: Startup configuration is now handled in main.py to avoid conflicts


@kopf.on.create("identity.karectl.io", "v1alpha1", "user")
@kopf.on.update("identity.karectl.io", "v1alpha1", "user")
def user_create_update(body, spec, meta, status, patch, **kwargs):
    """ Operator function for creating and updating users.
        Provision notebook PVCs for the projects the user has access to.
    """
    username = spec["username"]
    user_groups = spec.get("groups", [])

    ensure_realm_exists()
    result = sync_keycloak_user(username, spec)

    if result and "password" in result:
        patch.status["initialPassword"] = result["password"]

    kopf.info(meta, reason="UserSynced", message=f"User {username} synced.")

    # Provision notebook PVCs for user's projects
    if user_groups:
        projects = get_user_projects(user_groups)

        if projects:
            logger.info(f"Provisioning notebook storage for {username} in {len(projects)} projects: {projects}")
            pvc_results = ensure_user_notebook_pvc(username, projects)

            # Track storage and status
            provisioned = [pvc for pvc, reason in pvc_results.items() if reason.get("status") in ("created", "exists")]
            skipped = [pvc for pvc, reason in pvc_results.items() if reason.get("status") == "skipped"]
            errors = [pvc for pvc, reason in pvc_results.items() if reason.get("status") == "error"]

            patch.status["notebookStorage"] = {
                "provisioned": provisioned,
                "skipped": skipped,
                "errors": errors,
            }

            if provisioned:
                kopf.info(
                    meta,
                    reason="StorageProvisioned",
                    message=f"Notebook storage provisioned for {username} in projects: {', '.join(provisioned)}",
                )
            if errors:
                kopf.warn(
                    meta,
                    reason="StorageError",
                    message=f"Failed to provision storage in projects: {', '.join(errors)}",
                )
        else:
            logger.info(f"User {username} has groups but no projects configured")
    else:
        logger.info(f"User {username} has no groups, skipping storage provisioning")


@kopf.on.delete("identity.karectl.io", "v1alpha1", "user")
def user_delete(body, spec, meta, **kwargs):
    """ Operator function for deleting users.

        PVCs are cleaned up when Project is deleted (namespace cascading deletion)
    """
    username = spec["username"]
    user_groups = spec.get("groups", [])

    delete_keycloak_user(username)

    # Update which PVCs will be retained
    if user_groups:
        projects = get_user_projects(user_groups)
        if projects:
            logger.info(
                f"User {username} deleted. Notebook PVCs retained in projects: {projects}. "
                "PVCs will be cleaned up when project is deleted."
            )

    kopf.info(meta, reason="UserDeleted", message=f"User {username} deleted. Notebook PVCs retained.")


@kopf.on.create("identity.karectl.io", "v1alpha1", "group")
@kopf.on.update("identity.karectl.io", "v1alpha1", "group")
def group_create_update(body, spec, meta, patch, **kwargs):
    """ Operator function for creating and updating groups.

        Provisions notebook PVCs for group members when projects are configured.
    """
    groupname = meta["name"]
    projects = spec.get("projects", [])

    ensure_realm_exists()
    sync_keycloak_group(groupname, spec)
    kopf.info(meta, reason="GroupSynced", message=f"Group {groupname} synced.")

    # Provision notebook storage for all members in all projects
    if projects:
        members = get_group_members(groupname)

        if members:
            logger.info(f"Provisioning notebook storage for {len(members)} members of {groupname} in projects: {projects}")

            all_results = {}
            for username in members:
                pvc_results = ensure_user_notebook_pvc(username, projects)
                all_results[username] = pvc_results

            # Summarise results
            total_provisioned = sum(
                1 for user_results in all_results.values()
                for result in user_results.values()
                if result.get("status") in ("created", "exists")
            )
            total_errors = sum(
                1 for user_results in all_results.values()
                for result in user_results.values()
                if result.get("status") == "error"
            )

            patch.status["storageProvisioning"] = {
                "members": len(members),
                "projects": len(projects),
                "pvcsProvisioned": total_provisioned,
                "errors": total_errors,
            }

            if total_provisioned > 0:
                kopf.info(
                    meta,
                    reason="StorageProvisioned",
                    message=f"Provisioned {total_provisioned} notebook PVCs for group {groupname} members",
                )
            if total_errors > 0:
                kopf.warn(
                    meta,
                    reason="StorageError",
                    message=f"Failed to provision {total_errors} PVCs for group {groupname}",
                )
        else:
            logger.info(f"Group {groupname} has projects but no members")
    else:
        logger.info(f"Group {groupname} has no projects configured")


@kopf.on.delete("identity.karectl.io", "v1alpha1", "group")
def group_delete(body, spec, meta, **kwargs):
    """Operator function for deleting groups."""
    groupname = meta["name"]
    delete_keycloak_group(groupname)
    kopf.info(meta, reason="GroupDeleted", message=f"Group {groupname} deleted.")


@kopf.on.create("identity.karectl.io", "v1alpha1", "keycloakclient")
@kopf.on.update("identity.karectl.io", "v1alpha1", "keycloakclient")
@kopf.on.resume("identity.karectl.io", "v1alpha1", "keycloakclient")
def client_create_update(body, spec, meta, **kwargs):
    """Handle KeycloakClient create, update, and resume (on operator restart).
    """
    client_id = spec["clientId"]
    namespace = meta.get("namespace", "keycloak")
    sync_keycloak_client(client_id, spec, namespace=namespace)
    kopf.info(
        meta, reason="ClientSynced", message=f"Keycloak client {client_id} synced."
    )


@kopf.on.delete("identity.karectl.io", "v1alpha1", "keycloakclient")
def client_delete(body, spec, meta, **kwargs):
    client_id = spec["clientId"]
    delete_keycloak_client(client_id)
    kopf.info(
        meta, reason="ClientDeleted", message=f"Keycloak client {client_id} deleted."
    )

@kopf.on.create("research.karectl.io", "v1alpha1", "project")
@kopf.on.update("research.karectl.io", "v1alpha1", "project")
@kopf.on.resume("research.karectl.io", "v1alpha1", "project")
def project_create_update(body, spec, meta, patch, **kwargs):
    """ Handle Project resource creation and updates.
        Creates/updates: Project namespace, resource quota, limitRange, jupyterHub hub role binding and cilium network policy
        for namespace isolation.
    """
    project_name = meta["name"]
    description = spec.get("description", "")
    apps = spec.get("apps", [])
    profiles = spec.get("profiles", [])

    # Create/update project namespace
    try:
        ns_result = ensure_proj_namespace(project_name, description)
        kopf.info(
            meta,
            reason="NamespaceReady",
            message=f"Namespace {ns_result['status']}: {ns_result['namespace']}",
        )
    except Exception as e:
        kopf.warn(
            meta,
            reason="NamespaceFailed",
            message=f"Failed to ensure namespace for {project_name}: {e}",
        )
        raise

    # ResourceQuota
    try:
        quota_spec = spec.get("resource_quota") or {}
        quota_result = ensure_resource_quota(project_name, quota_spec)
        kopf.info(
            meta,
            reason="QuotaReady",
            message=f"ResourceQuota {quota_result['status']}: {quota_result['name']}",
        )
    except Exception as e:
        kopf.warn(
            meta,
            reason="QuotaFailed",
            message=f"Failed to ensure quota for {project_name}: {e}",
        )

    # LimitRange
    try:
        limit_spec = spec.get("limit_range") or {}
        lr_result = ensure_limit_range(project_name, limit_spec)
        kopf.info(
            meta,
            reason="LimitRangeReady",
            message=f"LimitRange {lr_result['status']}: {lr_result['name']}",
        )
    except Exception as e:
        kopf.warn(
            meta,
            reason="LimitRangeFailed",
            message=f"Failed to ensure limit range for {project_name}: {e}",
        )

    # JupyterHub hub service account RoleBinding
    try:
        rb_result = ensure_jupyter_rolebind(project_name)
        kopf.info(
            meta,
            reason="RoleBindingReady",
            message=f"Hub RoleBinding {rb_result['status']}: {rb_result['name']}",
        )
    except Exception as e:
        kopf.warn(
            meta,
            reason="RoleBindingFailed",
            message=f"Failed to ensure RoleBinding for {project_name}: {e}",
        )

    # CiliumNetworkPolicy in the project namespace
    try:
        ns_name = get_proj_namespace(project_name)
        policy_result = create_project_network_policy(project_name, namespace=ns_name)
        kopf.info(
            meta,
            reason="NetworkPolicyCreated",
            message=f"Network policy {policy_result['status']}: {policy_result['name']}",
        )
    except Exception as e:
        kopf.warn(
            meta,
            reason="NetworkPolicyFailed",
            message=f"Failed to create network policy for {project_name}: {e}",
        )

    patch.status["namespace"] = get_proj_namespace(project_name)
    kopf.info(
        meta,
        reason="ProjectSynced",
        message=(
            f"Project {project_name} synced to namespace "
            f"{get_proj_namespace(project_name)} "
            f"({len(apps)} apps, {len(profiles)} profiles)"
        ),
    )


@kopf.on.delete("research.karectl.io", "v1alpha1", "project")
def project_delete(body, spec, meta, **kwargs):
    """ Handle Project resource deletion.

    Deletes the project namespace with cascading deletion. Automatically removes all
    resources within that namespace.
    """
    project_name = meta["name"]
    try:
        ns_result = del_proj_namespace(project_name)
        kopf.info(
            meta,
            reason="NamespaceDeleted",
            message=f"Namespace {ns_result['status']}: {ns_result['namespace']}",
        )
    except Exception as e:
        kopf.warn(
            meta,
            reason="NamespaceDeleteFailed",
            message=f"Failed to delete namespace for {project_name}: {e}",
        )

    kopf.info(
        meta,
        reason="ProjectDeleted",
        message=f"Project {project_name} cleanup completed",
    )
