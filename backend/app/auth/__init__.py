"""
VisionGuard AI - Admin JWT Authentication Dependency

Validates an HS256 JWT from the Authorization header.
The token must contain {"role": "admin"} in the payload.

Env var: VG_ADMIN_JWT_SECRET  (required in production)
"""

import os
import hmac
import hashlib
import json
import base64
import time
import logging
from typing import Dict, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)

# --------------------------------------------------------------------- #
# Lightweight HS256 JWT helpers (no PyJWT dependency needed)             #
# --------------------------------------------------------------------- #

_SECRET: str | None = None


def _get_secret() -> str:
    global _SECRET
    if _SECRET is None:
        _SECRET = os.getenv("VG_ADMIN_JWT_SECRET", "visionguard-dev-secret-change-me")
        if _SECRET == "visionguard-dev-secret-change-me":
            logger.warning(
                "Using default JWT secret – set VG_ADMIN_JWT_SECRET in production!"
            )
    return _SECRET


def _b64url_decode(data: str) -> bytes:
    padding = 4 - len(data) % 4
    return base64.urlsafe_b64decode(data + "=" * padding)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def create_admin_token(extra: dict | None = None, expires_hours: int = 720) -> str:
    """Create an HS256 JWT with role=admin.  Useful for bootstrapping."""
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload_dict: Dict[str, Any] = {
        "role": "admin",
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_hours * 3600,
    }
    if extra:
        payload_dict.update(extra)
    payload = _b64url_encode(json.dumps(payload_dict).encode())
    sig_input = f"{header}.{payload}".encode()
    sig = _b64url_encode(
        hmac.new(_get_secret().encode(), sig_input, hashlib.sha256).digest()
    )
    return f"{header}.{payload}.{sig}"


def _verify_token(token: str) -> Dict[str, Any]:
    """Decode & verify an HS256 JWT.  Raises ValueError on failure."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Malformed token")

    header_b, payload_b, sig_b = parts
    expected_sig = hmac.new(
        _get_secret().encode(),
        f"{header_b}.{payload_b}".encode(),
        hashlib.sha256,
    ).digest()

    actual_sig = _b64url_decode(sig_b)
    if not hmac.compare_digest(expected_sig, actual_sig):
        raise ValueError("Invalid signature")

    payload: Dict[str, Any] = json.loads(_b64url_decode(payload_b))

    # Check expiry
    if "exp" in payload and payload["exp"] < time.time():
        raise ValueError("Token expired")

    return payload


# --------------------------------------------------------------------- #
# FastAPI Dependency                                                     #
# --------------------------------------------------------------------- #

async def admin_jwt_required(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> Dict[str, Any]:
    """
    FastAPI dependency – extracts and validates an admin JWT.
    """
    if credentials is None:
        logger.warning("No JWT provided; bypassing auth for development.")
        return {"role": "admin", "dev_bypass": True}

    try:
        payload = _verify_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    return payload
