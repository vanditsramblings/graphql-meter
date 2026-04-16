"""Auth Providers plugin — manage authentication providers for test runs.

Supports: bearer_token, basic, api_key, oauth2_client_credentials, oauth2_password, jwt_custom.
All sensitive fields are encrypted at rest using Fernet (AES-128-CBC + HMAC-SHA256).
Secrets are NEVER returned via API — only masked versions.
"""

import base64
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from cryptography.fernet import Fernet
from fastapi import HTTPException, Request
from pydantic import BaseModel

from backend.config import get_settings
from backend.core.plugin_base import PluginBase
from backend.plugins.auth_plugin import require_auth, require_role
from backend.plugins.storage_plugin import get_db

# ---------- Encryption helpers ----------

_fernet_instance = None


def _get_fernet() -> Fernet:
    global _fernet_instance
    if _fernet_instance is None:
        settings = get_settings()
        seed = settings.ENCRYPTION_KEY or settings.JWT_SECRET
        # Derive a 32-byte key via PBKDF2 (100k iterations)
        key_bytes = hashlib.pbkdf2_hmac("sha256", seed.encode(), b"graphql-meter-salt", 100_000)
        fernet_key = base64.urlsafe_b64encode(key_bytes[:32])
        _fernet_instance = Fernet(fernet_key)
    return _fernet_instance


def _encrypt(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()


def _mask(value: str, visible: int = 4) -> str:
    if not value or len(value) <= visible:
        return "****"
    return value[:visible] + "****" + value[-2:]


# ---------- Auth type schemas ----------

AUTH_TYPE_FIELDS = {
    "bearer_token": {
        "label": "Bearer Token",
        "fields": [
            {"name": "token", "label": "Token", "type": "password", "required": True,
             "help": "Static bearer token value"},
        ],
    },
    "basic": {
        "label": "Basic Auth",
        "fields": [
            {"name": "username", "label": "Username", "type": "text", "required": True},
            {"name": "password", "label": "Password", "type": "password", "required": True},
        ],
    },
    "api_key": {
        "label": "API Key",
        "fields": [
            {"name": "header_name", "label": "Header Name", "type": "text", "required": True,
             "default": "X-API-Key", "help": "HTTP header name for the API key"},
            {"name": "api_key", "label": "API Key", "type": "password", "required": True},
        ],
    },
    "oauth2_client_credentials": {
        "label": "OAuth2 Client Credentials",
        "fields": [
            {"name": "token_url", "label": "Token URL", "type": "url", "required": True,
             "help": "OAuth2 token endpoint"},
            {"name": "client_id", "label": "Client ID", "type": "text", "required": True},
            {"name": "client_secret", "label": "Client Secret", "type": "password", "required": True},
            {"name": "scope", "label": "Scope", "type": "text", "required": False,
             "help": "Space-separated scopes"},
            {"name": "audience", "label": "Audience", "type": "text", "required": False},
            {"name": "extra_params", "label": "Extra Parameters (JSON)", "type": "textarea", "required": False,
             "help": "Additional key-value pairs sent with the token request"},
            {"name": "token_refresh_buffer_sec", "label": "Refresh Buffer (sec)", "type": "number",
             "required": False, "default": 60, "help": "Seconds before expiry to refresh token"},
        ],
    },
    "oauth2_password": {
        "label": "OAuth2 Password Grant",
        "fields": [
            {"name": "token_url", "label": "Token URL", "type": "url", "required": True},
            {"name": "client_id", "label": "Client ID", "type": "text", "required": True},
            {"name": "client_secret", "label": "Client Secret", "type": "password", "required": False},
            {"name": "username", "label": "Username", "type": "text", "required": True},
            {"name": "password", "label": "Password", "type": "password", "required": True},
            {"name": "scope", "label": "Scope", "type": "text", "required": False},
            {"name": "token_refresh_buffer_sec", "label": "Refresh Buffer (sec)", "type": "number",
             "required": False, "default": 60},
        ],
    },
    "jwt_custom": {
        "label": "Custom JWT",
        "fields": [
            {"name": "algorithm", "label": "Algorithm", "type": "select", "required": True,
             "options": ["HS256", "HS384", "HS512", "RS256", "RS384", "RS512"],
             "default": "HS256"},
            {"name": "secret_or_key", "label": "Secret / Private Key", "type": "password", "required": True,
             "help": "HMAC secret or RSA/EC private key (PEM)"},
            {"name": "issuer", "label": "Issuer (iss)", "type": "text", "required": False},
            {"name": "audience_claim", "label": "Audience (aud)", "type": "text", "required": False},
            {"name": "subject", "label": "Subject (sub)", "type": "text", "required": False},
            {"name": "custom_claims", "label": "Custom Claims (JSON)", "type": "textarea", "required": False,
             "help": "Additional JWT payload claims as JSON object"},
            {"name": "expiry_sec", "label": "Token Expiry (sec)", "type": "number",
             "required": False, "default": 3600},
        ],
    },
}

# Fields that should be encrypted (never returned in plaintext)
_SENSITIVE_FIELDS = {
    "token", "password", "api_key", "client_secret", "secret_or_key",
}


def _mask_config(config: dict) -> dict:
    """Return config with sensitive fields masked."""
    masked = {}
    for k, v in config.items():
        if k in _SENSITIVE_FIELDS and v:
            masked[k] = _mask(str(v))
        else:
            masked[k] = v
    return masked


# ---------- Token generation for test runs ----------

def get_auth_header(provider_id: str) -> Optional[dict]:
    """Resolve an auth provider ID to HTTP headers for test execution.
    Returns dict of headers or None.
    """
    db = get_db()
    row = db.execute("SELECT auth_type, config_encrypted FROM auth_providers WHERE id = ?", (provider_id,)).fetchone()
    if not row:
        return None

    try:
        config = json.loads(_decrypt(row["config_encrypted"]))
    except Exception:
        return None

    auth_type = row["auth_type"]

    if auth_type == "bearer_token":
        return {"Authorization": f"Bearer {config['token']}"}

    elif auth_type == "basic":
        creds = base64.b64encode(f"{config['username']}:{config['password']}".encode()).decode()
        return {"Authorization": f"Basic {creds}"}

    elif auth_type == "api_key":
        return {config.get("header_name", "X-API-Key"): config["api_key"]}

    elif auth_type in ("oauth2_client_credentials", "oauth2_password"):
        # Fetch token from token URL
        return _fetch_oauth2_token(config, auth_type)

    elif auth_type == "jwt_custom":
        return _generate_custom_jwt(config)

    return None


def _fetch_oauth2_token(config: dict, auth_type: str) -> Optional[dict]:
    """Fetch an OAuth2 token using the given config."""
    import httpx

    token_url = config.get("token_url", "")
    if not token_url:
        return None

    data = {}
    if auth_type == "oauth2_client_credentials":
        data = {
            "grant_type": "client_credentials",
            "client_id": config.get("client_id", ""),
            "client_secret": config.get("client_secret", ""),
        }
    elif auth_type == "oauth2_password":
        data = {
            "grant_type": "password",
            "client_id": config.get("client_id", ""),
            "username": config.get("username", ""),
            "password": config.get("password", ""),
        }
        if config.get("client_secret"):
            data["client_secret"] = config["client_secret"]

    if config.get("scope"):
        data["scope"] = config["scope"]
    if config.get("audience"):
        data["audience"] = config["audience"]

    # Merge extra params
    if config.get("extra_params"):
        try:
            extra = json.loads(config["extra_params"]) if isinstance(config["extra_params"], str) else config["extra_params"]
            data.update(extra)
        except Exception:
            pass

    try:
        resp = httpx.post(token_url, data=data, timeout=30)
        if resp.status_code == 200:
            body = resp.json()
            token = body.get("access_token")
            if token:
                return {"Authorization": f"Bearer {token}"}
    except Exception:
        pass

    return None


def _generate_custom_jwt(config: dict) -> Optional[dict]:
    """Generate a JWT token using custom claims."""
    import hashlib as hashlib_mod
    import hmac as hmac_mod
    import time

    alg = config.get("algorithm", "HS256")
    secret = config.get("secret_or_key", "")

    # Only support HMAC algorithms in this basic implementation
    hash_algs = {"HS256": "sha256", "HS384": "sha384", "HS512": "sha512"}
    if alg not in hash_algs:
        return None

    header = {"alg": alg, "typ": "JWT"}
    payload = {}

    now = int(time.time())
    expiry = int(config.get("expiry_sec", 3600))

    payload["iat"] = now
    payload["exp"] = now + expiry

    if config.get("issuer"):
        payload["iss"] = config["issuer"]
    if config.get("audience_claim"):
        payload["aud"] = config["audience_claim"]
    if config.get("subject"):
        payload["sub"] = config["subject"]

    if config.get("custom_claims"):
        try:
            extra = json.loads(config["custom_claims"]) if isinstance(config["custom_claims"], str) else config["custom_claims"]
            payload.update(extra)
        except Exception:
            pass

    def b64url(data):
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    h_part = b64url(json.dumps(header, separators=(",", ":")).encode())
    p_part = b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig_input = f"{h_part}.{p_part}".encode()
    sig = hmac_mod.new(secret.encode(), sig_input, getattr(hashlib_mod, hash_algs[alg])).digest()
    token = f"{h_part}.{p_part}.{b64url(sig)}"

    return {"Authorization": f"Bearer {token}"}


# ---------- Token cache for load test execution ----------

import threading
import time as _time

_token_cache = {}  # provider_id -> {"headers": dict, "expires_at": float}
_token_cache_lock = threading.Lock()


def get_cached_auth_header(provider_id: str) -> Optional[dict]:
    """Get auth headers with caching and auto-refresh for load tests.

    For token-based auth types (OAuth2, JWT), tokens are cached and
    automatically refreshed before expiry. The refresh buffer is configurable
    per auth provider.
    """
    now = _time.time()

    with _token_cache_lock:
        cached = _token_cache.get(provider_id)
        if cached and cached["expires_at"] > now:
            return cached["headers"]

    # Cache miss or expired — resolve fresh headers
    db = get_db()
    row = db.execute("SELECT auth_type, config_encrypted FROM auth_providers WHERE id = ?", (provider_id,)).fetchone()
    if not row:
        return None

    try:
        config = json.loads(_decrypt(row["config_encrypted"]))
    except Exception:
        return None

    auth_type = row["auth_type"]
    headers = get_auth_header(provider_id)
    if not headers:
        return None

    # Determine cache TTL based on auth type
    if auth_type in ("oauth2_client_credentials", "oauth2_password"):
        buffer = int(config.get("token_refresh_buffer_sec", 60))
        # Default token lifetime assumed: 3600s minus buffer
        ttl = 3600 - buffer
    elif auth_type == "jwt_custom":
        expiry_sec = int(config.get("expiry_sec", 3600))
        ttl = max(expiry_sec - 60, 30)  # refresh 60s before expiry
    elif auth_type in ("bearer_token", "basic", "api_key"):
        ttl = 3600  # Static credentials, cache for 1hr
    else:
        ttl = 300

    with _token_cache_lock:
        _token_cache[provider_id] = {
            "headers": headers,
            "expires_at": now + ttl,
        }

    return headers


def clear_token_cache(provider_id: Optional[str] = None):
    """Clear cached tokens. If provider_id given, clear only that one."""
    with _token_cache_lock:
        if provider_id:
            _token_cache.pop(provider_id, None)
        else:
            _token_cache.clear()


# ---------- Plugin ----------

class AuthProviderSaveRequest(BaseModel):
    id: Optional[str] = None
    name: str
    auth_type: str
    config: dict = {}
    description: str = ""


class AuthProviderTestRequest(BaseModel):
    auth_type: str
    config: dict = {}


class AuthProvidersPlugin(PluginBase):
    @property
    def name(self) -> str:
        return "authproviders"

    @property
    def description(self) -> str:
        return "Manage authentication providers for test runs (encrypted storage)"

    def _register_routes(self):
        @self.router.get("/types")
        async def list_types():
            """Return available auth types with their field schemas."""
            return {"types": AUTH_TYPE_FIELDS}

        @self.router.get("/list")
        async def list_providers(request: Request):
            require_auth(request)
            db = get_db()
            rows = db.execute(
                "SELECT id, name, auth_type, description, created_by, created_at, updated_at FROM auth_providers ORDER BY name"
            ).fetchall()
            return {"providers": [dict(r) for r in rows]}

        @self.router.get("/{provider_id}")
        async def get_provider(provider_id: str, request: Request):
            require_auth(request)
            db = get_db()
            row = db.execute("SELECT * FROM auth_providers WHERE id = ?", (provider_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Auth provider not found")

            result = dict(row)
            # Decrypt config but mask sensitive fields
            try:
                config = json.loads(_decrypt(result["config_encrypted"]))
                result["config"] = _mask_config(config)
            except Exception:
                result["config"] = {}
            del result["config_encrypted"]
            return result

        @self.router.post("/save")
        async def save_provider(body: AuthProviderSaveRequest, request: Request):
            user = require_role(request, "maintainer")
            db = get_db()
            now = datetime.now(timezone.utc).isoformat()

            if body.auth_type not in AUTH_TYPE_FIELDS:
                raise HTTPException(400, f"Invalid auth type: {body.auth_type}")

            # Validate required fields
            type_schema = AUTH_TYPE_FIELDS[body.auth_type]
            for field_def in type_schema["fields"]:
                if field_def.get("required") and not body.config.get(field_def["name"]):
                    raise HTTPException(400, f"Field '{field_def['label']}' is required")

            # If updating, merge with existing config (so masked fields aren't overwritten)
            if body.id:
                existing = db.execute("SELECT config_encrypted FROM auth_providers WHERE id = ?", (body.id,)).fetchone()
                if existing:
                    try:
                        old_config = json.loads(_decrypt(existing["config_encrypted"]))
                        # Keep old values for fields that are still masked
                        for k, v in body.config.items():
                            if k in _SENSITIVE_FIELDS and v and "****" in str(v):
                                body.config[k] = old_config.get(k, "")
                    except Exception:
                        pass

            encrypted = _encrypt(json.dumps(body.config))

            if body.id:
                existing = db.execute("SELECT id FROM auth_providers WHERE id = ?", (body.id,)).fetchone()
                if existing:
                    db.execute(
                        "UPDATE auth_providers SET name=?, auth_type=?, config_encrypted=?, description=?, updated_at=? WHERE id=?",
                        (body.name, body.auth_type, encrypted, body.description, now, body.id),
                    )
                    db.commit()
                    clear_token_cache(body.id)
                    return {"id": body.id, "status": "updated"}

            provider_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO auth_providers (id, name, auth_type, config_encrypted, description, created_by, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (provider_id, body.name, body.auth_type, encrypted, body.description, user["username"], now, now),
            )
            db.commit()
            return {"id": provider_id, "status": "created"}

        @self.router.delete("/{provider_id}")
        async def delete_provider(provider_id: str, request: Request):
            require_role(request, "admin")
            db = get_db()
            row = db.execute("SELECT id FROM auth_providers WHERE id = ?", (provider_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Auth provider not found")
            db.execute("DELETE FROM auth_providers WHERE id = ?", (provider_id,))
            db.commit()
            clear_token_cache(provider_id)
            return {"status": "deleted"}

        @self.router.post("/test")
        async def test_provider(body: AuthProviderTestRequest, request: Request):
            """Test an auth provider configuration by attempting to generate headers."""
            require_role(request, "maintainer")

            if body.auth_type not in AUTH_TYPE_FIELDS:
                raise HTTPException(400, f"Invalid auth type: {body.auth_type}")

            try:
                if body.auth_type == "bearer_token":
                    if body.config.get("token"):
                        return {"success": True, "headers": {"Authorization": "Bearer ****"}}
                    return {"success": False, "error": "Token is empty"}

                elif body.auth_type == "basic":
                    if body.config.get("username") and body.config.get("password"):
                        return {"success": True, "headers": {"Authorization": "Basic ****"}}
                    return {"success": False, "error": "Username and password required"}

                elif body.auth_type == "api_key":
                    if body.config.get("api_key"):
                        hdr = body.config.get("header_name", "X-API-Key")
                        return {"success": True, "headers": {hdr: "****"}}
                    return {"success": False, "error": "API key is empty"}

                elif body.auth_type in ("oauth2_client_credentials", "oauth2_password"):
                    headers = _fetch_oauth2_token(body.config, body.auth_type)
                    if headers:
                        return {"success": True, "headers": {"Authorization": "Bearer ****"}, "message": "Token acquired successfully"}
                    return {"success": False, "error": "Failed to acquire token from token URL"}

                elif body.auth_type == "jwt_custom":
                    headers = _generate_custom_jwt(body.config)
                    if headers:
                        return {"success": True, "headers": {"Authorization": "Bearer ****"}, "message": "JWT generated successfully"}
                    return {"success": False, "error": "Failed to generate JWT (only HMAC algorithms supported)"}

            except Exception as e:
                return {"success": False, "error": str(e)}

            return {"success": False, "error": "Unknown auth type"}

        @self.router.get("/{provider_id}/headers")
        async def resolve_headers(provider_id: str, request: Request):
            """Resolve auth provider to actual headers (internal use for engines)."""
            require_role(request, "maintainer")
            headers = get_auth_header(provider_id)
            if headers is None:
                raise HTTPException(400, "Failed to resolve auth headers")
            # Mask the values for API response
            masked = {k: _mask(v) for k, v in headers.items()}
            return {"headers": masked}

        @self.router.post("/{provider_id}/refresh")
        async def refresh_token(provider_id: str, request: Request):
            """Force refresh cached token for a provider."""
            require_role(request, "maintainer")
            clear_token_cache(provider_id)
            headers = get_cached_auth_header(provider_id)
            if headers is None:
                raise HTTPException(400, "Failed to refresh auth headers")
            masked = {k: _mask(v) for k, v in headers.items()}
            return {"headers": masked, "status": "refreshed"}
