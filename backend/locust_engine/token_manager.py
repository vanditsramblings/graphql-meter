"""Token manager — OAuth2 client_credentials token cache for Azure AD / generic OAuth2."""

import threading
import time
import requests


class TokenManager:
    """Thread-safe OAuth2 token cache with auto-refresh."""

    def __init__(self, token_url: str, client_id: str, client_secret: str, scope: str = "", audience: str = ""):
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        self.audience = audience
        self._token = None
        self._expires_at = 0
        self._lock = threading.Lock()

    def get_token(self) -> str:
        """Get a valid access token, refreshing if needed."""
        if self._token and time.time() < self._expires_at - 60:
            return self._token

        with self._lock:
            # Double-check after acquiring lock
            if self._token and time.time() < self._expires_at - 60:
                return self._token
            return self._refresh()

    def _refresh(self) -> str:
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        if self.scope:
            data["scope"] = self.scope
        if self.audience:
            data["audience"] = self.audience

        resp = requests.post(self.token_url, data=data, timeout=30)
        resp.raise_for_status()
        body = resp.json()

        self._token = body["access_token"]
        self._expires_at = time.time() + body.get("expires_in", 3600)
        return self._token
