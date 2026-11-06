"""
Standalone OAuth2 client_credentials token fetcher for the u-OS Administration API.

Creds are hardcoded for now (hackathon speed). TODO: replace _get_device_credentials()
below with a REST call to the vault server once that's built - something like:

    def _get_device_credentials():
        resp = requests.post(
            f"{VAULT_URL}/v1/credentials/lookup",
            json={"device_serial": "BA8K14PC7500013"},
            cert=(IRF_CLIENT_CERT, IRF_CLIENT_KEY),   # mTLS, see architecture discussion
            verify=VAULT_CA_BUNDLE,
            timeout=10,
        )
        resp.raise_for_status()
        creds = resp.json()
        return creds["client_id"], creds["client_secret"]

Everything else in this module (get_token) stays the same either way - only
_get_device_credentials() changes when the vault integration lands.

Usage:
    from oauth_token import get_token
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
"""
import requests

HOST = "192.168.0.101"
TOKEN_URL = f"https://{HOST}/oauth2/token"

DEFAULT_SCOPES = [
    "u-os-adm.system.readonly",
    "u-os-adm.update.readonly",
    "u-os-adm.network.readonly",
    "u-os-adm.logging.readonly",
]

requests.packages.urllib3.disable_warnings()


def _get_device_credentials():
    """PLACEHOLDER - hardcoded for now. Replace with a vault server REST call
    (see module docstring) once that service exists."""
    client_id = "dda068a4-1521-4f5b-aff7-375c5f1a3c1f"
    client_secret = "gRAJgn7AScranpAZ0n56kicmHH"
    return client_id, client_secret


def get_token(scopes=None, verify=False, timeout=10):
    """Fetch a bearer access token via OAuth2 client_credentials."""
    client_id, client_secret = _get_device_credentials()
    scopes = scopes or DEFAULT_SCOPES
    resp = requests.post(
        TOKEN_URL,
        data={"grant_type": "client_credentials", "scope": " ".join(scopes)},
        auth=(client_id, client_secret),
        verify=verify,
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


if __name__ == "__main__":
    print(get_token())
