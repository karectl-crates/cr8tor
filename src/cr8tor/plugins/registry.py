"""Plugin registry for discovering and managing plugins."""

import importlib
import logging

from .base import PluginBase

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Registry for discovering and managing cr8tor plugins."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._plugins = {}
            cls._instance._initialised = False
        return cls._instance

    def __init__(self):
        if not self._initialised:
            self._plugins = {}
            self._initialised = True

    def discover_plugins(self, builtin_only=False):
        """Discover and load all available plugins.

        Args:
            builtin_only: If True, only load built-in plugins

        Returns:
            int: Number of plugins discovered
        """
        logger.info("Discovering plugins...")

        # Always load built-in plugins
        builtin_count = self._load_builtin_plugins()

        external_count = 0
        if not builtin_only:
            # Load external plugins via entry points
            external_count = self._load_external_plugins()

        total_count = builtin_count + external_count
        logger.info(
            f"Discovered {total_count} plugins ({builtin_count} builtin, {external_count} external)"
        )

        return total_count

    def _load_builtin_plugins(self):
        """Load built-in plugins from cr8tor.plugins package."""
        builtin_plugins = [
            "cr8tor.plugins.identity",
            "cr8tor.plugins.workspaces",
            "cr8tor.plugins.project_sync",
        ]

        loaded_count = 0
        for plugin_module in builtin_plugins:
            try:
                module = importlib.import_module(plugin_module)

                # Look for plugin class in module
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, PluginBase)
                        and attr != PluginBase
                    ):
                        plugin_instance = attr()
                        self.register_plugin(plugin_instance)
                        loaded_count += 1
                        break

            except ImportError as e:
                logger.warning(f"Could not load builtin plugin {plugin_module}: {e}")
            except Exception as e:
                logger.error(f"Error loading builtin plugin {plugin_module}: {e}")

        return loaded_count

    def _load_external_plugins(self):
        """Load external plugins via Python entry points."""
        loaded_count = 0

        try:
            import pkg_resources

            for entry_point in pkg_resources.iter_entry_points("cr8tor_plugins"):
                try:
                    plugin_class = entry_point.load()

                    if not issubclass(plugin_class, PluginBase):
                        logger.error(
                            f"Plugin {entry_point.name} does not inherit from PluginBase"
                        )
                        continue

                    plugin_instance = plugin_class()
                    self.register_plugin(plugin_instance)
                    loaded_count += 1

                    logger.info(f"Loaded external plugin: {plugin_instance.name}")

                except Exception as e:
                    logger.error(
                        f"Failed to load external plugin {entry_point.name}: {e}"
                    )

        except ImportError:
            logger.debug(
                "pkg_resources not available, skipping external plugin discovery"
            )

        return loaded_count

    def register_plugin(self, plugin):
        """Register a plugin instance.

        Args:
            plugin: Plugin instance to register

        Returns:
            bool: True if registration successful, False otherwise
        """
        if not isinstance(plugin, PluginBase):
            logger.error(f"Plugin must inherit from PluginBase: {type(plugin)}")
            return False

        plugin_name = plugin.name

        if plugin_name in self._plugins:
            existing_version = self._plugins[plugin_name].version
            new_version = plugin.version
            logger.warning(
                f"Plugin {plugin_name} already registered (existing: {existing_version}, new: {new_version})"
            )
            return False

        self._plugins[plugin_name] = plugin
        logger.debug(f"Registered plugin: {plugin_name} v{plugin.version}")
        return True

    def initialise_all_plugins(self):
        """Initialise all registered plugins.

        Returns:
            Dict[str, bool]: Map of plugin names to initialization success status
        """
        logger.info("Initializing all plugins...")

        results = {}
        for plugin_name, plugin in self._plugins.items():
            try:
                success = plugin.initialise()
                results[plugin_name] = success

                if success:
                    logger.info(f"Plugin {plugin_name} initialised successfully")
                else:
                    logger.error(f"Plugin {plugin_name} initialization failed")

            except Exception as e:
                logger.error(f"Exception initializing plugin {plugin_name}: {e}")
                results[plugin_name] = False

        successful_count = sum(1 for success in results.values() if success)
        logger.info(
            f"initialised {successful_count}/{len(self._plugins)} plugins successfully"
        )

        return results

    def register_all_handlers(self):
        """Register kopf handlers for all initialised plugins."""
        logger.info("Registering handlers for all plugins...")

        for plugin_name, plugin in self._plugins.items():
            if not plugin._initialised:
                logger.warning(
                    f"Skipping handler registration for uninitialised plugin: {plugin_name}"
                )
                continue

            try:
                plugin.register_handlers()
                logger.debug(f"Registered handlers for plugin: {plugin_name}")
            except Exception as e:
                logger.error(
                    f"Failed to register handlers for plugin {plugin_name}: {e}"
                )

    def shutdown_all_plugins(self):
        """Shutdown all plugins."""
        logger.info("Shutting down all plugins...")

        for plugin_name, plugin in self._plugins.items():
            try:
                plugin.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down plugin {plugin_name}: {e}")

    def get_plugin(self, name: str):
        """Get a plugin by name."""
        return self._plugins.get(name)

    def get_all_plugins(self):
        """Get all registered plugins."""
        return self._plugins.copy()

    def list_plugin_names(self):
        """Get list of all plugin names."""
        return list(self._plugins.keys())

    def get_plugins_health_status(self):
        """Get health status of all plugins."""
        return {
            name: plugin.get_health_status() for name, plugin in self._plugins.items()
        }

    def get_plugins_metadata(self):
        """Get metadata for all plugins."""
        return [plugin.get_metadata() for plugin in self._plugins.values()]
