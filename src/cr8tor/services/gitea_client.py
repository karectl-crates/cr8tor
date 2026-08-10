""" Gitea API client for cr8tor operator."""

import os
import logging
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


def get_gitea_verify_tls():
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


def get_gitea_oidc_source_id():
    """ Get the id of the Gitea auth source backing Keycloak OIDC logins.

    Accounts are pre-provisioned against this auth source so that login still goes through
    SSO. Returns None when unset or not an integer, in which case pre-provisioning is
    skipped rather than falling back to a local-password account.
    """
    raw = (os.environ.get("GITEA_OIDC_SOURCE_ID") or "").strip()
    if not raw:
        return None

    try:
        return int(raw)
    except ValueError:
        logger.warning(
            f"GITEA_OIDC_SOURCE_ID is not an integer ({raw!r}); skipping Gitea pre-provisioning"
        )
        return None


def get_gitea_network_target():
    """ Resolve how project namespaces reach Gitea, for network policy generation.

    An in-cluster Gitea is reached through a namespace selector; an external or
    ingress-fronted Gitea has to be reached by FQDN. Both the location and the ports are
    derived from GITEA_URL so that a Gitea behind ingress on 443 is not blocked, and both
    can be overridden with GITEA_NAMESPACE and GITEA_PORTS.

    Returns:
        dict with `mode` ("cluster" or "fqdn"), `namespace`, `fqdn` and `ports`.
    """
    parsed = urlparse(get_gitea_url())
    hostname = parsed.hostname or ""
    default_port = parsed.port or (443 if parsed.scheme == "https" else 80)

    raw_ports = (os.environ.get("GITEA_PORTS") or "").strip()
    ports = []
    for chunk in raw_ports.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            ports.append(int(chunk))
        except ValueError:
            logger.warning(f"Ignoring non-integer port in GITEA_PORTS: {chunk!r}")
    if not ports:
        ports = [default_port]

    namespace = (os.environ.get("GITEA_NAMESPACE") or "").strip()
    if not namespace and hostname.endswith((".svc", ".svc.cluster.local")):
        # e.g. gitea-http.gitea.svc.cluster.local -> gitea
        parts = hostname.split(".")
        if len(parts) >= 2:
            namespace = parts[1]

    if namespace:
        return {"mode": "cluster", "namespace": namespace, "fqdn": None, "ports": ports}

    return {"mode": "fqdn", "namespace": None, "fqdn": hostname, "ports": ports}


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
        self.verify_tls = get_gitea_verify_tls()

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
