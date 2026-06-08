# Interpreting Results

Job outputs are stored as JSON logs and exposed by the backend file API.

## Where results come from

- Live/in-memory progress: `GET /api/job/log`
- Persisted files: `GET /api/files` and `GET /api/files/{filename}`
- Stored under: `frontend/api/files/`

## Current persisted shape

Job files contain:

- `metadata` (job-level info like date, outcome, job type)
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

For hardness items, fields include `tray_index`, `sample_index`, `mode`, per-pass results, optional image paths, and `sample_error`.

## What to check

- **Outcome**: `successful`, `cancelled`, or `aborted`
- **Completion**: `completed / total`
- **Per-item status**: `complete`, `active`, `incomplete`, `error`
- **Dispensing accuracy**: compare `actual_weight` vs `target_weight`
- **Hardness completeness**: verify expected passes (`shore_a`, `shore_d`, or both)

## Quick API inspection

```bash
curl http://localhost:8000/api/files
curl http://localhost:8000/api/files/<filename>.json
```

## UI inspection

- Open **Data** screen.
- Select a job JSON file.
- Review arc completion and per-cell statuses in the result grid.

## Related pages

- [Using the Jubilee Powder UI](using-gui.md)
- [Web Frontend Reference](../api/gui/jubilee-gui.md)
