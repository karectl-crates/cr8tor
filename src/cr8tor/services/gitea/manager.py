""" Gitea organisation, team, and repo management.
"""

import logging
from typing import Any

from httpx import HTTPStatusError

from .client import get_gitea_client

logger = logging.getLogger(__name__)


async def ensure_organisation(
    org_name, description="", visibility="private"
    ):
    """ Create Gitea organisation if not exists.

    Args:
        org_name: Organisation name (will be used as username)
        description: Organisation description
        visibility: private, limited, or public
    """
    client = get_gitea_client()
    try:
        org = await client.get(f"/api/v1/orgs/{org_name}")
        logger.info(f"Gitea organisation '{org_name}' already exists")
        return {"created": False, "org": org}
    except HTTPStatusError as e:
        if e.response.status_code != 404:
            raise

    # Create organisation
    payload = {
        "username": org_name,
        "full_name": org_name.replace("-", " ").title(),
        "description": description,
        "visibility": visibility,
    }

    try:
        org = await client.post(f"/api/v1/admin/users/{org_name}/orgs", payload)
        logger.info(f"Created Gitea organisation: {org_name}")
        return {"created": True, "org": org}
    except HTTPStatusError as e:
        if e.response.status_code == 422:
            # Organisation might already exist
            logger.warning(f"Could not create Gitea org '{org_name}': {e}")
            return {"created": False, "org": None, "error": str(e)}
        raise


async def delete_organisation(org_name):
    """ Delete Gitea organisation.
    """
    client = get_gitea_client()

    try:
        await client.delete(f"/api/v1/orgs/{org_name}")
        logger.info(f"Deleted Gitea organisation: {org_name}")
        return True
    except HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.info(f"Gitea organisation '{org_name}' already deleted or not found")
            return True
        logger.error(f"Failed to delete Gitea org '{org_name}': {e}")
        raise


async def ensure_team(org_name, team_name, permission="write"):
    """ Create team in organisation if not exists.

    Args:
        org_name: Organisation name
        team_name: Team name
        permission: read, write, or admin
    """
    client = get_gitea_client()

    # Check for existence
    existing_team_id = await get_team_id(org_name, team_name)
    if existing_team_id:
        logger.info(f"Gitea team '{team_name}' already exists in org '{org_name}'")
        return {"team_id": existing_team_id, "created": False}

    # Create team
    payload = {
        "name": team_name,
        "permission": permission,
        "includes_all_repositories": True,
        "can_create_org_repo": permission in ("write", "admin"),
    }
    try:
        team = await client.post(f"/api/v1/orgs/{org_name}/teams", payload)
        logger.info(f"Created Gitea team '{team_name}' in org '{org_name}'")
        return {"team_id": team["id"], "created": True}
    except HTTPStatusError as e:
        if e.response.status_code == 422:
            # Team might already exist
            logger.warning(f"Could not create Gitea team '{team_name}': {e}")
            team_id = await get_team_id(org_name, team_name)
            return {"team_id": team_id, "created": False, "error": str(e)}
        raise


async def get_team_id(org_name, team_name):
    """ Get team ID by name.
    """
    client = get_gitea_client()

    try:
        teams = await client.get(f"/api/v1/orgs/{org_name}/teams")
        for team in teams:
            if team["name"] == team_name:
                return team["id"]
        return None
    except HTTPStatusError as e:
        if e.response.status_code == 404:
            return None
        raise


async def add_user_to_team(team_id, username):
    """ Add user to team.
    """
    client = get_gitea_client()

    try:
        await client.put(f"/api/v1/teams/{team_id}/members/{username}")
        logger.info(f"Added user '{username}' to Gitea team {team_id}")
        return True
    except HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning(
                f"User '{username}' not found in Gitea"
            )
            return False
        if e.response.status_code == 422:
            # User already in team or some validation error
            logger.info(f"User '{username}' may already be in team {team_id}")
            return False
        raise


async def remove_user_from_team(team_id, username):
    """ Remove user from team.
    """
    client = get_gitea_client()

    try:
        await client.delete(f"/api/v1/teams/{team_id}/members/{username}")
        logger.info(f"Removed user '{username}' from Gitea team {team_id}")
        return True
    except HTTPStatusError as e:
        if e.response.status_code == 404:
            # User not in team or doesn't exist
            return False
        raise


async def ensure_repository(
    org_name,
    repo_name,
    description = "",
    auto_init = True,
    private = True,
):
    """ Create repository in organisation if not exists.

    Args:
        org_name: Organisation name
        repo_name: Repository name
        description: Repository description
        auto_init: Initialise with README
        private: Make repository private
    """
    client = get_gitea_client()

    # Check for existence
    try:
        repo = await client.get(f"/api/v1/repos/{org_name}/{repo_name}")
        logger.info(f"Gitea repository '{org_name}/{repo_name}' already exists")
        return {"created": False, "repo": repo}
    except HTTPStatusError as e:
        if e.response.status_code != 404:
            raise

    # Create repository
    payload = {
        "name": repo_name,
        "description": description,
        "private": private,
        "auto_init": auto_init,
        "default_branch": "main",
    }

    try:
        repo = await client.post(f"/api/v1/org/{org_name}/repos", payload)
        logger.info(f"Created Gitea repository: {org_name}/{repo_name}")
        return {"created": True, "repo": repo}
    except HTTPStatusError as e:
        if e.response.status_code == 409:
            # Repository already exists
            logger.info(f"Gitea repository '{org_name}/{repo_name}' already exists")
            return {"created": False, "repo": None}
        raise
