"""
Upload completed job logs to Google Drive as a per-job folder (JSON, CSV, images).
"""

from __future__ import annotations

import logging
import mimetypes
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from googleapiclient.http import MediaFileUpload

from src.ConfigLoader import ConfigLoader
from src.google_drive.auth_manager import GoogleAuthManager
from src.google_drive.job_export import build_artifacts, stage_artifacts

log = logging.getLogger(__name__)

_FOLDER_MIME = "application/vnd.google-apps.folder"


def _escape_drive_query_literal(value: str) -> str:
    """Escape a string for use inside single-quoted Drive API query literals."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


class JobDriveBackup:
    """Builds export artifacts from JobLog JSON and uploads them to Drive."""

    def __init__(self, auth: GoogleAuthManager | None = None) -> None:
        self._auth = auth or GoogleAuthManager()
        self._cfg = ConfigLoader()
        if self._cfg.get_google_drive_enabled():
            folder_id = self._cfg.get_google_drive_folder_id().strip()
            if not folder_id:
                raise ValueError(
                    "google_drive.drive_folder_id must be non-empty when "
                    "google_drive.enabled is true"
                )
        self._folder_id = self._cfg.get_google_drive_folder_id()
        self._last_upload: datetime | None = None
        self._last_error: str | None = None

    @property
    def folder_id(self) -> str:
        return self._folder_id

    @property
    def folder_configured(self) -> bool:
        return bool(self._folder_id)

    @property
    def last_upload(self) -> str | None:
        """ISO-8601 UTC timestamp of the last successful upload, or None."""
        if self._last_upload is None:
            return None
        return self._last_upload.isoformat()

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def record_error(self, message: str) -> None:
        """Store the most recent failure without raising an exception."""
        self._last_error = message

    def upload_result(self, file_path: Path) -> None:
        """Export and upload one job log JSON and derived files."""
        if not self._folder_id:
            raise ValueError(
                "google_drive.drive_folder_id is not set in system_config.json"
            )

        drive = self._auth.get_drive_service()
        artifacts = build_artifacts(
            file_path, files_root=self._cfg.get_job_files_dir()
        )

        with tempfile.TemporaryDirectory() as tmp:
            staging = Path(tmp)
            stage_artifacts(artifacts, staging)
            job_parent = self._find_or_create_folder(
                drive, artifacts.stem, self._folder_id
            )
            self._upload_tree(drive, staging / artifacts.stem, job_parent)

        self._last_upload = datetime.now(timezone.utc)
        self._last_error = None
        log.info(
            "[JobDriveBackup] Uploaded job folder %s to Drive", artifacts.stem
        )

    def _find_or_create_folder(self, drive, name: str, parent_id: str) -> str:
        safe_name = _escape_drive_query_literal(name)
        safe_parent = _escape_drive_query_literal(parent_id)
        query = (
            f"name = '{safe_name}' and '{safe_parent}' in parents "
            f"and mimeType = '{_FOLDER_MIME}' and trashed = false"
        )
        result = (
            drive.files()
            .list(q=query, spaces="drive", fields="files(id)", pageSize=1)
            .execute()
        )
        files = result.get("files", [])
        if files:
            return files[0]["id"]

        body = {
            "name": name,
            "mimeType": _FOLDER_MIME,
            "parents": [parent_id],
        }
        created = drive.files().create(body=body, fields="id").execute()
        return created["id"]

    def _upload_tree(self, drive, local_dir: Path, parent_id: str) -> None:
        for entry in sorted(local_dir.iterdir(), key=lambda p: p.name):
            if entry.is_dir():
                folder_id = self._find_or_create_folder(
                    drive, entry.name, parent_id
                )
                self._upload_tree(drive, entry, folder_id)
            else:
                mime, _ = mimetypes.guess_type(entry.name)
                if mime is None:
                    mime = "application/octet-stream"
                media = MediaFileUpload(str(entry), mimetype=mime)
                drive.files().create(
                    body={"name": entry.name, "parents": [parent_id]},
                    media_body=media,
                    fields="id",
                ).execute()
