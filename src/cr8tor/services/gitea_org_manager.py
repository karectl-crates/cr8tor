""" Service for managing Gitea organisations, teams, and repos for Projects.
"""

import os
import requests
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

# Get gitea config from env
GITEA_URL = os.getenv("GITEA_URL")
GITEA_ADMIN_TOKEN = os.getenv("GITEA_ADMIN_TOKEN")


class GiteaOrgManager:
    """ Manage gitea organisations for projects.
    """

    def __init__(self, gitea_url = None, admin_token = None):
        self.base_url = gitea_url or GITEA_URL
        self.admin_token = admin_token or GITEA_ADMIN_TOKEN
        self.headers = {
            "Authorization": f"token {self.admin_token}",
            "Content-Type": "application/json",
        }

    def _request(self, method, endpoint, **kwargs):
        """ Create HTTP request to gitea API."""
        url = f"{self.base_url}/api/v1{endpoint}"

        try:
            response = requests.request(
                method, url, headers=self.headers, timeout=30, verify=False, **kwargs
            )
            response.raise_for_status()
            return response.json() if response.text else None
        except requests.exceptions.RequestException as e:
            logger.error(f"Gitea API error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise

    def create_organisation(self, org_name, description: str = "", visibility: str = "private"):
        """Create a gitea organisation."""
        payload = {
            "username": org_name,
            "description": description,
            "visibility": visibility,
            "repo_admin_change_team_access": False,
        }

        try:
            org = self._request("POST", "/orgs", json=payload)
            logger.info(f"Created organisation: {org_name}")
            return org
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 422:  # Already exists
                logger.info(f"Organisation {org_name} already exists")
                return self.get_organisation(org_name)
            raise

    def get_organisation(self, org_name):
        """ Get org details."""
        return self._request("GET", f"/orgs/{org_name}")

    def delete_organisation(self, org_name) -> None:
        """Delete an organisation."""
        self._request("DELETE", f"/orgs/{org_name}")
        logger.info(f"Deleted organisation: {org_name}")

    def create_team(
        self,
        org_name,
        team_name,
        permission: str = "read",
        description: str = "",
    ):
        """Create a team within an organisation."""
        payload = {
            "name": team_name,
            "description": description,
            "permission": permission,
            "can_create_org_repo": permission == "admin",
            "includes_all_repositories": True,
        }

        try:
            team = self._request("POST", f"/orgs/{org_name}/teams", json=payload)
            logger.info(f"Created team {team_name} in {org_name}")
            return team
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 422:  # Already exists
                logger.info(f"Team {team_name} already exists in {org_name}")
                teams = self.list_teams(org_name)
                return next((t for t in teams if t["name"] == team_name), None)
            raise

    def list_teams(self, org_name):
        """List all teams in an organisation."""
        return self._request("GET", f"/orgs/{org_name}/teams")

    def get_team_members(self, team_id) -> List[Dict]:
        """Get all members of a team."""
        return self._request("GET", f"/teams/{team_id}/members")

    def add_user_to_team(self, team_id, username):
        """Add a user to a team."""
        try:
            self._request("PUT", f"/teams/{team_id}/members/{username}")
            logger.info(f"Added {username} to team {team_id}")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"User {username} not found in Gitea, skipping")
            else:
                raise

    def remove_user_from_team(self, team_id, username):
        """Remove a user from a team."""
        try:
            self._request("DELETE", f"/teams/{team_id}/members/{username}")
            logger.info(f"Removed {username} from team {team_id}")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                pass
            else:
                raise

    def create_repository(
        self,
        org_name,
        repo_name,
        description: str = "",
        private: bool = True,
        auto_init: bool = True,
    ):
        """Create a repository in an organization."""
        payload = {
            "name": repo_name,
            "description": description,
            "private": private,
            "auto_init": auto_init,
            "default_branch": "main",
        }

        try:
            repo = self._request("POST", f"/orgs/{org_name}/repos", json=payload)
            logger.info(f"Created repository {org_name}/{repo_name}")
            return repo
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 409:  # Already exists
                logger.info(f"Repository {org_name}/{repo_name} already exists")
                return self.get_repository(org_name, repo_name)
            raise

    def get_repository(self, org_name, repo_name):
        """Get repository details."""
        return self._request("GET", f"/repos/{org_name}/{repo_name}")

    def list_repositories(self, org_name: str):
        """List all repositories in an organisation."""
        return self._request("GET", f"/orgs/{org_name}/repos")

    def delete_repository(self, org_name: str, repo_name: str):
        """Delete a repository."""
        self._request("DELETE", f"/repos/{org_name}/{repo_name}")
        logger.info(f"Deleted repository {org_name}/{repo_name}")

    def sync_project_organisation(
        self,
        project_name,
        description,
        gitea_config,
        all_users,
    ):
        """
        Sync a Project to Gitea organisation.

        Args:
            project_name: Name of the project
            description: Project description
            gitea_config: Gitea configuration from Project spec
            all_users: List of all User CRs with their groups
        """
        if not gitea_config.get("enabled", False):
            logger.info(f"Gitea not enabled for project {project_name}, skipping")
            return

        # Create/update org
        visibility = gitea_config.get("visibility", "private")
        self.create_organisation(project_name, description, visibility)

        # Create teams and sync users
        teams_config = gitea_config.get("teams", [])
        for team_config in teams_config:
            team_name = team_config["name"]
            permission = team_config.get("permission", "read")
            team_description = team_config.get("description", "")
            required_groups = team_config["groups"]

            # Create team
            team = self.create_team(
                org_name=project_name,
                team_name=team_name,
                permission=permission,
                description=team_description,
            )
            team_id = team["id"]

            # Get team members
            current_members = self.get_team_members(team_id)
            current_usernames = {m["username"] for m in current_members}

            # Set users
            should_be_members = set()
            for user in all_users:
                username = user.get("spec", {}).get("username")
                user_groups = user.get("spec", {}).get("groups", [])

                # Check if user has any of the required groups
                if username and any(group in user_groups for group in required_groups):
                    should_be_members.add(username)

            # Add missing users
            for username in should_be_members - current_usernames:
                self.add_user_to_team(team_id, username)

            # Remove users without required groups
            for username in current_usernames - should_be_members:
                self.remove_user_from_team(team_id, username)

        # Create initial repos
        repos_config = gitea_config.get("repositories", [])
        for repo_config in repos_config:
            repo_name = repo_config["name"]
            repo_description = repo_config.get("description", "")
            private = repo_config.get("private", True)
            auto_init = repo_config.get("auto_init", True)

            self.create_repository(
                org_name=project_name,
                repo_name=repo_name,
                description=repo_description,
                private=private,
                auto_init=auto_init,
            )

        logger.info(f"Synced project {project_name} successfully")

    def delete_project_organisation(self, project_name):
        """Delete Gitea organisation for a project."""
        try:
            self.delete_organisation(project_name)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.info(f"Organisation {project_name} doesn't exist, nothing to delete")
            else:
                raise


# Singleton instance
_gitea_org_manager = None


def get_gitea_org_manager():
    """Get singleton instance."""
    global _gitea_org_manager
    if _gitea_org_manager is None:
        _gitea_org_manager = GiteaOrgManager()
    return _gitea_org_manager


def sync_project_to_gitea(project_name, project_spec, all_users):
    """
    Sync a Project CR to Gitea.

    Args:
        project_name: Project name
        project_spec: Project spec dictionary
        all_users: List of all User CRs
    """
    apps = project_spec.get("apps", [])
    gitea_app = next((app for app in apps if app.get("type") == "gitea"), None)
    gitea_config = gitea_app.get("config") if gitea_app else None

    if not gitea_config:
        logger.info(f"No Gitea configuration for project {project_name}")
        return

    description = project_spec.get("description", "")
    manager = get_gitea_org_manager()
    manager.sync_project_organisation(project_name, description, gitea_config, all_users)


def delete_project_from_gitea(project_name):
    """Delete Gitea organisation for a project."""
    manager = get_gitea_org_manager()
    manager.delete_project_organisation(project_name)
