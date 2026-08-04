""" Gitea organisation, team, and repo management.
"""

import logging

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
        org = await client.post(f"/api/v1/orgs", payload)
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

    # Default repository units that the team can access
    default_units = [
        "repo.code",
        "repo.issues",
        "repo.pulls",
        "repo.releases",
        "repo.wiki",
        "repo.projects",
        "repo.packages",
        "repo.actions",
    ]

    # Create team
    payload = {
        "name": team_name,
        "permission": permission,
        "includes_all_repositories": True,
        "can_create_org_repo": permission in ("write", "admin"),
        "units": default_units,
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


async def ensure_user(username, email, full_name="", source_id=None):
    """ Create a Gitea user backed by an external auth source if not exists.

    Pre-provisioning the account means team assignment no longer has to wait for the user's
    first OIDC login. The account is bound to `source_id` (the Keycloak auth source) so
    authentication still goes through SSO and no local password is set.

    Args:
        username: Gitea username, matching the Keycloak username
        email: User email address
        full_name: Display name
        source_id: Gitea auth source id. When None the user is not created.

    Returns:
        dict with `created`, `user` and, when nothing was done, `skipped`/`reason`.
    """
    client = get_gitea_client()

    # Check for existence first: an account that already exists needs no auth source
    try:
        user = await client.get(f"/api/v1/users/{username}")
        logger.info(f"Gitea user '{username}' already exists")
        return {"created": False, "user": user}
    except HTTPStatusError as e:
        if e.response.status_code != 404:
            raise

    if source_id is None:
        logger.warning(
            f"No Gitea OIDC auth source configured; not pre-provisioning user '{username}'. "
            "The account will be created by Gitea on first SSO login instead."
        )
        return {"created": False, "user": None, "skipped": True, "reason": "no-oidc-source-id"}

    payload = {
        "username": username,
        "email": email,
        "login_name": username,
        "source_id": source_id,
        "must_change_password": False,
    }
    if full_name:
        payload["full_name"] = full_name

    try:
        user = await client.post("/api/v1/admin/users", payload)
        logger.info(f"Pre-provisioned Gitea user '{username}' against auth source {source_id}")
        return {"created": True, "user": user}
    except HTTPStatusError as e:
        if e.response.status_code == 422:
            # Raced with another writer, or the username/email is already taken
            logger.info(f"Gitea user '{username}' already exists")
            return {"created": False, "user": None}
        raise


async def get_team_members(team_id, page_size=50):
    """ List the usernames of a team's members.

    Args:
        team_id: Gitea team id
        page_size: Results per API page

    Returns:
        List of usernames.
    """
    client = get_gitea_client()
    logins = []
    page = 1

    while True:
        try:
            batch = await client.get(
                f"/api/v1/teams/{team_id}/members?page={page}&limit={page_size}"
            )
        except HTTPStatusError as e:
            if e.response.status_code == 404:
                return logins
            raise

        if not batch:
            break

        logins.extend(
            login for login in
            (member.get("login") or member.get("username") for member in batch)
            if login
        )

        if len(batch) < page_size:
            break
        page += 1

    return logins


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
        repo = await client.post(f"/api/v1/orgs/{org_name}/repos", payload)
        logger.info(f"Created Gitea repository: {org_name}/{repo_name}")
        return {"created": True, "repo": repo}
    except HTTPStatusError as e:
        if e.response.status_code == 409:
            # Repository already exists
            logger.info(f"Gitea repository '{org_name}/{repo_name}' already exists")
            return {"created": False, "repo": None}
        raise
