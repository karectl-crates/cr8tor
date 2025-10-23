import typer
from typing_extensions import Annotated
from cr8tor.cli.create import app as create_command
from cr8tor.cli.build import app as build_command
from cr8tor.cli.validate import app as validate_command
from cr8tor.cli.sign_off import app as sign_off_command
from cr8tor.cli.disclosure import app as disclosure_command
from cr8tor.cli.stage_transfer import app as stage_transfer_command
from cr8tor.cli.publish import app as publish_command

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

app = typer.Typer(
    help="Cr8tor: Research crate creation and Kubernetes operator",
    add_completion=False,
)

# Add existing crate CLI commands
app.add_typer(create_command)
app.add_typer(build_command)
app.add_typer(validate_command)
app.add_typer(sign_off_command)
app.add_typer(disclosure_command)
app.add_typer(stage_transfer_command)
app.add_typer(publish_command)


# Add operator commands
@app.command("operator")
def run_operator():
    """Run the Kubernetes operator (connects to cluster)."""
    from cr8tor.main import main

    main()


@app.command("generate-crds")
def generate_crds(
    output: Annotated[
        str, typer.Option("-o", "--output", help="Output directory")
    ] = "crds/generated",
    force: Annotated[bool, typer.Option("--force", help="Force regeneration")] = False,
    validate: Annotated[
        bool, typer.Option("--validate", help="Validate generated CRDs")
    ] = False,
):
    """Generate CRD YAML files from pydantic models."""
    import sys
    from pathlib import Path
    from cr8tor.crd.generator import KareCRDManager

    try:
        output_dir = Path(output)
        manager = KareCRDManager(output_dir=output_dir)

        success = manager.generate_all_crds(force=force)

        if success:
            typer.echo(f"CRDs generated successfully in {output_dir}")

            if validate:
                if manager.validate_generated_crds():
                    typer.echo("CRD validation passed")
                else:
                    typer.echo("CRD validation failed")
                    sys.exit(1)
        else:
            typer.echo("No CRDs generated (models unchanged)")

    except Exception as e:
        typer.echo(f"Failed to generate CRDs: {e}")
        sys.exit(1)


@app.command("validate-models")
def validate_models():
    """Validate CRD models without generating files."""
    from cr8tor.crd.generator import KareCRDManager

    try:
        manager = KareCRDManager()
        manager.registry.discover_models()
        models = manager.registry.get_all_models()
        crds = manager.get_crds_as_dict()

        typer.echo(f"Validated {len(models)} CRD models")
        for key in models.keys():
            typer.echo(f"  - {key}")
        typer.echo(f"Generated {len(crds)} CRDs in memory")

    except Exception as e:
        typer.echo(f"Model validation failed: {e}")
        raise typer.Exit(1)
