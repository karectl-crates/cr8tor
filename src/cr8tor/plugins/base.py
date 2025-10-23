"""Base plugin architecture for cr8tor operator."""

from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class PluginBase(ABC):
    """Base class for all cr8tor plugins."""

    def __init__(self):
        self._initialised = False
        self._models_registered = False

    @property
    @abstractmethod
    def name(self):
        """Unique name for this plugin."""
        pass

    @property
    @abstractmethod
    def version(self):
        """Plugin version."""
        pass

    @property
    @abstractmethod
    def description(self):
        """Human-readable description of what this plugin does."""
        pass

    @property
    @abstractmethod
    def models(self):
        """Return list of CRD models this plugin provides."""
        pass

    def initialise(self):
        """Initialise the plugin. Called once during operator startup.

        Returns:
            bool: True if initialisation successful, False otherwise
        """
        if self._initialised:
            logger.warning(f"Plugin {self.name} already initialised")
            return True

        try:
            logger.info(f"Initialising plugin: {self.name} v{self.version}")

            # Register models
            if not self._models_registered:
                self._register_models()
                self._models_registered = True

            # Custom initialization logic
            self._initialise_plugin()

            self._initialised = True
            logger.info(f"Plugin {self.name} initialised successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialise plugin {self.name}: {e}")
            return False

    def _register_models(self):
        """Register this plugin's models with the CRD registry."""
        from cr8tor.crd.registry import CRDRegistry

        CRDRegistry()
        for model in self.models:
            if not hasattr(model, "_crd_group"):
                logger.warning(
                    f"Model {model.__name__} not properly decorated with @CRDRegistry.register"
                )
                continue

            logger.debug(f"Model {model.__name__} registered by plugin {self.name}")

    def _initialise_plugin(self):
        """Override this method for custom plugin initialization logic."""
        pass

    def shutdown(self):
        """Cleanup plugin resources. Called during operator shutdown."""
        if not self._initialised:
            return

        try:
            logger.info(f"Shutting down plugin: {self.name}")
            self._shutdown_plugin()
            self._initialised = False
        except Exception as e:
            logger.error(f"Error shutting down plugin {self.name}: {e}")

    def _shutdown_plugin(self):
        """Override this method for custom plugin shutdown logic."""
        pass

    @abstractmethod
    def register_handlers(self):
        """Register kopf handlers for this plugin.

        This method should import and register all kopf event handlers
        for the CRDs managed by this plugin.
        """
        pass

    def get_health_status(self):
        """Get health status of this plugin."""
        return {
            "name": self.name,
            "version": self.version,
            "initialised": self._initialised,
            "models_count": len(self.models),
            "status": "healthy" if self._initialised else "not_initialised",
        }

    def get_metadata(self):
        """Get plugin metadata."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "models": [model.__name__ for model in self.models],
        }
