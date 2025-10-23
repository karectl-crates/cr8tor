#!/usr/bin/env python3
"""Test script for the new cr8tor operator system."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_crd_registry():
    """Test CRD registry functionality."""
    print("Testing CRD Registry...")

    from cr8tor.crd.registry import CRDRegistry

    registry = CRDRegistry()
    registry.discover_models()

    models = registry.get_all_models()
    print(f"Discovered {len(models)} CRD models")

    for key, model_info in models.items():
        print(f"    - {key}: {model_info['kind']} ({model_info['group']})")

    return len(models) > 0


def test_crd_generation():
    """Test CRD generation."""
    print("Testing CRD Generation...")

    from cr8tor.crd.generator import KareCRDManager

    manager = KareCRDManager()
    success = manager.generate_all_crds(force=True)

    if success:
        print("CRDs generated successfully")

        # Validate generated CRDs
        if manager.validate_generated_crds():
            print("Generated CRDs are valid")
            return True
        else:
            print("Generated CRDs validation failed")
            return False
    else:
        print("CRD generation failed")
        return False


def test_plugin_system():
    """Test plugin system."""
    print("Testing Plugin System...")

    from cr8tor.plugins.registry import PluginRegistry

    plugin_registry = PluginRegistry()
    discovered_count = plugin_registry.discover_plugins(builtin_only=True)

    print(f"Discovered {discovered_count} plugins")

    if discovered_count == 0:
        print("No plugins discovered")
        return False

    # Initialize plugins
    results = plugin_registry.initialise_all_plugins()
    successful_count = sum(1 for success in results.values() if success)

    print(f"Initialised {successful_count}/{discovered_count} plugins")

    # Get plugin health status
    health_status = plugin_registry.get_plugins_health_status()
    for name, status in health_status.items():
        print(f"    - {name}: {status['status']}")

    return successful_count > 0


def test_pydantic_models():
    """Test pydantic model imports and schemas."""
    print("Testing Pydantic Models...")

    try:
        from cr8tor.models.identity import UserSpec, GroupSpec, KeycloakClientSpec
        from cr8tor.models.workspaces import VDIInstanceSpec

        models = [UserSpec, GroupSpec, KeycloakClientSpec, VDIInstanceSpec]

        for model in models:
            schema = model.model_json_schema()
            print(f"{model.__name__}: {len(schema.get('properties', {}))} fields")

            if hasattr(model, "_crd_group"):
                print(f" - CRD: {model._crd_group}/{model._crd_kind}")
            else:
                print(" - Missing CRD metadata")
                return False

        return True

    except Exception as e:
        print(f"Model import/schema error: {e}")
        return False


def main():
    """Run all tests."""
    print("Testing Cr8tor Operator System")
    print("=" * 50)

    tests = [
        ("Pydantic Models", test_pydantic_models),
        ("CRD Registry", test_crd_registry),
        ("CRD Generation", test_crd_generation),
        ("Plugin System", test_plugin_system),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"{test_name} failed with exception: {e}")
            results.append((test_name, False))

        print()

    # Summary
    print("Test Results:")

    passed = 0
    for test_name, success in results:
        status = "PASS" if success else "FAIL"
        print(f"{status} {test_name}")
        if success:
            passed += 1

    print(f"\n{passed}/{len(results)} tests passed")

    if passed == len(results):
        print("All tests passed!")
        sys.exit(0)
    else:
        print("Some tests failed. Please fix issues before proceeding.")
        sys.exit(1)


if __name__ == "__main__":
    main()
