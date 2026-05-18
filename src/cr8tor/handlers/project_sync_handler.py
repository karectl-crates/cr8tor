""" Handler for project sync triggers via ConfigMap.
"""

import json
import logging
import kopf

logger = logging.getLogger(__name__)


def get_project_sync_plugin():
    """ Get the ProjectSyncPlugin.
    """
    from cr8tor.main import plugin_registry

    if not plugin_registry:
        logger.error("Plugin registry not initialised")
        return None

    return plugin_registry.get_plugin("project-sync")


@kopf.on.create("v1", "configmap", labels={"karectl.io/trigger": "project-sync"})
@kopf.on.update("v1", "configmap", labels={"karectl.io/trigger": "project-sync"})
def project_sync_trigger(body, meta, **kwargs):
    """ Triggered when a ConfigMap with label karectl.io/trigger=project-sync is created/updated.

    Expected ConfigMap data:
        project_data: JSON string containing parsed project.toml data
    """
    logger.info("Project sync triggered via ConfigMap")

    # Get plugin instance
    plugin = get_project_sync_plugin()
    if not plugin:
        logger.error("ProjectSyncPlugin not found in registry")
        kopf.warn(meta, reason="SyncFailed", message="ProjectSyncPlugin not available")
        return

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
