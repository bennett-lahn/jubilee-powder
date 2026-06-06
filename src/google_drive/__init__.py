"""Google Drive job log backup.

When ``google_drive.enabled`` is true in ``jubilee_api_config/system_config.json``,
these modules require (via ``ConfigLoader``):

- ``google_drive.credentials_file`` - OAuth client secrets path
- ``google_drive.drive_folder_id`` - parent Drive folder ID (non-empty)
- ``google_drive.retry_interval_seconds`` - upload retry interval
- ``paths.job_files_dir`` - local job JSON and image root (for export staging)

Job export also requires completed job logs to include ``metadata.job_type``,
``metadata.id``, and the appropriate ``state.molds`` or ``state.samples`` section.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.google_drive.drive_backup import JobDriveBackup

__all__ = ["JobDriveBackup"]


def __getattr__(name: str):
    if name == "JobDriveBackup":
        from src.google_drive.drive_backup import JobDriveBackup

        return JobDriveBackup
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
