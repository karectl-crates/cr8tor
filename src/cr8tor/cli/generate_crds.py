"""Generate CRD files from pydantic models."""

import argparse
import sys
from pathlib import Path
from cr8tor.crd.generator import KareCRDManager


def generate_crds_command(args):
    """Generate CRD YAML files."""
    output_dir = Path(args.output) if args.output else Path("crds/generated")

    manager = KareCRDManager(output_dir=output_dir)

    try:
        success = manager.generate_all_crds(force=args.force)

        if success:
            print(f"CRDs generated successfully in {output_dir}")

            if args.validate:
                if manager.validate_generated_crds():
                    print("CRD validation passed")
                else:
                    print("CRD validation failed")
                    return 1
        else:
            print("No CRDs generated (models unchanged)")

        return 0

    except Exception as e:
        print(f"Failed to generate CRDs: {e}")
        return 1


def add_generate_crds_parser(subparsers):
    """Add generate-crds subcommand to the CLI."""
    parser = subparsers.add_parser("generate-crds", help="Generate CRD YAML files")

    parser.add_argument(
        "-o", "--output", help="Output directory for CRDs (default: crds/generated)"
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Force regeneration even if models unchanged",
    )

    parser.add_argument(
        "--validate", action="store_true", help="Validate generated CRDs after creation"
    )

    parser.set_defaults(func=generate_crds_command)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate CRD files")
    add_generate_crds_parser(parser.add_subparsers())

    args = parser.parse_args()
    if hasattr(args, "func"):
        sys.exit(args.func(args))
    else:
        parser.print_help()
