# Interpreting Results

Job outputs are stored as JSON logs by `JobLog` and exposed by the backend file API.

## Overview

Results are available in two forms:

- **Live progress** during a job (`GET /api/job/log`)
- **Persisted job files** after completion (`GET /api/files`, `GET /api/files/{filename}`)

Files are stored under the configured job files directory (`paths.job_files_dir` in `system_config.json`, typically `frontend/api/files/`).

!!! note "On-disk file naming"
    Completed logs use the pattern `{id:04d}_{YYYY-MM-DD}_{type}_{count}.json` where `id` is a sequential integer, `type` is `dispensing` or `hardness`, and `count` is the number of planned items. Hardness images for job `0012` live under `images/0012/`.

## Persisted Job Shape

`JobLog` writes two top-level sections:

- `metadata` (job-level info like date, outcome, job type, `units_completed`)
- `state` with item arrays (`molds` for dispensing, `samples` for hardness)

Typical normalized fields used by the UI:

```json
{
  "job_type": "dispensing",
  "date": "2026-06-07",
  "status": "successful",
  "completed": 6,
  "total": 6,
  "items": [
    {
      "well_id": "0",
      "target_weight": 50.0,
      "actual_weight": 49.98,
      "status": "complete"
    }
  ]
}
```

For hardness items, fields include `tray_index`, `sample_index`, `mode`, per-pass results (`result_shore_a`, `result_shore_d`), per-pass statuses, optional image paths, and `sample_error`.

=== "Dispensing on disk"

    ```json
    {
      "metadata": {
        "id": 12,
        "date": "2026-06-07",
        "job_type": "dispensing",
        "outcome": "successful",
        "units_completed": 2
      },
      "state": {
        "molds": [
          {
            "well_id": "0",
            "target_weight": 50.0,
            "actual_weight": 49.98,
            "status": "complete"
          }
        ]
      }
    }
    ```

=== "Hardness on disk"

    ```json
    {
      "metadata": {
        "id": 13,
        "date": "2026-06-07",
        "job_type": "hardness",
        "outcome": "successful",
        "units_completed": 1
      },
      "state": {
        "samples": [
          {
            "tray_index": 0,
            "sample_index": 0,
            "mode": "shore_a_d",
            "result_shore_a": 61.0,
            "result_shore_d": 58.5,
            "status_shore_a": "complete",
            "status_shore_d": "complete",
            "status": "complete"
          }
        ]
      }
    }
    ```

## What to Check

| Check | What to look for |
|-------|------------------|
| Outcome | `successful`, `cancelled`, or `aborted` |
| Completion | `completed / total` |
| Per-item status | `complete`, `active`, `incomplete`, `error` |
| Dispensing accuracy | `actual_weight` vs `target_weight` |
| Hardness completeness | Expected passes (`shore_a`, `shore_d`, or both) |

!!! tip "Start with outcome and completion"
    A `successful` job with `completed == total` and all items `complete` is a clean run. Investigate any `error` or `incomplete` items before trusting the batch.

## Inspect Results

=== "API"

    ```bash
    curl http://localhost:8000/api/files
    curl http://localhost:8000/api/files/<filename>.json
    ```

=== "Automation UI"

    1. Open the **Data** screen.
    2. Select a job JSON file.
    3. Review arc completion and per-cell statuses in the result grid.

=== "Google Drive backup"

    When `google_drive.enabled` is true, completed logs are exported to Drive as a per-job folder containing the JSON, derived CSV files, and hardness images. Check upload status on the Settings screen (`last_upload`, `last_error`).

    Required config fields when enabled:

    - `google_drive.credentials_file`
    - `google_drive.drive_folder_id` (non-empty)
    - `google_drive.retry_interval_seconds`

!!! warning "Drive export requires complete metadata"
    Upload fails if `metadata.job_type`, `metadata.id`, or the expected `state.molds` / `state.samples` section is missing from the JSON file.

## See Also

- [Using the Jubilee Powder UI](using-gui.md)
- [Run Operations on New Data](run-new-data.md)
- [Web Frontend Reference](../api/gui/jubilee-gui.md)
