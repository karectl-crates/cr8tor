import kopf
import logging
from cr8tor.identity import identity_handler  # noqa: F401
from cr8tor.vdi import vdi_handler  # noqa: F401

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@kopf.on.startup()
def startup_fn(**kwargs):
    logger.info("Cr8tor Operator is starting up.")


if __name__ == "__main__":
    kopf.run()
