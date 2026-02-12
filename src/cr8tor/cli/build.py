import bagit
import sys
import typer
import rocrate.model as m
import cr8tor.airlock.schema as s
import cr8tor.airlock.resourceops as project_resources
import cr8tor.airlock.linkml_ops as linkml_ops
from pathlib import Path
from typing import Annotated
from rocrate.rocrate import ROCrate

from cr8tor.exception import DirectoryNotFoundError
from cr8tor.utils import log, make_uuid
from cr8tor.cli.display import print_crate

from cr8tor_metamodel.datamodel.cr8tor_metamodel_pydantic import (
    Governance,
    Project,
    Ingress,
    CreateAction,
    AssessAction,
)

app = typer.Typer()


def init_bag(project_id: str, bagit_dir: Path, config: dict) -> bagit.Bag:
    """
    Initializes a BagIt bag for a given project.
    Args:
        project_id (str): The unique identifier for the project.
        bagit_dir (Path): The directory where the bag will be created.
        config (dict): Configuration dictionary containing BagIt metadata.
    Returns:
        bagit.Bag: The created BagIt bag object.
    Raises:
        OSError: If the directory cannot be created.
        bagit.BagError: If there is an error creating the bag.
    """

    bagit_dir.mkdir(parents=True, exist_ok=True)

    bag: bagit.Bag = bagit.make_bag(bag_dir=bagit_dir, checksums=["sha512"])

    # bag.info.update(s.BagitInfo(**config["bagit-info"])) # ToDo: Fix serialisation alias issue
    bag.info.update(**config["bagit-info"])
    bag.info["External-Identifier"] = make_uuid(project_id)

    return bag


def check_required_keys(data: dict, required_keys: dict):
    for key, error_message in required_keys.items():
        if key not in data:
            raise KeyError(error_message)


@app.command(name="build")
def build(
    resources_dir: Annotated[
        Path,
        typer.Option(
            default="-i", help="Directory containing resources to include in RO-Crate."
        ),
    ] = "./resources",
    config_file: Annotated[
        Path, typer.Option(default="-c", help="Location of configuration TOML file.")
    ] = "./config.toml",
    dryrun: Annotated[bool, typer.Option(default="--dryrun")] = False,
):
    """
    Builds the RO-Crate data crate for the target Cr8tor project using the specified metadata resources and configuration.

    This command performs the following actions:
    - Reads the configuration from the specified TOML file.
    - Includes resources from the specified directory into the RO-Crate.
    - If the `dryrun` option is provided, prints the crate details without writing to the "crate/" directory.

    Args:
        resources_dir (Path): Directory containing resources to include in the RO-Crate. Defaults to "./resources".
        config_file (Path): Location of the configuration TOML file. Defaults to "./config.toml".
        dryrun (bool): If True, prints the crate details without writing to the "crate/" directory. Defaults to False.

    Example usage:
        cr8tor build -i path-to-resources-dir -c path-to-config-file --dryrun
    """
    ###############################################################################
    # 1 Validate project build materials (i.e. resources/ & config.toml)
    ###############################################################################

    config = project_resources.read_resource(config_file)

    if not resources_dir.exists():
        raise DirectoryNotFoundError(resources_dir)

    # Load LinkML-based governance YAML as Pydantic model
    log.info("HERE")

    governance_path = resources_dir.joinpath("governance", "cr8-governance.yaml")
    try:
        governance = linkml_ops.load_yaml_as_pydantic(governance_path, Governance)
    except Exception as e:
        raise ValueError(f"Error loading governance file: {str(e)}")

    # Load LinkML-based ingress YAML as Pydantic model
    ingress_path = resources_dir.joinpath("data", "cr8-ingress.yaml")
    try:
        ingress = linkml_ops.load_yaml_as_pydantic(ingress_path, Ingress)
    except Exception as e:
        raise ValueError(f"Error loading ingress file: {str(e)}")

    ###############################################################################
    # 2 Check mandatory user-defined elements (i.e. gov, access) exists
    ###############################################################################

    # Validate governance model has required attributes
    if not governance.project:
        raise ValueError(f"To build ro-crate 'project' properties must be defined in resource: {governance_path}")
    
    # Check for actions (assuming it's a field in Project model)
    if hasattr(governance.project, 'actions') and not governance.project.actions:
        log.warning(f"No actions found in project. This may be expected for newly created projects.")

    # Validate ingress model has required attributes
    if not ingress.destination:
        raise ValueError(f"To build ro-crate 'destination' must be defined in resource: {ingress_path}")

    ###############################################################################
    # 3 Create initial Ro-Crate & build contextual entities
    ###############################################################################

    crate = ROCrate(gen_preview=True)

    #
    # Load project info and init RC 'Project' entity
    #

    project = governance.project
    log.info(
        f"[cyan]Creating RO-Crate for[/cyan] - [bold magenta]{project.name}[/bold magenta]",
    )

    # Get project ID (assuming it exists in the model)
    project_id = project.id if hasattr(project, 'id') else project.reference

    project_entity = m.ContextEntity(
        crate=crate,
        identifier=project_id,
        properties={
            "@type": "Project",
            "name": project.name,
            "identifier": project.reference,
        },
    )
    crate.add(project_entity)

    #
    # Load requesting agent info and init RC 'Person' entity
    # TODO: Requesting agent not yet in LinkML model - add when available
    #
    # For now, skip requesting agent if not available in the governance model
    if hasattr(governance, 'requesting_agent') and governance.requesting_agent:
        requesting_agent = governance.requesting_agent
        person_entity = m.Person(
            crate,
            identifier=f"requesting-agent-{project_id}",
            properties={
                "name": requesting_agent.name,
                "affiliation": {"@id": f"requesting-agent-org-{project_id}"},
            },
        )

        aff_entity = m.ContextEntity(
            crate,
            identifier=f"requesting-agent-org-{project_id}",
            properties={
                "@type": "Organisation",
                "name": requesting_agent.affiliation.name,
                "url": str(requesting_agent.affiliation.url),
            },
        )

        crate.add(aff_entity)
        crate.add(person_entity)

        # Relation definition for ro-crate metadata file only (i.e. not stored are managed in the resources)
        project_entity["memberOf"] = [{"@id": person_entity.id}]

    #
    # Load project repository info and init RC 'SoftwareSourceCode' entity
    # TODO: Repository not yet in LinkML model - add when available
    #
    # For now, skip repository if not available in the governance model
    if hasattr(governance, 'repository') and governance.repository:
        repo = governance.repository
        repo_entity = m.ContextEntity(
            crate=crate,
            identifier=f"repo-{project_id}",
            properties={
                "@type": "SoftwareSourceCode",
                "name": repo.name,
                "description": repo.description,
                "codeRepository": f"{repo.codeRepository}cr8-{project_id}",
            },
        )

        crate.add(repo_entity)
        crate.metadata["isBasedOn"] = {"@id": f"repo-{project_id}"}

    #
    # Load access info and init RC entities
    #

    # contract_props = s.DataAccessContract(
    #     source=s.DatabricksSourceConnection(**access["source"]),
    #     credentials=s.SourceAccessCredential(**access["credentials"]),
    #     project_name=governance["project"]["project_name"],
    #     project_start_time=governance["project"]["project_start_time"],
    #     destination_type=governance["project"]["destination"]["type"],
    #     destination_name=governance["project"]["destination"]["name"],
    #     destination_format=governance["project"]["destination"]["format"],
    #     metadata=None
    # )
    # TODO: Identify and init any RC contextual entities for describing data access

    ###############################################################################
    # 4 Build data entities
    ###############################################################################

    #
    # Governance resources
    #

    crate.add_file(
        source=governance_path,
        dest_path="governance/cr8-governance.yaml",
        properties={
            "name": project.name,
            "description": project.description,
        },
    )

    log.info(
        msg="[cyan]Validated and added file[/cyan] - [bold magenta]governance/cr8-governance.yaml[/bold magenta]",
    )

    #
    # Metadata resources
    #

    for f in resources_dir.joinpath("metadata").glob("dataset*.toml"):
        dataset_dict = project_resources.read_resource(f)
        dataset_props = s.DatasetMetadata(**dataset_dict)

        crate.add_file(
            source=f,
            dest_path=f"metadata/{f.name}",
            properties={
                "name": dataset_props.name,
                "description": dataset_props.description,
            },
        )

        hasparts = []

        if dataset_props.staging_path is not None:
            staging_entity = m.ContextEntity(
                crate=crate,
                identifier=f"{dataset_props.name}-staging",
                properties={
                    "@type": "Dataset",
                    "name": f"{dataset_props.name} (Staging)",
                    "url": f"{dataset_props.staging_path}",
                    "encodingFormat": "application/x-duckdb",  # TODO: add format from project metadata
                },
            )
            crate.add(staging_entity)
            hasparts.append({"@id": staging_entity.id})

        if dataset_props.publish_path is not None:
            publish_entity = m.ContextEntity(
                crate=crate,
                identifier=f"{dataset_props.name}-publish",
                properties={
                    "@type": "Dataset",
                    "name": f"{dataset_props.name} (Publish)",
                    "url": f"{dataset_props.publish_path}",
                    "encodingFormat": "application/x-duckdb",  # TODO: add format from project metadata
                },
            )
            crate.add(publish_entity)
            hasparts.append({"@id": publish_entity.id})

        data_ctx_entity = m.ContextEntity(
            crate=crate,
            identifier=f"{dataset_props.name}",
            properties={
                "@type": "Dataset",
                "name": f"{dataset_props.name}",
                "description": dataset_props.description,
                "hasPart": hasparts,
            },
        )

        crate.add(data_ctx_entity)

    #
    # Ingress/Data resources
    # TODO: Process ingress model data and add to RO-Crate
    #

    crate.add_file(
        source=ingress_path,
        dest_path="data/cr8-ingress.yaml",
        properties={
            "name": "Data Ingress Configuration",
            "description": "Data ingress configuration for the project",
        },
    )

    log.info(
        msg="[cyan]Validated and added file[/cyan] - [bold magenta]data/cr8-ingress.yaml[/bold magenta]",
    )

    # Legacy access resources - commented out as using new LinkML ingress model
    # source_data = {}
    # source_data["source"] = access["source"].copy()
    # source_data["source"]["type"] = source_data["source"]["type"].lower()
    # source_data["source"]["credentials"] = access["credentials"]
    # source_data["extract_config"] = (
    #     access["extract_config"] if "extract_config" in access else None
    # )
    # access_source = s.SourceConnectionModel(**source_data)
    # crate.add_file(
    #     source=access_resource_path,
    #     dest_path="access/access.toml",
    #     properties={"name": access_source.source.type},
    # )
    # log.info(
    #     msg="[cyan]Validated and added access descriptor file[/cyan] - [bold magenta]access/access.toml[/bold magenta]",
    # )

    ###############################################################################
    # 5 Finalise Crate
    ###############################################################################
    crate.name = project.name
    crate.description = project.description
    crate.license = s.CrateMeta.License
    
    # Get code repository URL from governance if available
    repo_url = governance.repository.codeRepository if hasattr(governance, 'repository') and governance.repository else "https://github.com/lsc-sde-crates"
    
    crate.publisher = m.ContextEntity(
        crate,
        identifier=s.CrateMeta.Publisher,
        properties={
            "@type": "Organisation",
            "name": "LSC SDE",
            "url": repo_url,
        },
    )
    crate.mainEntity = project_entity

    ###############################################################################
    # 6 Process and render all action entities
    ###############################################################################

    #
    # Check for actions (assuming actions is a field in Project model)
    #

    if hasattr(governance.project, 'actions') and governance.project.actions:
        for action in governance.project.actions:
            # Actions are already validated Pydantic models from LinkML
            # Check if it's a CreateAction or AssessAction instance
            if isinstance(action, CreateAction):
                action_type = "CreateAction"
            elif isinstance(action, AssessAction):
                action_type = "AssessAction"
            else:
                action_type = "Action"

            crate.add_action(
                instrument=action.instrument,
                identifier=action.id,
                result=action.result if action.result else [],
                properties={
                    "@type": action_type,
                    "name": action.name,
                    "startTime": action.start_time.isoformat(),
                    "endTime": action.end_time.isoformat(),
                    "actionStatus": action.action_status,
                    "agent": action.agent,
                },
            )

    ###############################################################################
    # 7 Add Ro-crate meta to bagit directory structure
    ###############################################################################
    if not dryrun:
        bagit_dir = Path("./bagit")

        if bagit_dir.exists() and bagit_dir.is_dir():
            bag = bagit.Bag(str(bagit_dir))

            # Update bag info from config.toml; This does not modify the External-Identifier.
            # Delete and recreate the bag if the External-Identifier needs to be changed.
            bag.info.update(**config["bagit-info"])
            log.info("Loaded existing bag")
        else:
            bag = init_bag(
                project_id=project_id, bagit_dir=bagit_dir, config=config
            )

        crate.write(bagit_dir / "data")
        bag.save(manifests=True)

        n_payload_files = len(list(bag.payload_files()))
        log.info(
            f"[cyan]RO-Crate BagIt created at[/cyan] - [bold magenta]{bagit_dir} with {n_payload_files} files.[/bold magenta]",
        )
    else:
        log.warning(
            "[bold red]Dry run option set. Crate will not be written to disk.[/bold red]\n"
        )

    print_crate(crate=crate)
