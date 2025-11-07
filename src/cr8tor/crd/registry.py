"""CRD Registry system for automatic CRD discovery."""

import importlib
import pkgutil
import logging

logger = logging.getLogger(__name__)


class CRDRegistry:
    """Global registry forCRD models with auto-discovery."""

    _instance = None
    _initialised = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._models = {}
            cls._instance._initialised = False
        return cls._instance

    def __init__(self):
        if not self._initialised:
            self._models = {}
            self._initialised = True

    @classmethod
    def register(cls, group, version, kind, plural=None, scope="Namespaced"):
        """Decorator to register CRD models.

        Args:
            group: API group (e.g., 'identity.k8tre.io')
            version: API version (e.g., 'v1alpha1')
            kind: Kind name (e.g., 'User')
            plural: Plural name (defaults to kind.lower() + 's')
            scope: 'Namespaced' or 'Cluster'
        """

        def decorator(model_class):
            if not hasattr(model_class, "__annotations__"):
                raise ValueError(
                    f"CRD model {model_class.__name__} must have type annotations"
                )

            # Set CRD metadata on the class
            model_class._crd_group = group
            model_class._crd_version = version
            model_class._crd_kind = kind
            model_class._crd_plural = plural or f"{kind.lower()}s"
            model_class._crd_scope = scope

            # Register in singleton instance
            registry_instance = cls()
            key = f"{group}/{version}/{kind}"

            registry_instance._models[key] = {
                "model": model_class,
                "group": group,
                "version": version,
                "kind": kind,
                "plural": model_class._crd_plural,
                "scope": scope,
                "singular": kind.lower(),
            }

            logger.debug(f"Registered CRD: {key}")
            return model_class

        return decorator

    def discover_models(self, package_paths=None):
        """Auto-discover all CRD models in specified packages.

        Args:
            package_paths: List of package paths to search (e.g., ['cr8tor.models'])
        """
        if package_paths is None:
            package_paths = ["cr8tor.models"]

        for package_path in package_paths:
            try:
                self._discover_in_package(package_path)
            except ImportError as e:
                logger.warning(f"Could not discover models in {package_path}: {e}")

    def _discover_in_package(self, package_path):
        """Recursively discover models in a package."""
        try:
            package = importlib.import_module(package_path)
        except ImportError:
            logger.warning(f"Package {package_path} not found")
            return

        # Import all submodules
        if hasattr(package, "__path__"):
            for _, module_name, _ in pkgutil.iter_modules(package.__path__):
                full_module_name = f"{package_path}.{module_name}"
                try:
                    importlib.import_module(full_module_name)
                    logger.debug(f"Discovered models in {full_module_name}")
                except ImportError as e:
                    logger.warning(f"Could not import {full_module_name}: {e}")

    def get_all_models(self):
        """Get all registered CRD models."""
        return self._models.copy()

    def get_model_by_key(self, group, version, kind):
        """Get a specific CRD model by its key."""
        key = f"{group}/{version}/{kind}"
        return self._models.get(key)

    def get_models_by_group(self, group):
        """Get all models for a specific group."""
        return {
            key: model_info
            for key, model_info in self._models.items()
            if model_info["group"] == group
        }

    def list_registered_models(self):
        """List all registered model keys."""
        return list(self._models.keys())

    def clear_registry(self):
        """Clear all registered models (useful for testing)."""
        self._models.clear()

    def validate_model_schema(self, model_class):
        """Validate that a model can be converted to OpenAPI schema."""
        try:
            schema = model_class.model_json_schema()
            return "properties" in schema and isinstance(schema["properties"], dict)
        except Exception as e:
            logger.error(f"Schema validation failed for {model_class.__name__}: {e}")
            return False
