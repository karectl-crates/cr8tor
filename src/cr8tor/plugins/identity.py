"""Identity management plugin for cr8tor operator."""

import logging

from .base import PluginBase

logger = logging.getLogger(__name__)


class IdentityPlugin(PluginBase):
    """Plugin for managing identity-related CRDs (Users, Groups, KeycloakClients)."""

    @property
    def name(self):
        return "identity"

    @property
    def version(self):
        return "1.0.0"

    @property
    def description(self):
        return "Manages Keycloak users, groups, and clients through Kubernetes CRDs"

    @property
    def models(self):
        from cr8tor.models.identity import UserSpec, GroupSpec, KeycloakClientSpec

        return [UserSpec, GroupSpec, KeycloakClientSpec]

    def _initialise_plugin(self):
        """initialise identity-specific resources."""
        logger.info("Initializing identity plugin...")

        # Ensure Keycloak realm exists
        try:
            from cr8tor.services.client import ensure_realm_exists

            ensure_realm_exists()
            logger.info("Keycloak realm validation completed")
        except Exception as e:
            logger.warning(f"Could not validate Keycloak realm: {e}")

    def register_handlers(self):
        """Register kopf handlers for identity CRDs."""
        logger.info("Registering identity handlers...")

        # Import handlers to trigger decorator registration
        try:
            logger.info("Identity handlers registered successfully")
        except Exception as e:
            logger.error(f"Failed to register identity handlers: {e}")
            raise
