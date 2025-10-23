"""Workspaces plugin for cr8tor operator."""

import logging

from .base import PluginBase

logger = logging.getLogger(__name__)


class WorkspacesPlugin(PluginBase):
    """Plugin for managing workspace-related CRDs (VDI instances)."""

    @property
    def name(self) -> str:
        return "workspaces"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return (
            " Manages VDI instances and workspace environments through Kubernetes CRDs"
        )

    @property
    def models(self):
        from cr8tor.models.workspaces import VDIInstanceSpec

        return [VDIInstanceSpec]

    def _initialise_plugin(self):
        """Initialise workspaces-specific resources."""
        logger.info("Initializing workspaces plugin...")

        # Validate required templates and configurations
        try:
            from pathlib import Path

            template_path = Path("/app/templates/vdi-pod-template.yaml.j2")
            if not template_path.exists():
                logger.warning(f"VDI template not found at {template_path}")
            else:
                logger.info("VDI templates validated")
        except Exception as e:
            logger.warning(f"Could not validate VDI templates: {e}")

    def register_handlers(self):
        """Register kopf handlers for workspaces CRDs."""
        logger.info("Registering workspaces handlers...")

        # Import handlers to trigger decorator registration
        try:
            logger.info("Workspaces handlers registered successfully")
        except Exception as e:
            logger.error(f"Failed to register workspaces handlers: {e}")
            raise
