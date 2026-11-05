"""
Groww API authentication and secure token management.

Authentication flow
-------------------
Groww uses a two-step auth:

  Step 1 — Exchange API Key + (TOTP or Secret) for an ACCESS TOKEN:
      access_token = GrowwAPI.get_access_token(api_key, totp="123456")
      # or approval flow:
      access_token = GrowwAPI.get_access_token(api_key, secret="mysecret")

  Step 2 — Use the access token to construct the client:
      groww = GrowwAPI(access_token)

The access token must be renewed daily (approved via Groww Cloud API Keys page).
There is NO programmatic refresh endpoint — renewal is always manual.

Token storage
-------------
Tokens are cached encrypted on disk using Fernet symmetric encryption when
the `cryptography` package is available. Falls back to plaintext JSON.

Permissions required
--------------------
- Active Trading API Subscription (purchased via Groww Cloud)
- Daily token approval on the Groww Cloud API Keys page
  https://groww.in/trade-api
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional Fernet encryption
# ---------------------------------------------------------------------------
try:
    from cryptography.fernet import Fernet
    _HAS_FERNET = True
except ImportError:
    _HAS_FERNET = False
    logger.warning(
        "cryptography package not installed — tokens stored as plaintext JSON. "
        "pip install cryptography for encrypted storage."
    )

_DEFAULT_TOKEN_PATH = Path.home() / ".groww" / "token_cache.json"
_ENV_ACCESS_TOKEN = "GROWW_API_TOKEN"      # final access token
_ENV_API_KEY      = "GROWW_API_KEY"        # raw API key (pre-auth)
_ENV_SECRET       = "GROWW_API_SECRET"     # for approval flow
_ENV_TOKEN_SECRET = "GROWW_TOKEN_SECRET"   # encryption passphrase


# ---------------------------------------------------------------------------
# Token cache (disk-backed, optionally encrypted)
# ---------------------------------------------------------------------------

class TokenCache:
    """
    Persists a Groww access token between process restarts.

    Token JSON on disk:
        {
            "token": "<encrypted-or-plain-token>",
            "stored_at": <unix-timestamp>,
            "encrypted": true|false
        }
    """

    def __init__(self, path: Path = _DEFAULT_TOKEN_PATH) -> None:
        self._path = path
        self._fernet = self._build_fernet()

    # ------------------------------------------------------------------
    def _build_fernet(self) -> Optional[object]:
        if not _HAS_FERNET:
            return None
        secret = os.environ.get(_ENV_TOKEN_SECRET)
        if not secret:
            return None
        import base64
        raw = hashlib.sha256(secret.encode()).digest()
        key = base64.urlsafe_b64encode(raw)
        return Fernet(key)

    # ------------------------------------------------------------------
    def save(self, token: str) -> None:
        """Encrypt (if possible) and persist token to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        encrypted = False
        stored = token
        if self._fernet:
            stored = self._fernet.encrypt(token.encode()).decode()
            encrypted = True
        payload = {"token": stored, "stored_at": time.time(), "encrypted": encrypted}
        self._path.write_text(json.dumps(payload, indent=2))
        self._path.chmod(0o600)
        logger.info("Groww access token cached at %s (encrypted=%s)", self._path, encrypted)

    # ------------------------------------------------------------------
    def load(self) -> Optional[str]:
        """Load and optionally decrypt cached token."""
        if not self._path.exists():
            return None
        try:
            payload = json.loads(self._path.read_text())
            token = payload["token"]
            if payload.get("encrypted"):
                if not self._fernet:
                    logger.warning(
                        "Token was stored encrypted but GROWW_TOKEN_SECRET is not set — cannot decrypt."
                    )
                    return None
                token = self._fernet.decrypt(token.encode()).decode()
            age_hours = (time.time() - payload.get("stored_at", 0)) / 3600
            if age_hours > 20:
                logger.warning(
                    "Cached Groww token is %.1f h old. Tokens require daily renewal via "
                    "Groww Cloud API Keys page.", age_hours
                )
            return token
        except Exception as exc:
            logger.error("Failed to read token cache: %s", exc)
            return None

    # ------------------------------------------------------------------
    def clear(self) -> None:
        if self._path.exists():
            self._path.unlink()
            logger.info("Groww token cache cleared.")


# ---------------------------------------------------------------------------
# Token resolution
# ---------------------------------------------------------------------------

def get_api_token(cache: Optional[TokenCache] = None) -> str:
    """
    Resolve the Groww access token using this priority:

    1. ``GROWW_API_TOKEN`` env var  (highest priority)
    2. Disk cache (TokenCache)

    Raises
    ------
    RuntimeError
        When no token can be found.

    Notes
    -----
    Token renewal is MANUAL — the user must reactivate the token daily via
    the Groww Cloud API Keys page and update GROWW_API_TOKEN or call
    ``TokenCache().save(new_token)``.
    """
    env_token = os.environ.get(_ENV_ACCESS_TOKEN, "").strip()
    if env_token:
        logger.debug("Groww token sourced from GROWW_API_TOKEN env var.")
        return env_token

    if cache is None:
        cache = TokenCache()
    cached = cache.load()
    if cached:
        logger.debug("Groww token sourced from disk cache.")
        return cached

    raise RuntimeError(
        "Groww access token not found.\n"
        "Options:\n"
        "  1. Set GROWW_API_TOKEN=<your_access_token>\n"
        "  2. Call obtain_access_token() to exchange API key → access token,\n"
        "     then TokenCache().save(token)\n"
        "Get your API key at https://groww.in/trade-api (subscription required)."
    )


def obtain_access_token(
    api_key: Optional[str] = None,
    totp: Optional[str] = None,
    secret: Optional[str] = None,
    save_to_cache: bool = True,
) -> str:
    """
    Exchange a raw Groww API key for an access token.

    Two auth modes (mutually exclusive):
      - TOTP mode:     provide ``totp`` (6-digit code from your authenticator app)
      - Approval mode: provide ``secret`` (from Groww Cloud API Keys)

    If ``api_key`` is not passed, falls back to the GROWW_API_KEY env var.
    If ``secret`` is not passed, falls back to GROWW_API_SECRET env var.

    Parameters
    ----------
    api_key : str, optional
        Raw Groww API key. Reads GROWW_API_KEY if not provided.
    totp : str, optional
        6-digit TOTP code from authenticator app.
    secret : str, optional
        API secret for approval flow. Reads GROWW_API_SECRET if not provided.
    save_to_cache : bool
        If True, persists the resulting access token via TokenCache.

    Returns
    -------
    str
        The access token to pass to ``GrowwAPI(token)``.

    Raises
    ------
    RuntimeError
        If api_key is missing or the exchange fails.

    Notes
    -----
    Requires network access to https://api.groww.in/v1/token/api/access.
    Rate-limits and HTTP errors from Groww are re-raised as RuntimeError.
    """
    # Resolve API key
    resolved_key = (api_key or os.environ.get(_ENV_API_KEY, "")).strip()
    if not resolved_key:
        raise RuntimeError(
            "Groww API key not provided. Set GROWW_API_KEY or pass api_key=."
        )

    # Resolve secret if in approval mode
    if totp is None and secret is None:
        secret = os.environ.get(_ENV_SECRET, "").strip() or None

    if totp is None and secret is None:
        raise RuntimeError(
            "Provide either totp= (TOTP code) or secret= (approval flow secret) "
            "to exchange the API key for an access token."
        )

    try:
        from growwapi import GrowwAPI
        from growwapi.groww.exceptions import GrowwAPIException
    except ImportError as exc:
        raise RuntimeError("growwapi package not installed. Run: pip install growwapi") from exc

    try:
        access_token = GrowwAPI.get_access_token(
            api_key=resolved_key,
            totp=totp,
            secret=secret,
        )
    except Exception as exc:
        raise RuntimeError(f"Groww token exchange failed: {exc}") from exc

    if save_to_cache:
        TokenCache().save(access_token)

    logger.info("Groww access token obtained and cached.")
    return access_token


# ---------------------------------------------------------------------------
# Capability report
# ---------------------------------------------------------------------------

def capability_report() -> dict:
    """
    Documents which Groww API features require extra permissions/activation.
    Reference only — not enforced programmatically.
    """
    return {
        "authentication": {
            "method": "API Key → Access Token (Bearer)",
            "approaches": [
                "TOTP (requires authenticator app linked to Groww account)",
                "Approval/Secret (requires daily approval on Groww Cloud dashboard)",
            ],
            "token_lifetime": "~24 hours; must be renewed daily via Groww Cloud",
            "url": "https://groww.in/trade-api",
        },
        "market_data_rest": {
            "available": True,
            "endpoints": ["get_ltp", "get_ohlc", "get_quote"],
            "notes": "Requires active Trading API Subscription.",
        },
        "market_data_websocket": {
            "available": True,
            "transport": "NATS (via GrowwFeed)",
            "endpoints": [
                "subscribe_ltp", "subscribe_market_depth",
                "subscribe_index_value",
                "subscribe_equity_order_updates",
                "subscribe_fno_order_updates",
                "subscribe_fno_position_updates",
            ],
        },
        "historical_data": {
            "available": True,
            "max_range_per_request": "30 days",
            "intervals": [
                "1minute", "2minute", "3minute", "5minute",
                "10minute", "15minute", "30minute",
                "1hour", "4hour", "1day", "1week", "1month",
            ],
            "notes": "Chunk requests > 30 days. Use get_historical_candles (v2).",
        },
        "order_placement": {
            "available": True,
            "exchanges": ["NSE", "BSE", "MCX"],
            "segments": ["CASH", "FNO", "CURRENCY", "COMMODITY"],
            "products": ["CNC", "MIS", "NRML", "MTF", "BO", "CO"],
            "order_types": ["MARKET", "LIMIT", "SL", "SL_M"],
        },
        "portfolio_holdings": {
            "available": True,
            "notes": "Demat equity holdings only. MF not exposed via Trading API.",
        },
        "margin": {
            "available": "Partial",
            "notes": "get_available_margin_details() returns cash/collateral. "
                     "Span margin calculation not in SDK v1.5.",
        },
        "smart_orders": {
            "available": True,
            "types": ["GTT", "OCO"],
        },
        "user_profile": {
            "available": True,
            "notes": "get_user_profile() returns name, email, PAN, demat info.",
        },
    }