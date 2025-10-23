import kopf
import logging
import kubernetes
import os

from cr8tor.plugins.registry import PluginRegistry
from cr8tor.crd.generator import KareCRDManager

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Global plugin registry instance
plugin_registry = None


@kopf.on.startup()
def startup_fn(settings: kopf.OperatorSettings, **kwargs):
    """Configure the unified operator with plugin system."""
    global plugin_registry

    logger.info("Cr8tor Operator is starting up...")

    # Load Kubernetes configuration
    try:
        kubernetes.config.load_incluster_config()
        logger.info("Loaded in-cluster Kubernetes config")
    except kubernetes.config.ConfigException:
        try:
            kubernetes.config.load_kube_config()
            logger.info("Loaded local Kubernetes config")
        except Exception as e:
            logger.warning(f"Could not load Kubernetes config: {e}")

    # Auto-apply CRDs if running in cluster
    if should_manage_crds():
        try:
            crd_manager = KareCRDManager()
            memory_only = not should_generate_crd_files()

            if memory_only:
                logger.info("Applying CRDs in memory-only mode (no YAML files)")
            else:
                logger.info("Generating CRD files and applying to cluster")
                crd_manager.generate_all_crds(force=True)

            if crd_manager.apply_crds_to_cluster(memory_only=memory_only):
                logger.info("CRDs applied to cluster successfully")
            else:
                logger.warning("No CRDs were applied to cluster")
        except Exception as e:
            logger.error(f"Failed to apply CRDs to cluster: {e}")

    # Initialise plugin system
    plugin_registry = PluginRegistry()

    # Discover plugins
    discovered_count = plugin_registry.discover_plugins()
    if discovered_count == 0:
        logger.error("No plugins discovered - operator will have no functionality")
        raise RuntimeError("No plugins available")

    # Initialise all plugins
    init_results = plugin_registry.initialise_all_plugins()
    successful_inits = sum(1 for success in init_results.values() if success)

    if successful_inits == 0:
        logger.error("No plugins initialized successfully")
        raise RuntimeError("Plugin initialization failed")

    # Register handlers from all plugins
    plugin_registry.register_all_handlers()

    # Configure operator settings
    settings.batching.worker_limit = int(os.getenv("WORKER_LIMIT", "5"))
    settings.posting.enabled = os.getenv("POSTING_ENABLED", "false").lower() == "true"
    settings.watching.server_timeout = int(os.getenv("SERVER_TIMEOUT", "60"))

    # Log startup summary
    plugin_names = list(init_results.keys())
    logger.info(f"Initialised plugins: {plugin_names}")
    logger.info(f"Worker limit: {settings.batching.worker_limit}")
    logger.info(f"Posting enabled: {settings.posting.enabled}")
    logger.info("Cr8tor Operator startup complete")


@kopf.on.cleanup()
def cleanup_fn(**kwargs):
    """Cleanup operator resources."""
    logger.info("Cr8tor Operator is shutting down...")

    global plugin_registry
    if plugin_registry:
        plugin_registry.shutdown_all_plugins()

    logger.info("Cr8tor Operator shutdown complete")


def should_manage_crds() -> bool:
    """Determine if operator should manage CRDs directly."""
    return os.getenv("MANAGE_CRDS", "true").lower() == "true"


def should_generate_crd_files() -> bool:
    """Determine if operator should generate CRD YAML files."""
    return os.getenv("GENERATE_CRD_FILES", "false").lower() == "true"


def main():
    try:
        kopf.run()
    except KeyboardInterrupt:
        logger.info("Operator stopped by user")
    except Exception as e:
        logger.error(f"Operator failed: {e}")
        raise


if __name__ == "__main__":
    main()
