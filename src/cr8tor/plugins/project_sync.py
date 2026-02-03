""" Project Sync Plugin
    Auto-generate CRDs when projects are published.
"""

import kopf
import logging
import toml
from pathlib import Path
from typing import Dict, Any, Optional, List
from kubernetes import client
from kubernetes.client.rest import ApiException
import os

from cr8tor.plugins.base import BasePlugin
from cr8tor.models.identity import (
    UserSpec,
    GroupSpec,
    ProjectSpec,
    ResourceQuotaConfig,
    StorageConfig,
    AppConfig,
)

logger = logging.getLogger(__name__)


class ProjectSyncPlugin(BasePlugin):
    """ Auto generate CRDs when cr8tor projects are published.
    """

    def __init__(self):
        super().__init__()
        self.name = "project-sync"
        self.description = "Auto generate from published cr8tor-projects"
        self.version = "1.0.0"

        self.domain = None
        self.default_quota_tier = os.getenv("CRTOR_DEFAULT_QUOTA_TIER", "medium")
        self.target_namespace = os.getenv("CRTOR_TARGET_NAMESPACE", "keycloak")

        self.quota_tiers = {
            "small": {
                "requests_cpu": "2",
                "requests_memory": "4Gi",
                "limits_cpu": "4",
                "limits_memory": "8Gi",
                "pods": "10",
            },
            "medium": {
                "requests_cpu": "4",
                "requests_memory": "8Gi",
                "limits_cpu": "8",
                "limits_memory": "16Gi",
                "pods": "20",
            },
            "large": {
                "requests_cpu": "8",
                "requests_memory": "16Gi",
                "limits_cpu": "16",
                "limits_memory": "32Gi",
                "pods": "40",
            },
        }

        self.custom_api = None

    def initialize(self) -> bool:
        """ Initialise the plugin.
        """
        try:
            self.custom_api = client.CustomObjectsApi()
            self.core_api = client.CoreV1Api()

            # Load domain from realm config
            self._load_domain_from_config()

            logger.info(f"ProjectSyncPlugin initialised")
            logger.info(f"  Domain: {self.domain}")
            logger.info(f"  Default quota tier: {self.default_quota_tier}")
            logger.info(f"  Target namespace: {self.target_namespace}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialise ProjectSyncPlugin: {e}")
            return False

    def _load_domain_from_config(self):
        """ Load domain from config map
        """
        try:
            cm = self.core_api.read_namespaced_config_map(
                name="keycloak-config",
                namespace="keycloak"
            )
            self.domain = cm.data.get("DOMAIN", "")
            if self.domain:
                logger.info(f"Getting domain from keycloak-config: {self.domain}")
        except Exception as e:
            logger.warning(f"Could not load domain from ConfigMap: {e}, using fallback")
            self.domain = "dev.karectl.org"

    def register_handlers(self):
        """ Register kopf handlers.
        """
        pass

    def shutdown(self):
        """ Cleanup on shutdown.
        """
        logger.info("ProjectSyncPlugin shutting down")

    def generate_project_crd(self, project_data, quota_tier):
        """ Generate project CRD from the data.
        """
        project_info = project_data.get("project", {})
        project_name = project_info.get("name", "unknown")

        quota_config = self.quota_tiers.get(quota_tier, self.quota_tiers["medium"])
        project_spec = ProjectSpec(
            description=project_info.get("description", f"{project_name} research project"),
            apps=[
                AppConfig(
                    name="jupyterhub",
                    type="jupyterhub",
                    url=f"https://jupyter.{self.domain}/hub",
                    config={
                        "workspace": f"/{project_name}",
                        "quota": f"{quota_config['requests_cpu']}CPU",
                    },
                ),
                AppConfig(
                    name="guacamole",
                    type="vdi",
                    url=f"https://guacamole.{self.domain}",
                    config={
                        "protocol": "rdp",
                        "resolution": "1920x1080",
                        "desktop": "ubuntu-mate",
                    },
                ),
                AppConfig(
                    name="gitea",
                    type="gitea",
                    url=f"https://gitea.{self.domain}",
                    config={},
                ),
            ],
            profiles=[
                {
                    "display_name": f"{project_name.title()} Workspace 1",
                    "description": f"Primary workspace for {project_name} project",
                    "slug": f"{project_name}-ws1",
                    "kubespawner_override": {
                        "image": "ghcr.io/karectl/marimo-notebook-workspace:latest",
                        "env": {
                            "PROJECT_NAME": project_name,
                            "WORKSPACE": f"/{project_name}/ws1",
                        },
                    },
                }
            ],
            resource_quota=ResourceQuotaConfig(**quota_config),
            storage=StorageConfig(
                storage_class="rwo-default",
                default_vdi_size="2Gi",
                default_notebook_size="2Gi",
            ),
        )

        return {
            "apiVersion": "research.karectl.io/v1alpha1",
            "kind": "Project",
            "metadata": {
                "name": project_name,
                "labels": {
                    "karectl.io/project-id": project_info.get("id", ""),
                    "karectl.io/source": "cr8tor-projects",
                    "karectl.io/reference": project_info.get("reference", ""),
                },
            },
            "spec": project_spec.model_dump(exclude_none=True),
        }

    def generate_user_crd(self, project_data):
        """ Generate User CRD from requesting agent.
        """
        project_info = project_data.get("project", {})
        requesting_agent = project_data.get("requesting_agent", {})

        if not requesting_agent or not requesting_agent.get("name"):
            return None

        project_name = project_info.get("name", "unknown")
        username = requesting_agent["name"].lower().replace(" ", "-")
        affiliation = requesting_agent.get("affiliation", {})
        email = affiliation.get("name", f"{username}@example.com")

        user_spec = UserSpec(
            username=username,
            email=email,
            enabled=True,
            groups=[f"{project_name}-admin"],
            keycloak={"email_verified": True},
            jupyterhub={
                "workspace": project_name,
                "compute_quota": "2CPU,8Gi",
            },
            karectl={
                "user_id": f"{username}_{project_name}",
                "affiliation": affiliation.get("name", ""),
                "affiliation_url": affiliation.get("url", ""),
            },
        )

        return {
            "apiVersion": "identity.karectl.io/v1alpha1",
            "kind": "User",
            "metadata": {
                "name": username,
                "labels": {
                    "karectl.io/source": "cr8tor-projects",
                    "karectl.io/project": project_name,
                },
            },
            "spec": user_spec.model_dump(exclude_none=True),
        }

    def generate_group_crds(self, project_data):
        """ Generate Group CRDs.
        """
        project_info = project_data.get("project", {})
        requesting_agent = project_data.get("requesting_agent", {})
        project_name = project_info.get("name", "unknown")

        admin_username = None
        if requesting_agent and requesting_agent.get("name"):
            admin_username = requesting_agent["name"].lower().replace(" ", "-")

        groups = []
        parent_spec = GroupSpec(
            description=f"{project_name.title()} parent group",
            projects=[project_name],
            subgroups=[f"{project_name}-admin", f"{project_name}-analyst"],
        )

        groups.append({
            "apiVersion": "identity.karectl.io/v1alpha1",
            "kind": "Group",
            "metadata": {
                "name": project_name,
                "labels": {
                    "karectl.io/source": "cr8tor-projects",
                    "karectl.io/project": project_name,
                },
            },
            "spec": parent_spec.model_dump(exclude_none=True),
        })

        # Admin group
        admin_spec = GroupSpec(
            description=f"Admins of {project_name} project",
            projects=[project_name],
            members=[admin_username] if admin_username else [],
        )
        groups.append({
            "apiVersion": "identity.karectl.io/v1alpha1",
            "kind": "Group",
            "metadata": {
                "name": f"{project_name}-admin",
                "labels": {
                    "karectl.io/source": "cr8tor-projects",
                    "karectl.io/project": project_name,
                    "karectl.io/role": "admin",
                },
            },
            "spec": admin_spec.model_dump(exclude_none=True),
        })

        # Analyst group
        analyst_spec = GroupSpec(
            description=f"Analysts of {project_name} project",
            projects=[project_name],
            members=[],
        )
        groups.append({
            "apiVersion": "identity.karectl.io/v1alpha1",
            "kind": "Group",
            "metadata": {
                "name": f"{project_name}-analyst",
                "labels": {
                    "karectl.io/source": "cr8tor-projects",
                    "karectl.io/project": project_name,
                    "karectl.io/role": "analyst",
                },
            },
            "spec": analyst_spec.model_dump(exclude_none=True),
        })

        return groups

    def apply_crd(self, crd, merge_members=True):
        """ Apply CRD to k8s cluster
        """
        try:
            group, version = crd["apiVersion"].split("/")
            kind = crd["kind"]
            name = crd["metadata"]["name"]
            plural = kind.lower() + "s"

            # Check for resource
            try:
                existing = self.custom_api.get_namespaced_custom_object(
                    group=group,
                    version=version,
                    namespace=self.target_namespace,
                    plural=plural,
                    name=name,
                )
                # Groups and handling members
                if kind == "Group" and merge_members:
                    existing_members = existing.get("spec", {}).get("members", [])
                    new_members = crd.get("spec", {}).get("members", [])
                    merged_members = list(set(existing_members + new_members))
                    crd["spec"]["members"] = merged_members
                    logger.info(f"Merging {kind}/{name} members: {existing_members} + {new_members} = {merged_members}")

                # Update existing
                logger.info(f"Updating existing {kind}/{name}")
                self.custom_api.patch_namespaced_custom_object(
                    group=group,
                    version=version,
                    namespace=self.target_namespace,
                    plural=plural,
                    name=name,
                    body=crd,
                )
            except ApiException as e:
                if e.status == 404:
                    # Create new ones
                    logger.info(f"Creating new {kind}/{name}")
                    self.custom_api.create_namespaced_custom_object(
                        group=group,
                        version=version,
                        namespace=self.target_namespace,
                        plural=plural,
                        body=crd,
                    )
                else:
                    raise

            return True

        except Exception as e:
            logger.error(f"Failed to apply {crd['kind']}/{crd['metadata']['name']}: {e}")
            return False

    def sync_project_from_data(self, project_data):
        """ Sync a project from pre-parsed data

        Args:
            project_data: Parsed project data
        """
        project_info = project_data.get("project", {})
        project_name = project_info.get("name", "unknown")

        logger.info(f"Syncing project from data: {project_name}")

        # Generate CRDs
        try:
            project_crd = self.generate_project_crd(project_data, self.default_quota_tier)
            user_crd = self.generate_user_crd(project_data)
            group_crds = self.generate_group_crds(project_data)
        except Exception as e:
            logger.error(f"Failed to generate CRDs for {project_name}: {e}")
            return {"status": "error", "project": project_name, "error": str(e)}

        # Apply in the order we need, Users, Groups and Projects
        results = {}
        success = True

        if user_crd:
            if not self.apply_crd(user_crd):
                success = False
                results["user"] = "failed"
            else:
                results["user"] = "ok"

        for group_crd in group_crds:
            group_name = group_crd["metadata"]["name"]
            if not self.apply_crd(group_crd):
                success = False
                results[f"group_{group_name}"] = "failed"
            else:
                results[f"group_{group_name}"] = "ok"

        if not self.apply_crd(project_crd):
            success = False
            results["project"] = "failed"
        else:
            results["project"] = "ok"

        if success:
            logger.info(f"Successfully synced project: {project_name}")
            return {"status": "success", "project": project_name, "results": results}
        else:
            logger.warning(f"Partially synced project: {project_name}")
            return {"status": "partial", "project": project_name, "results": results}



# Plugin instance
plugin = ProjectSyncPlugin()


@kopf.on.create("v1", "configmap", labels={"karectl.io/trigger": "project-sync"})
@kopf.on.update("v1", "configmap", labels={"karectl.io/trigger": "project-sync"})
def project_sync_trigger(body, meta, **kwargs):
    """ Triggered when a ConfigMap with label karectl.io/trigger=project-sync is created/updated.

    Expected ConfigMap data:
        project_data: JSON string containing parsed project.toml data
    """
    import json

    logger.info("Project sync triggered via ConfigMap")

    # Get project data from ConfigMap
    data = body.get("data", {})
    project_data_json = data.get("project_data")

    if not project_data_json:
        logger.error("No project_data found in ConfigMap")
        kopf.warn(meta, reason="SyncFailed", message="Missing project_data in ConfigMap")
        return

    try:
        # Parse JSON data
        project_data = json.loads(project_data_json)
        project_name = project_data.get("project", {}).get("name", "unknown")

        logger.info(f"Syncing project: {project_name}")
        # Trigger the sync with parsed data
        result = plugin.sync_project_from_data(project_data)
        logger.info(f"Sync result: {result}")
        kopf.info(meta, reason="SyncCompleted", message=f"Project {project_name} sync: {result.get('status')}")

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in project_data: {e}")
        kopf.warn(meta, reason="SyncFailed", message=f"Invalid JSON data: {e}")
    except Exception as e:
        logger.error(f"Error syncing project: {e}")
        kopf.warn(meta, reason="SyncFailed", message=f"Sync error: {e}")
