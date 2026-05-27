"""
Google Sheets / Drive synchronizer for the Jubilee automation system.

Sheet layout
------------
Three tabs in a single Google Spreadsheet mirror the local UI:

  Main tab  (worksheet named "Main")
  --------
  Row 1: headers — job_type | status | job_id | started_at | completed_at | result_link | error
  Row 2: the active/last job slot (always a single data row)

  Status values (set by the user or the system):
    Draft     — user is still editing; system ignores this row
    Ready     — user is done; system should start the job when machine is IDLE
    Running   — system has accepted the job and started it
    Complete  — job finished successfully; result_link is populated
    Error     — job failed; error column holds the reason

  Dispensing tab  (worksheet named "Dispensing")
  --------------
  Row 1: headers — well_id | target_weight
  Rows 2-25: one row per well (blank rows are skipped)

  Hardness tab  (worksheet named "Hardness")
  ------------
  Row 1: headers — tray_index | sample_id | mode
  Rows 2+: one row per sample (blank rows are skipped)

Usage
-----
    from src.google_drive.sheets_sync import SheetsSynchronizer

    sync = SheetsSynchronizer()
    job  = sync.poll_for_job()   # dict | None
    if job:
        sync.mark_running("my-job-id")
        ...
        sync.upload_result(Path("/path/to/result.json"))
        sync.mark_complete()
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from googleapiclient.http import MediaFileUpload

from src.ConfigLoader import ConfigLoader
from src.google_drive.auth_manager import GoogleAuthManager

log = logging.getLogger(__name__)

_MAIN_TAB        = "Main"
_DISPENSING_TAB  = "Dispensing"
_HARDNESS_TAB    = "Hardness"

# Column indices in the Main tab (0-based)
_COL_JOB_TYPE     = 0
_COL_STATUS       = 1
_COL_JOB_ID       = 2
_COL_STARTED_AT   = 3
_COL_COMPLETED_AT = 4
_COL_RESULT_LINK  = 5
_COL_ERROR        = 6


class SheetsSynchronizer:
    """Polls a Google Spreadsheet for pending jobs and uploads results to Drive.

    Parameters
    ----------
    auth:
        Optional ``GoogleAuthManager`` instance.  A new one is created if not
        supplied.  Pass an explicit instance in tests to inject a mock.
    """

    def __init__(self, auth: Optional[GoogleAuthManager] = None) -> None:
        self._auth   = auth or GoogleAuthManager()
        self._cfg    = ConfigLoader()
        self._sheet_id    = self._cfg.get("google_drive.spreadsheet_id", "")
        self._folder_id   = self._cfg.get("google_drive.drive_folder_id", "")
        self._connected   = False
        self._last_poll:  Optional[datetime] = None
        self._last_error: Optional[str]      = None

    # ------------------------------------------------------------------
    # Public read / poll API
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def last_poll(self) -> Optional[str]:
        """ISO-8601 UTC timestamp of the last successful poll, or None."""
        if self._last_poll is None:
            return None
        return self._last_poll.isoformat()

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def poll_for_job(self) -> Optional[dict]:
        """Check the Main tab for a job with status == "Ready".

        Returns a dict suitable for passing to the existing job-start logic,
        or ``None`` if no ready job is found or an error occurs.

        Return shape (dispensing)::

            {
                "job_type": "dispensing",
                "wells": [{"well_id": "0", "target_weight": 50.0}, ...]
            }

        Return shape (hardness)::

            {
                "job_type": "hardness",
                "samples": [{"tray_index": 0, "sample_id": "0", "mode": "shore_a"}, ...]
            }
        """
        try:
            gc     = self._auth.get_gspread_client()
            sheet  = gc.open_by_key(self._sheet_id)
            main   = sheet.worksheet(_MAIN_TAB)
            row    = main.row_values(2)   # row 2 is the active job slot

            if not row:
                self._connected = True
                self._last_poll = datetime.now(timezone.utc)
                return None

            row = self._pad_row(row, 7)
            status   = row[_COL_STATUS].strip()
            job_type = row[_COL_JOB_TYPE].strip().lower()

            self._connected = True
            self._last_poll = datetime.now(timezone.utc)
            self._last_error = None

            if status != "Ready":
                return None

            if job_type == "dispensing":
                items = self._parse_dispensing_tab(sheet)
                if not items:
                    log.warning("[SheetsSynchronizer] Dispensing tab is empty; ignoring Ready status.")
                    return None
                return {"job_type": "dispensing", "wells": items}

            if job_type == "hardness":
                items = self._parse_hardness_tab(sheet)
                if not items:
                    log.warning("[SheetsSynchronizer] Hardness tab is empty; ignoring Ready status.")
                    return None
                return {"job_type": "hardness", "samples": items}

            log.warning("[SheetsSynchronizer] Unknown job_type %r in Main tab.", job_type)
            return None

        except Exception as exc:
            self._connected  = False
            self._last_error = str(exc)
            log.error("[SheetsSynchronizer] poll_for_job error: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Public write API — update Main tab status
    # ------------------------------------------------------------------

    def mark_running(self, job_id: str) -> None:
        """Write Running + started_at + job_id to the Main tab row 2."""
        now = datetime.now(timezone.utc).isoformat()
        self._update_main_row({
            _COL_STATUS:     "Running",
            _COL_JOB_ID:     job_id,
            _COL_STARTED_AT: now,
            _COL_ERROR:      "",
        })

    def mark_complete(self) -> None:
        """Write Complete + completed_at to the Main tab row 2."""
        now = datetime.now(timezone.utc).isoformat()
        self._update_main_row({
            _COL_STATUS:       "Complete",
            _COL_COMPLETED_AT: now,
            _COL_ERROR:        "",
        })

    def mark_error(self, message: str) -> None:
        """Write Error + message to the Main tab row 2."""
        now = datetime.now(timezone.utc).isoformat()
        self._update_main_row({
            _COL_STATUS:       "Error",
            _COL_COMPLETED_AT: now,
            _COL_ERROR:        message,
        })

    # ------------------------------------------------------------------
    # Public write API — Drive upload
    # ------------------------------------------------------------------

    def upload_result(self, file_path: Path) -> bool:
        """Upload a JSON result file to the configured Drive folder.

        Parameters
        ----------
        file_path:
            Absolute path to the local JSON file written by ``JobLog.finalize``.

        Returns
        -------
        bool
            ``True`` on success, raises on failure (never returns ``False``).
        """
        drive = self._auth.get_drive_service()

        file_metadata: dict = {"name": file_path.name}
        if self._folder_id:
            file_metadata["parents"] = [self._folder_id]

        media = MediaFileUpload(str(file_path), mimetype="application/json")
        drive.files().create(body=file_metadata, media_body=media, fields="id").execute()

        return True

    # ------------------------------------------------------------------
    # Tab parsers
    # ------------------------------------------------------------------

    def _parse_dispensing_tab(self, sheet) -> list[dict]:
        """Read the Dispensing tab and return a list of well dicts."""
        ws   = sheet.worksheet(_DISPENSING_TAB)
        rows = ws.get_all_values()   # includes header row

        items = []
        for row in rows[1:]:   # skip header
            row = self._pad_row(row, 2)
            well_id_raw      = row[0].strip()
            target_weight_raw = row[1].strip()
            if not well_id_raw or not target_weight_raw:
                continue
            try:
                target_weight = float(target_weight_raw)
            except ValueError:
                log.warning(
                    "[SheetsSynchronizer] Skipping dispensing row with non-numeric "
                    "target_weight %r", target_weight_raw
                )
                continue
            items.append({"well_id": well_id_raw, "target_weight": target_weight})
        return items

    def _parse_hardness_tab(self, sheet) -> list[dict]:
        """Read the Hardness tab and return a list of sample dicts."""
        ws   = sheet.worksheet(_HARDNESS_TAB)
        rows = ws.get_all_values()

        valid_modes = {"shore_a", "shore_a_d", "shore_d"}
        items = []
        for row in rows[1:]:
            row = self._pad_row(row, 3)
            tray_index_raw = row[0].strip()
            sample_id      = row[1].strip()
            mode           = row[2].strip().lower()
            if not tray_index_raw or not sample_id or not mode:
                continue
            try:
                tray_index = int(tray_index_raw)
            except ValueError:
                log.warning(
                    "[SheetsSynchronizer] Skipping hardness row with non-integer "
                    "tray_index %r", tray_index_raw
                )
                continue
            if mode not in valid_modes:
                log.warning(
                    "[SheetsSynchronizer] Skipping hardness row with unknown mode %r", mode
                )
                continue
            items.append({"tray_index": tray_index, "sample_id": sample_id, "mode": mode})
        return items

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _update_main_row(self, updates: dict[int, str]) -> None:
        """Apply column-index-keyed updates to Main tab row 2.

        Fetches the current row first, applies the provided updates by column
        index, then writes the entire row back so unrelated columns are
        preserved.
        """
        try:
            gc    = self._auth.get_gspread_client()
            sheet = gc.open_by_key(self._sheet_id)
            main  = sheet.worksheet(_MAIN_TAB)
            row   = self._pad_row(main.row_values(2), 7)
            for col_idx, value in updates.items():
                row[col_idx] = value
            # gspread uses 1-based row and column indices for update
            main.update(
                range_name="A2:G2",
                values=[row],
            )
        except Exception as exc:
            log.error("[SheetsSynchronizer] _update_main_row error: %s", exc)

    @staticmethod
    def _pad_row(row: list, length: int) -> list:
        """Return row extended with empty strings to at least ``length`` elements."""
        return list(row) + [""] * max(0, length - len(row))
