"""GitOps CRD management and generation system."""

import hashlib
import json
import logging
from pathlib import Path
import yaml

from .registry import CRDRegistry

logger = logging.getLogger(__name__)


class OpenAPIConverter:
    """Convert pydantic schemas to OpenAPI v3 compatible schemas for CRDs."""

    @staticmethod
    def convert_schema(pydantic_schema):
        """Convert pydantic JSON schema to OpenAPI v3 schema for Kubernetes CRDs."""
        openapi_schema = {"type": "object", "properties": {}}

        if "properties" in pydantic_schema:
            openapi_schema["properties"] = OpenAPIConverter._convert_properties(
                pydantic_schema["properties"], pydantic_schema.get("$defs", {})
            )

        if "required" in pydantic_schema:
            openapi_schema["required"] = pydantic_schema["required"]

        return openapi_schema

    @staticmethod
    def _convert_properties(properties, property_defs):
        """Convert properties recursively."""
        converted = {}

        for prop_name, prop_schema in properties.items():
            converted[prop_name] = OpenAPIConverter._convert_property(
                prop_schema, property_defs
            )

        return converted

    @staticmethod
    def _convert_property(prop_schema, defs):
        """Convert a single property schema."""
        # Handle $ref (references to definitions)
        if "$ref" in prop_schema:
            ref_path = prop_schema["$ref"]
            if ref_path.startswith("#/$defs/"):
                def_name = ref_path.replace("#/$defs/", "")
                if def_name in defs:
                    return OpenAPIConverter._convert_property(defs[def_name], defs)

        # Handle arrays
        if prop_schema.get("type") == "array":
            converted = {"type": "array"}
            if "items" in prop_schema:
                converted["items"] = OpenAPIConverter._convert_property(
                    prop_schema["items"], defs
                )
            return converted

        # Handle objects
        if prop_schema.get("type") == "object":
            converted = {"type": "object"}
            if "properties" in prop_schema:
                converted["properties"] = OpenAPIConverter._convert_properties(
                    prop_schema["properties"], defs
                )
            if "required" in prop_schema:
                converted["required"] = prop_schema["required"]
            # Allow additional properties for flexible schemas
            converted["additionalProperties"] = True
            return converted

        # Handle basic types
        result = {}
        if "type" in prop_schema:
            result["type"] = prop_schema["type"]
        if "description" in prop_schema:
            result["description"] = prop_schema["description"]
        if "default" in prop_schema:
            result["default"] = prop_schema["default"]
        if "enum" in prop_schema:
            result["enum"] = prop_schema["enum"]

        # If no type specified, assume object
        if not result.get("type"):
            result["type"] = "object"
            result["additionalProperties"] = True

        return result


class KareCRDManager:
    """Manages CRD generation for GitOps workflows."""

    def __init__(self, output_dir=None):
        self.output_dir = output_dir or Path("crds/generated")
        self.registry = CRDRegistry()
        self.converter = OpenAPIConverter()

    def generate_all_crds(self, force=False):
        """Generate CRDs only if models changed.

        Returns:
            bool: True if CRDs were generated/updated, False if no changes needed
        """
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Discover all models
        self.registry.discover_models()
        # Check if models have changed
        current_hash = self._calculate_models_hash()
        hash_file = self.output_dir / ".models_hash"

        if not force and hash_file.exists():
            stored_hash = hash_file.read_text().strip()
            if stored_hash == current_hash:
                logger.info("CRD models unchanged, skipping generation")
                return False

        logger.info("Generating CRDs from pydantic models...")

        # Generate CRDs
        models = self.registry.get_all_models()
        if not models:
            logger.warning("No CRD models found to generate")
            return False

        generated_files = []

        for model_key, model_info in models.items():
            try:
                crd_def = self._generate_crd_definition(model_info)
                filename = f"{crd_def['metadata']['name']}.yaml"
                file_path = self.output_dir / filename

                with open(file_path, "w") as f:
                    yaml.dump(crd_def, f, default_flow_style=False, sort_keys=False)

                generated_files.append(filename)
                logger.info(f"Generated CRD: {filename}")

            except Exception as e:
                logger.error(f"Failed to generate CRD for {model_key}: {e}")
                raise

        # Generate kustomization.yaml
        self._generate_kustomization(generated_files)

        # Update hash file
        hash_file.write_text(current_hash)

        logger.info(f"Generated {len(generated_files)} CRD files")
        return True

    def _generate_crd_definition(self, model_info):
        """Generate a single CRD definition from model info."""
        model_class = model_info["model"]
        group = model_info["group"]
        version = model_info["version"]
        kind = model_info["kind"]
        plural = model_info["plural"]
        singular = model_info["singular"]
        scope = model_info["scope"]

        # Get pydantic schema
        try:
            schema = model_class.model_json_schema()
        except Exception as e:
            raise ValueError(
                f"Failed to generate schema for {model_class.__name__}: {e}"
            )

        # Convert to OpenAPI schema
        openapi_schema = self.converter.convert_schema(schema)

        # Create full CRD structure
        crd = {
            "apiVersion": "apiextensions.k8s.io/v1",
            "kind": "CustomResourceDefinition",
            "metadata": {"name": f"{plural}.{group}"},
            "spec": {
                "group": group,
                "versions": [
                    {
                        "name": version,
                        "served": True,
                        "storage": True,
                        "schema": {
                            "openAPIV3Schema": {
                                "type": "object",
                                "properties": {
                                    "spec": openapi_schema,
                                    "status": {
                                        "type": "object",
                                        "properties": {
                                            "phase": {"type": "string"},
                                            "conditions": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "type": {"type": "string"},
                                                        "status": {"type": "string"},
                                                        "reason": {"type": "string"},
                                                        "message": {"type": "string"},
                                                        "lastTransitionTime": {
                                                            "type": "string",
                                                            "format": "date-time",
                                                        },
                                                    },
                                                    "required": [
                                                        "type",
                                                        "status",
                                                        "reason",
                                                        "message",
                                                    ],
                                                },
                                            },
                                            "observedGeneration": {"type": "integer"},
                                        },
                                        "additionalProperties": True,
                                    },
                                },
                                "required": ["spec"],
                            }
                        },
                        "subresources": {"status": {}},
                    }
                ],
                "scope": scope,
                "names": {
                    "plural": plural,
                    "singular": singular,
                    "kind": kind,
                    "shortNames": [singular[:3]],
                },
            },
        }

        return crd

    def _generate_kustomization(self, filenames):
        """Generate kustomization.yaml for all CRDs."""
        kustomization = {
            "apiVersion": "kustomize.config.k8s.io/v1beta1",
            "kind": "Kustomization",
            "resources": sorted(filenames),
        }

        kustomization_path = self.output_dir / "kustomization.yaml"
        with open(kustomization_path, "w") as f:
            yaml.dump(kustomization, f, default_flow_style=False)

        logger.info("Generated kustomization.yaml")

    def _calculate_models_hash(self):
        """Calculate hash of all model definitions for change detection."""
        # Discover models first
        self.registry.discover_models()
        models = self.registry.get_all_models()

        # Create representation
        model_data = {}
        for model_key, model_info in sorted(models.items()):
            model_class = model_info["model"]
            try:
                schema = model_class.model_json_schema()
                model_data[model_key] = {
                    "schema": schema,
                    "group": model_info["group"],
                    "version": model_info["version"],
                    "kind": model_info["kind"],
                    "scope": model_info["scope"],
                }
            except Exception as e:
                logger.warning(f"Could not generate schema for {model_key}: {e}")
                continue

        # Calculate hash
        model_json = json.dumps(model_data, sort_keys=True)
        return hashlib.sha256(model_json.encode()).hexdigest()

    def apply_crds_to_cluster(self, memory_only: bool = True) -> bool:
        """Apply CRDs directly to Kubernetes cluster (for runtime operation).

        Args:
            memory_only: If True, generate CRDs only in memory without creating files
        """
        try:
            from kubernetes import client, config
            from kubernetes.config import ConfigException

            # Load kubernetes config
            try:
                config.load_incluster_config()
            except ConfigException:
                config.load_kube_config()

            api_client = client.ApiextensionsV1Api()

            # Generate CRDs in memory
            self.registry.discover_models()
            models = self.registry.get_all_models()

            if not models:
                logger.warning("No CRD models found for in-memory generation")
                return False

            applied_count = 0
            for model_key, model_info in models.items():
                try:
                    crd_def = self._generate_crd_definition(model_info)
                    crd_name = crd_def["metadata"]["name"]

                    # Try to get existing CRD
                    try:
                        existing = api_client.read_custom_resource_definition(crd_name)
                        # Update existing CRD
                        crd_def["metadata"]["resourceVersion"] = (
                            existing.metadata.resource_version
                        )
                        api_client.replace_custom_resource_definition(
                            name=crd_name, body=crd_def
                        )
                        logger.info(f"Updated CRD in-memory: {crd_name}")
                    except client.exceptions.ApiException as e:
                        if e.status == 404:
                            # Create new CRD
                            api_client.create_custom_resource_definition(body=crd_def)
                            logger.info(f"Created CRD in-memory: {crd_name}")
                        else:
                            raise

                    applied_count += 1

                except Exception as e:
                    logger.error(f"Failed to apply CRD {model_key}: {e}")

            logger.info(
                f"Applied {applied_count} CRDs to cluster (memory-only: {memory_only})"
            )
            return applied_count > 0

        except Exception as e:
            logger.error(f"Failed to apply CRDs to cluster: {e}")
            return False

    def get_crds_as_dict(self):
        """Generate all CRDs as in-memory dictionary objects.

        Returns:
            Dict mapping CRD names to their definitions
        """
        self.registry.discover_models()
        models = self.registry.get_all_models()

        crds = {}
        for model_key, model_info in models.items():
            try:
                crd_def = self._generate_crd_definition(model_info)
                crd_name = crd_def["metadata"]["name"]
                crds[crd_name] = crd_def
            except Exception as e:
                logger.error(f"Failed to generate in-memory CRD for {model_key}: {e}")

        return crds

    def validate_generated_crds(self):
        """Validate that generated CRDs are valid Kubernetes resources."""
        if not self.output_dir.exists():
            logger.error("CRD output directory does not exist")
            return False

        crd_files = list(self.output_dir.glob("*.yaml"))
        # Exclude kustomization.yaml as it's not a CRD
        crd_files = [f for f in crd_files if f.name != "kustomization.yaml"]

        if not crd_files:
            logger.error("No CRD files found to validate")
            return False

        valid_count = 0
        for crd_file in crd_files:
            try:
                with open(crd_file, "r") as f:
                    crd_def = yaml.safe_load(f)

                # Basic validation
                if not isinstance(crd_def, dict):
                    logger.error(f"Invalid YAML in {crd_file}")
                    continue

                required_fields = ["apiVersion", "kind", "metadata", "spec"]
                if not all(field in crd_def for field in required_fields):
                    logger.error(f"Missing required fields in {crd_file}")
                    continue

                if crd_def["kind"] != "CustomResourceDefinition":
                    logger.error(f"Not a CRD: {crd_file}")
                    continue

                valid_count += 1
                logger.debug(f"Valid CRD: {crd_file}")

            except Exception as e:
                logger.error(f"Failed to validate {crd_file}: {e}")

        logger.info(f"Validated {valid_count}/{len(crd_files)} CRD files")
        return valid_count == len(crd_files)
