import kopf
import logging
import kubernetes
from cr8tor.identity import identity_handler  # noqa: F401
from cr8tor.vdi import vdi_handler  # noqa: F401

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@kopf.on.startup()
def startup_fn(settings: kopf.OperatorSettings, **kwargs):
    """Configure the unified operator with optimal settings."""
    logger.info("Cr8tor Operator is starting up.")

    # Load Kubernetes configuration
    try:
        kubernetes.config.load_incluster_config()
        logger.info("Loaded in-cluster Kubernetes config")
    except kubernetes.config.ConfigException:
        kubernetes.config.load_kube_config()
        logger.info("Loaded local Kubernetes config")

    # Configure operator settings for optimal performance
    settings.batching.worker_limit = 3  # Balanced between identity (1) and vdi (5)
    settings.posting.enabled = False  # Reduce K8s event noise
    settings.watching.server_timeout = 60
    settings.posting.level = logging.INFO

    logger.info("Loaded handlers: identity, vdi")
    logger.info(f"Worker limit: {settings.batching.worker_limit}")


@kopf.on.cleanup()
def cleanup_fn(**kwargs):
    logger.info("Cr8tor Operator is shutting down.")


if __name__ == "__main__":
    try:
        kopf.run()
    except KeyboardInterrupt:
        logger.info("Operator stopped by user")
    except Exception as e:
        logger.error(f"Operator failed: {e}")
        raise
