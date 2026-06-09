"""Google Drive API authentication for the Jubilee automation system.

Uses a service account JSON key file. The credentials path is read from
``system_config.json`` under ``google_drive.credentials_file`` (relative to
the project root).

Example:
    Obtain a cached Drive v3 client::

        from src.google_drive.auth_manager import GoogleAuthManager

        auth = GoogleAuthManager()
        drive = auth.get_drive_service()

Note:
    Credentials and the Drive service are created lazily on the first call to
    :meth:`GoogleAuthManager.get_drive_service`. Call :meth:`invalidate` after
    permission or token errors to force a reload from disk.
"""

from __future__ import annotations

from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from src.ConfigLoader import ConfigLoader

_SCOPES = [
    "https://www.googleapis.com/auth/drive",
]


class GoogleAuthManager:
    """Load service account credentials and vend an authenticated Drive client.

    Credentials are read from ``google_drive.credentials_file`` in
    ``system_config.json`` (path relative to the project root). The Drive
    service is created lazily on the first call to :meth:`get_drive_service`.

    Example:
        ```python
        auth = GoogleAuthManager()
        drive = auth.get_drive_service()
        drive.files().list(pageSize=1).execute()
        ```

    Note:
        The manager caches both credentials and the built service until
        :meth:`invalidate` is called.
    """

    def __init__(self) -> None:
        """Create an unauthenticated manager; credentials load on first use."""
        self._creds: Credentials | None = None
        self._drive_service = None

    def get_drive_service(self):
        """Return an authenticated Google Drive v3 API client.

        Returns:
            googleapiclient.discovery.Resource: Cached Drive v3 service bound
            to the configured service account.

        Raises:
            FileNotFoundError: If the credentials file path does not exist.
        """
        if self._drive_service is None:
            self._drive_service = build(
                "drive", "v3", credentials=self._get_credentials()
            )
        return self._drive_service

    def invalidate(self) -> None:
        """Discard cached credentials and force re-authentication on next use.

        Call after token or permission errors so the next
        :meth:`get_drive_service` reloads credentials from disk.
        """
        self._creds = None
        self._drive_service = None

    def _get_credentials(self) -> Credentials:
        """Load or return cached service account credentials."""
        if self._creds is None or not self._creds.valid:
            credentials_file = self._resolve_credentials_path()
            self._creds = Credentials.from_service_account_file(
                str(credentials_file), scopes=_SCOPES
            )
        return self._creds

    def _resolve_credentials_path(self) -> Path:
        """Resolve ``google_drive.credentials_file`` to an on-disk path.

        Raises:
            FileNotFoundError: If the credentials file does not exist.
        """
        cfg = ConfigLoader()
        path = cfg.get_google_drive_credentials_file()
        if not path.exists():
            raise FileNotFoundError(
                f"Google service account credentials not found at {path}. "
                "Set google_drive.credentials_file in system_config.json to the "
                "correct path relative to the project root."
            )
        return path
