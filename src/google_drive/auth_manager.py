"""
Google API authentication manager for the Jubilee automation system.

Uses a service account JSON key file to authenticate with Google Sheets and
Google Drive APIs. The credentials path is read from system_config.json under
the ``google_drive.credentials_file`` key (relative to the project root).

Usage
-----
    from src.google_drive.auth_manager import GoogleAuthManager

    auth = GoogleAuthManager()
    gc     = auth.get_gspread_client()   # gspread.Client
    drive  = auth.get_drive_service()    # googleapiclient Resource
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from src.ConfigLoader import ConfigLoader

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Resolved at import time so it works regardless of cwd.
_PROJECT_ROOT = Path(__file__).parent.parent.parent


class GoogleAuthManager:
    """Loads service account credentials and vends authenticated API clients.

    Clients are cached after the first call so subsequent callers reuse the
    same connection without re-reading the credentials file.
    """

    def __init__(self) -> None:
        self._creds: Optional[Credentials] = None
        self._gspread_client: Optional[gspread.Client] = None
        self._drive_service = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_gspread_client(self) -> gspread.Client:
        """Return an authenticated gspread client, creating it on first call."""
        if self._gspread_client is None:
            self._gspread_client = gspread.authorize(self._get_credentials())
        return self._gspread_client

    def get_drive_service(self):
        """Return an authenticated Google Drive v3 service, creating it on first call."""
        if self._drive_service is None:
            self._drive_service = build(
                "drive", "v3", credentials=self._get_credentials()
            )
        return self._drive_service

    def invalidate(self) -> None:
        """Force the next call to re-authenticate (e.g. after a token error)."""
        self._creds = None
        self._gspread_client = None
        self._drive_service = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_credentials(self) -> Credentials:
        if self._creds is None or not self._creds.valid:
            credentials_file = self._resolve_credentials_path()
            self._creds = Credentials.from_service_account_file(
                str(credentials_file), scopes=_SCOPES
            )
        return self._creds

    def _resolve_credentials_path(self) -> Path:
        cfg = ConfigLoader()
        rel_path = cfg.get("google_drive.credentials_file", "jubilee_api_config/service_account.json")
        path = _PROJECT_ROOT / rel_path
        if not path.exists():
            raise FileNotFoundError(
                f"Google service account credentials not found at {path}. "
                "Set google_drive.credentials_file in system_config.json to the "
                "correct path relative to the project root."
            )
        return path
