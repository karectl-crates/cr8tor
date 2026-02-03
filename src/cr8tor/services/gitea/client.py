""" Gitea api client for cr8tor operator."""

import os
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def get_verify_tls():
    """ Get TLS verification from environment.
    """
    verify_tls = os.environ.get("GITEA_VERIFY_TLS", "true").lower()
    return verify_tls in ("true", "1", "yes")


def get_gitea_url():
    """ Get URL from environment.
    """
    return os.environ.get("GITEA_URL", "http://gitea-http.gitea.svc.cluster.local:3000")


def get_gitea_token():
    """ Get Gitea admin API token.
    """
    return os.environ.get("GITEA_ADMIN_TOKEN")


def is_gitea_enabled():
    """ Check if Gitea integration is enabled.
    """
    return bool(get_gitea_token())


class GiteaClient:
    """ Async HTTP client for Gitea API.
    """

    def __init__(self):
        self.base_url = get_gitea_url().rstrip("/")
        self.token = get_gitea_token()
        self.verify_tls = get_verify_tls()

        if not self.token:
            raise ValueError("GITEA_ADMIN_TOKEN environment variable is required")

    def _get_headers(self):
        """ Get headers for API requests.
        """
        return {
            "Authorization": f"token {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def get(self, path):
        """ Make GET requests. 
        """
        async with httpx.AsyncClient(verify=self.verify_tls, timeout=30.0) as client:
            url = f"{self.base_url}{path}"
            logger.debug(f"GET {url}")
            response = await client.get(url, headers=self._get_headers())
            response.raise_for_status()
            return response.json()

    async def post(self, path, data):
        """ Make POST request
        """
        async with httpx.AsyncClient(verify=self.verify_tls, timeout=30.0) as client:
            url = f"{self.base_url}{path}"
            logger.debug(f"POST {url}")
            response = await client.post(url, headers=self._get_headers(), json=data)
            response.raise_for_status()
            return response.json() if response.content else {}

    async def put(self, path, data=None):
        """ Make PUT request. 
        """
        async with httpx.AsyncClient(verify=self.verify_tls, timeout=30.0) as client:
            url = f"{self.base_url}{path}"
            logger.debug(f"PUT {url}")
            response = await client.put(
                url, headers=self._get_headers(), json=data or {}
            )
            response.raise_for_status()
            return response.json() if response.content else {}

    async def delete(self, path):
        """ Make DELETE request to API
        """
        async with httpx.AsyncClient(verify=self.verify_tls, timeout=30.0) as client:
            url = f"{self.base_url}{path}"
            logger.debug(f"DELETE {url}")
            response = await client.delete(url, headers=self._get_headers())
            response.raise_for_status()


def get_gitea_client():
    """ Get a new Gitea client instance. 
    """
    return GiteaClient()
