"""Command to initialize a new CR8 project using a specified cookiecutter template."""

from datetime import datetime
from typing import Annotated
from pathlib import Path

import typer
import sys
import re

from cookiecutter.main import cookiecutter
from cookiecutter.exceptions import OutputDirExistsException, FailedHookException
from cr8tor.utils import log
import cr8tor.airlock.resourceops as project_resources
import cr8tor.airlock.schema as schemas
import cr8tor.airlock.gh_rest_api_client as gh_rest_api_client

app = typer.Typer()


@app.command(name="initiate")
def initiate(
    template_path: Annotated[
        str,
        typer.Option(
            default="-t",
            help="GitHub URL or relative path to cr8-cookiecutter template (not needed with --skip-template)",
        ),
    ] = None,
    push_to_github: Annotated[
        bool,
        typer.Option(
            "--push/--no-push",
            help="Flag to indicate if the project should be pushed to GitHub",
        ),
    ] = False,
    git_org: Annotated[
        str,
        typer.Option(
            "-org",
            help="Target github organisation name", 
            hide_input=True,
        ),
    ] = None,
    git_projects_repo: Annotated[
        str,
        typer.Option(
            "-repo",
            help="Target github projects repository name", 
            hide_input=True,
        ),
    ] = None,
    checkout: Annotated[
        str,
        typer.Option(
            "-chk",
            help="Branch, tag or commit to checkout from cookiecutter template",
        ),
    ] = None,
    project_name: Annotated[
        str,
        typer.Option(
            "-n",
            help="Name of the project to be created. This is optional and can be provided as an argument.",
        ),
    ] = None,
    environment: Annotated[
        str,
        typer.Option(
            "-e",
            help="Target environment. Default PROD. Must be one of the three options: DEV, TEST, PROD.",
            case_sensitive=False,
            show_choices=True,
        ),
    ] = "PROD",
    cr8tor_branch: Annotated[
        str,
        typer.Option(
            "-cb",
            help="For developing and debugging. Provide the github cr8tor branch that should be used in orchestration layer.",
        ),
    ] = None,
    runner_os: Annotated[
        str,
        typer.Option(
            "-ros",
            help="Target runner OS for GitHub Actions workflows. Must be one of: Windows, Linux.",
            case_sensitive=False,
            show_choices=True,
        ),
    ] = "Windows",
    skip_template: Annotated[
        bool,
        typer.Option(
            "--skip-template",
            help="Skip cookiecutter template generation and use existing project directory",
        ),
    ] = False,
    project_dir: Annotated[
        str,
        typer.Option(
            "--project-dir",
            help="Path to existing project directory (used with --skip-template). Defaults to ./{project_name}",
        ),
    ] = None,
):
    """
    Initializes a new CR8 project using a specified cookiecutter template.

    Args:
        template_path (str): The GitHub URL or relative path to the cr8-cookiecutter template.
                             This is prompted from the user if not provided.
        push_to_github (bool): Flag to indicate if the project should be pushed to GitHub. Defaults to False.
        git_org (str, optional): The target GitHub organization name. Required if `push_to_github` is True.
        git_projects_repo (str, optional): The target projects GitHub repo name. Required if `push_to_github` is True.
        checkout (str, optional): The branch, tag, or commit to checkout from the cookiecutter template.
        project_name (str, optional): The name of the project to be created. If provided, cookiecutter will skip the prompt for other values.
        environment (str): The target environment (DEV, TEST, PROD). Defaults to "PROD".
        cr8tor_branch (str, optional): For development and debugging. Specifies the GitHub cr8tor branch to be used in the orchestration layer.
        runner_os (str): The target runner OS for GitHub Actions workflows (Windows, Linux). Defaults to "Windows".
        skip_template (bool): Skip cookiecutter template generation and use existing project directory. Defaults to False.
        project_dir (str): Path to existing project directory (used with --skip-template). Defaults to None.

    This command performs the following actions:
    - Generates a new project by applying the specified cookiecutter template (unless --skip-template is set).
    - Adds a timestamp to the context used by the template.
    - If `push_to_github` is True, creates a GitHub repository under the specified organization and pushes the generated project to GitHub using the personal access token (retrieved from `os.getenv("GH_TOKEN")`).

    Example usage:
        cr8tor initiate -t https://github.com/lsc-sde-crates/cr8-cookiecutter

        cr8tor initiate -t path-to-local-cr8-cookiecutter-dir

        cr8tor initiate -t path-to-local-cr8-cookiecutter-dir -n "my-project" -org "lsc-sde-crates" --push

        cr8tor initiate -t path-to-local-cr8-cookiecutter-dir -n "my-project" -org "lsc-sde-crates" -ros "Linux" --push
        
        # Push existing project to GitHub (from parent directory)
        cr8tor initiate -n "my-project" -org "lsc-sde-crates" -repo "cr8tor-projects" --push --skip-template
        
        # Push existing project to GitHub (from inside project directory)
        cd my-project
        cr8tor initiate -org "lsc-sde-crates" -repo "cr8tor-projects" --push --skip-template
        
        # Push existing project with explicit path
        cr8tor initiate --project-dir ./path/to/project -org "lsc-sde-crates" -repo "cr8tor-projects" --push --skip-template
    """
    valid_environments = ["DEV", "TEST", "PROD"]
    if environment.upper() not in valid_environments:
        raise typer.BadParameter(
            f"Invalid environment. Choose from {valid_environments}."
        )

    valid_runner_os = ["Windows", "Linux"]
    if runner_os not in valid_runner_os:
        raise typer.BadParameter(f"Invalid runner OS. Choose from {valid_runner_os}.")

    # Check if we should skip template generation and use existing project
    if skip_template:
        if not project_name and not project_dir:
            raise typer.BadParameter(
                "Either project name (-n) or project directory (--project-dir) is required when using --skip-template"
            )
        
        # Determine project directory
        if project_dir:
            # Use explicitly provided project directory
            project_dir_path = Path(project_dir).resolve()
        elif project_name:
            # Check if current directory is the project (has resources/governance/project.toml)
            current_dir = Path.cwd()
            if (current_dir / "resources" / "governance" / "project.toml").exists():
                project_dir_path = current_dir
                log.info(f"Detected project in current directory: {project_dir_path}")
            else:
                # Look for project as subdirectory
                project_dir_path = current_dir / project_name
        
        if not project_dir_path.exists():
            raise typer.BadParameter(
                f"Project directory '{project_dir_path}' does not exist. "
                f"Cannot use --skip-template without an existing project."
            )
        
        # Verify it's a valid project directory
        project_resources_path = project_dir_path / "resources" / "governance" / "project.toml"
        if not project_resources_path.exists():
            raise typer.BadParameter(
                f"Invalid project directory. Missing: {project_resources_path}"
            )
        
        log.info(f"Using existing project directory: {project_dir_path}")
        project_dir = str(project_dir_path)
    
    else:
        # Template path is required when not skipping template
        if not template_path:
            raise typer.BadParameter(
                "Template path (-t) is required when not using --skip-template"
            )
        
        # Generate project with cookiecutter
        extra_context = {
            "__timestamp": datetime.now().isoformat(timespec="seconds"),
            "__cr8_cc_template": template_path,
            "environment": environment.upper(),
            "__github_cr8tor_branch": cr8tor_branch,
            "runner_os": runner_os,
        }

        # Generate the project with cookiecutter
        if project_name is not None:
            extra_context.update({"project_name": project_name})
            extra_context.update({"github_organization": git_org})
            # extra_context.update({"github_projects_repo": git_projects_repo})
            try:
                project_dir = cookiecutter(
                    template_path,
                    checkout=checkout,
                    extra_context=extra_context,
                    no_input=True,
                )

            except OutputDirExistsException as e:
                log.info("Project directory already exists. Skipping creation...")
                # Extract folder name from exception message
                folder_name = re.search(r'"(.*?)"', str(e)).group(1)
                project_dir = Path.cwd() / folder_name
        else:
            try:
                project_dir = cookiecutter(
                    template_path, checkout=checkout, extra_context=extra_context
                )
            except FailedHookException as e:
                # Extract error message from the exception
                error_msg = str(e)
                if "VALIDATION_ERROR:" in error_msg:
                    validation_error = error_msg.split("VALIDATION_ERROR:")[1].strip()
                    print(f"Validation failed: {validation_error}")
                else:
                    print(f"Hook failed: {error_msg}")
                sys.exit(1)
            except OutputDirExistsException as e:
                log.info("Project directory already exists. Skipping creation...")
                # Extract folder name from exception message
                folder_name = re.search(r'"(.*?)"', str(e)).group(1)
                project_dir = Path.cwd() / folder_name

    resources_dir = Path(project_dir).joinpath("resources")
    project_resource_path = resources_dir.joinpath("governance", "project.toml")
    project_dict = project_resources.read_resource_entity(
        project_resource_path, "project"
    )
    project_info = schemas.ProjectProps(**project_dict)

    if push_to_github and git_org and git_projects_repo:
        
        log.info(f"Creating project directory {git_projects_repo} under organization {git_org} on GitHub...")
        # project_info.reference

        gh_client = gh_rest_api_client.GHApiClient(git_org)

        # Create the repository and push the project to GitHub
        gh_rest_api_client.create_and_push_project(gh_client, project_dir, git_projects_repo)

        # Check and create contributor teams on projects repo
        gh_rest_api_client.check_and_create_teams(gh_client, project_name, git_projects_repo)

        # Create repository environments for Signing Off experience
        gh_rest_api_client.create_github_environments(gh_client, git_projects_repo)