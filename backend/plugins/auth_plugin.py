"""Auth plugin — Manual JWT HS256, hardcoded users, role hierarchy, feature flags."""

import base64
import hashlib
import hmac
import json
import time
from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel

from backend.core.plugin_base import PluginBase
from backend.config import get_settings

# Hardcoded users
_USERS = {
    "admin": {"password": "admin123", "role": "admin", "display_name": "Admin"},
    "maintainer": {"password": "maintainer123", "role": "maintainer", "display_name": "Maintainer"},
    "reader": {"password": "reader123", "role": "reader", "display_name": "Reader"},
}

# Role hierarchy: higher index = more permissions
_ROLE_HIERARCHY = {"reader": 0, "maintainer": 1, "admin": 2}

# Feature flag definitions: flag_name -> minimum role required
FLAG_DEFS = {
    "tests.create": "maintainer",
    "tests.delete": "maintainer",
    "tests.run": "reader",
    "tests.stop": "reader",
    "configs.create": "maintainer",
    "configs.delete": "maintainer",
    "environments.create": "maintainer",
    "environments.delete": "admin",
    "storage.clear": "admin",
    "cleanup.run": "maintainer",
    "results.export": "reader",
    "results.notes": "maintainer",
}


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def _create_jwt(payload: dict, secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    h = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signature_input = f"{h}.{p}".encode()
    sig = hmac.new(secret.encode(), signature_input, hashlib.sha256).digest()
    s = _b64url_encode(sig)
    return f"{h}.{p}.{s}"


def _decode_jwt(token: str, secret: str) -> Optional[dict]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None

        signature_input = f"{parts[0]}.{parts[1]}".encode()
        expected_sig = hmac.new(secret.encode(), signature_input, hashlib.sha256).digest()
        actual_sig = _b64url_decode(parts[2])

        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        payload = json.loads(_b64url_decode(parts[1]))

        if payload.get("exp", 0) < time.time():
            return None

        return payload
    except Exception:
        return None


def get_current_user(request: Request) -> Optional[dict]:
    """Extract and validate JWT from request. Returns user dict or None."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]
    settings = get_settings()
    payload = _decode_jwt(token, settings.JWT_SECRET)
    if not payload:
        return None

    return {
        "username": payload.get("sub"),
        "role": payload.get("role"),
        "display_name": payload.get("name"),
    }


def require_auth(request: Request) -> dict:
    """Get current user or raise 401."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_role(request: Request, min_role: str) -> dict:
    """Get current user and verify minimum role, or raise 403."""
    user = require_auth(request)
    user_level = _ROLE_HIERARCHY.get(user["role"], -1)
    required_level = _ROLE_HIERARCHY.get(min_role, 999)
    if user_level < required_level:
        raise HTTPException(status_code=403, detail=f"Requires {min_role} role or higher")
    return user


def has_role(user_role: str, min_role: str) -> bool:
    return _ROLE_HIERARCHY.get(user_role, -1) >= _ROLE_HIERARCHY.get(min_role, 999)


def get_flags_for_role(role: str) -> list:
    """Return list of feature flags available for a given role."""
    return [flag for flag, min_role in FLAG_DEFS.items() if has_role(role, min_role)]


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthPlugin(PluginBase):
    @property
    def name(self) -> str:
        return "auth"

    @property
    def description(self) -> str:
        return "JWT HS256 authentication, RBAC, feature flags"

    def _register_routes(self):
        @self.router.post("/login")
        async def login(body: LoginRequest):
            user = _USERS.get(body.username)
            if not user or user["password"] != body.password:
                raise HTTPException(status_code=401, detail="Invalid credentials")

            settings = get_settings()
            payload = {
                "sub": body.username,
                "role": user["role"],
                "name": user["display_name"],
                "iat": int(time.time()),
                "exp": int(time.time()) + settings.JWT_EXPIRY_HOURS * 3600,
            }
            token = _create_jwt(payload, settings.JWT_SECRET)

            return {
                "token": token,
                "user": {
                    "username": body.username,
                    "role": user["role"],
                    "display_name": user["display_name"],
                },
                "flags": get_flags_for_role(user["role"]),
            }

        @self.router.get("/me")
        async def get_me(request: Request):
            user = require_auth(request)
            return {
                "user": user,
                "flags": get_flags_for_role(user["role"]),
            }

        @self.router.get("/flags")
        async def get_flags(request: Request):
            user = require_auth(request)
            return {
                "flags": get_flags_for_role(user["role"]),
                "all_flags": FLAG_DEFS,
            }
