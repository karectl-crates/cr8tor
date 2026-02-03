""" Gitea integration services for cr8tor operator.
"""

from .client import get_gitea_client, get_verify_tls, is_gitea_enabled
from .manager import (
    ensure_organisation,
    delete_organisation,
    ensure_team,
    get_team_id,
    add_user_to_team,
    remove_user_from_team,
    ensure_repository,
)

__all__ = [
    "get_gitea_client",
    "get_verify_tls",
    "is_gitea_enabled",
    "ensure_organisation",
    "delete_organisation",
    "ensure_team",
    "get_team_id",
    "add_user_to_team",
    "remove_user_from_team",
    "ensure_repository",
]
