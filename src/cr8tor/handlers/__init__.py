"""Handler modules for cr8tor operator."""

# Import existing handlers to ensure they're available for plugins
from . import identity_handler
from . import vdi_handler
from . import project_sync_handler

__all__ = ["identity_handler", "vdi_handler", "project_sync_handler"]
