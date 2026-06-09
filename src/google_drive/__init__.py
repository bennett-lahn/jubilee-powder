"""Google Drive job log backup.

When ``google_drive.enabled`` is true in ``api_config/system_config.json``,
these modules require (via :class:`~src.ConfigLoader.ConfigLoader`):

- ``google_drive.credentials_file`` - service account JSON key path
- ``google_drive.drive_folder_id`` - parent Drive folder ID (non-empty)
- ``google_drive.retry_interval_seconds`` - upload retry interval
- ``paths.job_files_dir`` - local job JSON and image root (for export staging)

Example:
    Lazy import from the package root::

        from src.google_drive import JobDriveBackup

        backup = JobDriveBackup()
        backup.upload_result(Path("frontend/api/files/0012_2026-06-07_dispensing_6.json"))

Note:
    Job export requires completed logs to include ``metadata.job_type``,
    ``metadata.id``, and the appropriate ``state.molds`` or ``state.samples``
    section. See :mod:`src.google_drive.job_export` for artifact layout.

Warning:
    When ``google_drive.enabled`` is true, ``google_drive.drive_folder_id`` must
    be non-empty or :class:`~src.google_drive.drive_backup.JobDriveBackup`
    construction raises :class:`ValueError`.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.google_drive.drive_backup import JobDriveBackup

__all__ = ["JobDriveBackup"]


def __getattr__(name: str):
    """Lazy-import :class:`~src.google_drive.drive_backup.JobDriveBackup`.

    Args:
        name: Attribute name requested by the importer.

    Returns:
        The requested export when ``name`` is ``"JobDriveBackup"``.

    Raises:
        AttributeError: For any other attribute name.
    """
    if name == "JobDriveBackup":
        from src.google_drive.drive_backup import JobDriveBackup

        return JobDriveBackup
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
