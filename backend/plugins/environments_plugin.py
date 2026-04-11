"""Environments plugin — CRUD for named environment profiles.

Supports HTTP/HTTPS/mTLS, certificate upload (PEM, PFX, cert+key),
auth provider association, custom headers, and SSL verification toggle.
"""

import base64
import json
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, Request, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional, List

from backend.core.plugin_base import PluginBase
from backend.plugins.storage_plugin import get_db
from backend.plugins.auth_plugin import require_auth, require_role


# ---------- Encryption for cert passwords ----------

def _encrypt_cert_password(password: str) -> str:
    """Encrypt certificate password using the auth providers Fernet."""
    if not password:
        return ""
    try:
        from backend.plugins.authproviders_plugin import _encrypt
        return _encrypt(password)
    except Exception:
        return ""


def _decrypt_cert_password(encrypted: str) -> str:
    """Decrypt certificate password."""
    if not encrypted:
        return ""
    try:
        from backend.plugins.authproviders_plugin import _decrypt
        return _decrypt(encrypted)
    except Exception:
        return ""


# ---------- Certificate format definitions ----------

CERT_TYPES = {
    "none": {
        "label": "No Certificate",
        "description": "No client certificate required",
        "fields": [],
    },
    "pem": {
        "label": "PEM Certificate + Key",
        "description": "Separate PEM-encoded certificate and private key files",
        "fields": [
            {"name": "cert_data", "label": "Certificate (PEM)", "type": "file", "accept": ".pem,.crt,.cer", "required": True},
            {"name": "key_data", "label": "Private Key (PEM)", "type": "file", "accept": ".pem,.key", "required": True},
            {"name": "cert_password", "label": "Key Password (if encrypted)", "type": "password", "required": False},
            {"name": "ca_cert_data", "label": "CA Certificate (PEM)", "type": "file", "accept": ".pem,.crt,.cer", "required": False,
             "help": "Certificate Authority bundle for verification"},
        ],
    },
    "pfx": {
        "label": "PFX / PKCS#12",
        "description": "Combined certificate and key in PKCS#12 format",
        "fields": [
            {"name": "cert_data", "label": "PFX File", "type": "file", "accept": ".pfx,.p12", "required": True},
            {"name": "cert_password", "label": "PFX Password", "type": "password", "required": True},
            {"name": "ca_cert_data", "label": "CA Certificate (PEM)", "type": "file", "accept": ".pem,.crt,.cer", "required": False},
        ],
    },
    "cert_key": {
        "label": "Certificate + Key (Base64)",
        "description": "Base64-encoded certificate and key (for copy-paste)",
        "fields": [
            {"name": "cert_data", "label": "Certificate (Base64)", "type": "textarea", "required": True},
            {"name": "key_data", "label": "Private Key (Base64)", "type": "textarea", "required": True},
            {"name": "cert_password", "label": "Key Password", "type": "password", "required": False},
            {"name": "ca_cert_data", "label": "CA Certificate (Base64)", "type": "textarea", "required": False},
        ],
    },
}

TLS_MODES = [
    {"value": "none", "label": "No TLS (HTTP)", "description": "Plain HTTP connection"},
    {"value": "standard", "label": "Standard TLS (HTTPS)", "description": "Server-side TLS verification"},
    {"value": "mtls", "label": "Mutual TLS (mTLS)", "description": "Client and server certificate verification"},
]


class EnvironmentSaveRequest(BaseModel):
    id: Optional[str] = None
    name: str
    platform: str = "cloud"
    base_url: str = ""
    graphql_path: str = "/graphql"
    protocol: str = "https"
    tls_mode: str = "standard"
    cert_type: str = "none"
    cert_data: str = ""
    key_data: str = ""
    cert_password: str = ""
    ca_cert_data: str = ""
    verify_ssl: bool = True
    headers_json: str = "{}"
    auth_provider_id: str = ""
    cert_path: str = ""
    key_path: str = ""
    notes: str = ""


class EnvironmentsPlugin(PluginBase):
    @property
    def name(self) -> str:
        return "environments"

    @property
    def description(self) -> str:
        return "Environment profiles CRUD with TLS/mTLS, certificates, and auth provider support"

    def __init__(self):
        super().__init__()
        self._seed_defaults()

    def _seed_defaults(self):
        try:
            db = get_db()
            count = db.execute("SELECT COUNT(*) as cnt FROM environments").fetchone()["cnt"]
            if count == 0:
                now = datetime.now(timezone.utc).isoformat()
                defaults = [
                    ("local", "cloud", "http://localhost:4000", "/graphql", "http", "none", "Local development"),
                    ("staging", "cloud", "https://staging.example.com", "/graphql", "https", "standard", "Staging environment"),
                    ("production", "cloud", "https://api.example.com", "/graphql", "https", "standard", "Production (read-only tests)"),
                ]
                for name, plat, url, path, proto, tls, notes in defaults:
                    db.execute(
                        "INSERT INTO environments (id,name,platform,base_url,graphql_path,protocol,tls_mode,notes,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (str(uuid.uuid4()), name, plat, url, path, proto, tls, notes, now, now),
                    )
                db.commit()
        except Exception:
            pass

    def _register_routes(self):
        @self.router.get("/cert-types")
        async def list_cert_types():
            """Return available certificate types with field schemas."""
            return {"cert_types": CERT_TYPES, "tls_modes": TLS_MODES}

        @self.router.get("/list")
        async def list_envs(request: Request):
            require_auth(request)
            db = get_db()
            rows = db.execute("SELECT * FROM environments ORDER BY name").fetchall()
            envs = []
            for r in rows:
                env = dict(r)
                # Never return cert password in plaintext
                env.pop("cert_password_encrypted", None)
                env["has_cert_password"] = bool(r["cert_password_encrypted"]) if "cert_password_encrypted" in r.keys() else False
                # Truncate cert data for list view
                for field in ("cert_data", "key_data", "ca_cert_data"):
                    if env.get(field) and len(env[field]) > 50:
                        env[field] = env[field][:40] + "...[truncated]"
                envs.append(env)
            return {"environments": envs}

        @self.router.get("/{env_id}")
        async def get_env(env_id: str, request: Request):
            require_auth(request)
            db = get_db()
            row = db.execute("SELECT * FROM environments WHERE id = ?", (env_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Environment not found")
            env = dict(row)
            env.pop("cert_password_encrypted", None)
            env["has_cert_password"] = bool(row["cert_password_encrypted"]) if "cert_password_encrypted" in row.keys() else False
            return env

        @self.router.post("/save")
        async def save_env(body: EnvironmentSaveRequest, request: Request):
            require_role(request, "maintainer")
            db = get_db()
            now = datetime.now(timezone.utc).isoformat()

            # Validate protocol/tls_mode
            if body.protocol not in ("http", "https", "mtls"):
                raise HTTPException(400, "Invalid protocol. Must be http, https, or mtls")
            if body.tls_mode not in ("none", "standard", "mtls"):
                raise HTTPException(400, "Invalid TLS mode")
            if body.cert_type not in ("", "none", "pem", "pfx", "cert_key"):
                raise HTTPException(400, "Invalid certificate type")

            # Validate headers JSON
            if body.headers_json:
                try:
                    json.loads(body.headers_json)
                except json.JSONDecodeError:
                    raise HTTPException(400, "Invalid headers JSON")

            # Encrypt cert password
            cert_password_enc = _encrypt_cert_password(body.cert_password) if body.cert_password else ""

            # For updates, keep existing cert password if not provided
            if body.id and not body.cert_password:
                existing = db.execute("SELECT cert_password_encrypted FROM environments WHERE id = ?", (body.id,)).fetchone()
                if existing and existing["cert_password_encrypted"]:
                    cert_password_enc = existing["cert_password_encrypted"]

            # For updates, keep existing cert data if new data is truncated/empty
            if body.id:
                existing = db.execute("SELECT cert_data, key_data, ca_cert_data FROM environments WHERE id = ?", (body.id,)).fetchone()
                if existing:
                    if not body.cert_data or "[truncated]" in body.cert_data:
                        body.cert_data = existing["cert_data"] or ""
                    if not body.key_data or "[truncated]" in body.key_data:
                        body.key_data = existing["key_data"] or ""
                    if not body.ca_cert_data or "[truncated]" in body.ca_cert_data:
                        body.ca_cert_data = existing["ca_cert_data"] or ""

            if body.id:
                existing = db.execute("SELECT id FROM environments WHERE id = ?", (body.id,)).fetchone()
                if existing:
                    db.execute(
                        """UPDATE environments SET name=?, platform=?, base_url=?, graphql_path=?,
                        protocol=?, tls_mode=?, cert_type=?, cert_data=?, key_data=?,
                        cert_password_encrypted=?, ca_cert_data=?, verify_ssl=?,
                        headers_json=?, auth_provider_id=?, cert_path=?, key_path=?,
                        notes=?, updated_at=?
                        WHERE id=?""",
                        (body.name, body.platform, body.base_url, body.graphql_path,
                         body.protocol, body.tls_mode, body.cert_type, body.cert_data,
                         body.key_data, cert_password_enc, body.ca_cert_data,
                         1 if body.verify_ssl else 0, body.headers_json,
                         body.auth_provider_id, body.cert_path, body.key_path,
                         body.notes, now, body.id),
                    )
                    db.commit()
                    return {"id": body.id, "status": "updated"}

            env_id = str(uuid.uuid4())
            db.execute(
                """INSERT INTO environments (id,name,platform,base_url,graphql_path,
                protocol,tls_mode,cert_type,cert_data,key_data,cert_password_encrypted,
                ca_cert_data,verify_ssl,headers_json,auth_provider_id,
                cert_path,key_path,notes,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (env_id, body.name, body.platform, body.base_url, body.graphql_path,
                 body.protocol, body.tls_mode, body.cert_type, body.cert_data,
                 body.key_data, cert_password_enc, body.ca_cert_data,
                 1 if body.verify_ssl else 0, body.headers_json,
                 body.auth_provider_id, body.cert_path, body.key_path,
                 body.notes, now, now),
            )
            db.commit()
            return {"id": env_id, "status": "created"}

        @self.router.delete("/{env_id}")
        async def delete_env(env_id: str, request: Request):
            require_role(request, "admin")
            db = get_db()
            row = db.execute("SELECT id FROM environments WHERE id = ?", (env_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Environment not found")
            db.execute("DELETE FROM environments WHERE id = ?", (env_id,))
            db.commit()
            return {"status": "deleted"}

        @self.router.post("/upload-cert/{env_id}")
        async def upload_cert(env_id: str, request: Request,
                              cert_file: Optional[UploadFile] = File(None),
                              key_file: Optional[UploadFile] = File(None),
                              ca_file: Optional[UploadFile] = File(None),
                              cert_password: Optional[str] = Form("")):
            """Upload certificate files for an environment."""
            require_role(request, "maintainer")
            db = get_db()
            row = db.execute("SELECT id FROM environments WHERE id = ?", (env_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Environment not found")

            updates = {}
            if cert_file:
                content = await cert_file.read()
                updates["cert_data"] = base64.b64encode(content).decode()
            if key_file:
                content = await key_file.read()
                updates["key_data"] = base64.b64encode(content).decode()
            if ca_file:
                content = await ca_file.read()
                updates["ca_cert_data"] = base64.b64encode(content).decode()
            if cert_password:
                updates["cert_password_encrypted"] = _encrypt_cert_password(cert_password)

            if not updates:
                raise HTTPException(400, "No files provided")

            now = datetime.now(timezone.utc).isoformat()
            set_clauses = ", ".join(f"{k}=?" for k in updates.keys())
            values = list(updates.values()) + [now, env_id]
            db.execute(f"UPDATE environments SET {set_clauses}, updated_at=? WHERE id=?", values)
            db.commit()
            return {"status": "uploaded", "files": list(updates.keys())}

        @self.router.get("/{env_id}/connection-info")
        async def get_connection_info(env_id: str, request: Request):
            """Get resolved connection info for an environment (for test engines)."""
            require_role(request, "maintainer")
            db = get_db()
            row = db.execute("SELECT * FROM environments WHERE id = ?", (env_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Environment not found")

            env = dict(row)
            result = {
                "base_url": env.get("base_url", ""),
                "graphql_path": env.get("graphql_path", "/graphql"),
                "full_url": f"{env.get('base_url', '')}{env.get('graphql_path', '/graphql')}",
                "protocol": env.get("protocol", "https"),
                "tls_mode": env.get("tls_mode", "standard"),
                "verify_ssl": bool(env.get("verify_ssl", 1)),
                "has_client_cert": bool(env.get("cert_data")),
                "has_ca_cert": bool(env.get("ca_cert_data")),
                "auth_provider_id": env.get("auth_provider_id", ""),
            }

            # Parse extra headers
            try:
                headers = json.loads(env.get("headers_json", "{}"))
                result["headers"] = headers
            except Exception:
                result["headers"] = {}

            # Resolve auth provider headers
            if env.get("auth_provider_id"):
                try:
                    from backend.plugins.authproviders_plugin import get_auth_header
                    auth_headers = get_auth_header(env["auth_provider_id"])
                    if auth_headers:
                        result["auth_headers_resolved"] = True
                    else:
                        result["auth_headers_resolved"] = False
                except Exception:
                    result["auth_headers_resolved"] = False

            return result
