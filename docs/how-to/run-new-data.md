# Run Operations on New Data

Use this workflow when you want to run jobs against a new recipe set or a different mold/sample selection.

## Recommended path

For daily operation, use the web UI:

- [Using the Jubilee Powder UI](using-gui.md)
- [Building and Running the Web UI](running.md)

For scripted runs, use `JubileeManager` with config-driven setup.

## 1) Verify configuration

Before running, confirm:

- `system_config.json` has correct machine IP, scale port, dispenser counts, and tamp/trickler settings.
- `motion_platform_positions.json` contains the positions used by your workflow.

See:

- [Configuration Guide](configuration.md)
- [Position Config API](../api/position-config.md)

## 2) Prepare input payload

Dispensing job payload shape:

```json
{
  "job_type": "dispensing",
  "wells": [
    { "well_id": "0", "target_weight": 50.0 },
    { "well_id": "1", "target_weight": 45.0 }
  ]
}
```

Hardness job payload shape:

```json
{
  "job_type": "hardness",
  "samples": [
    { "tray_index": 0, "sample_index": 0, "mode": "shore_a" },
    { "tray_index": 0, "sample_index": 1, "mode": "shore_d" }
  ]
}
```

## 3) Run and monitor

- Start from idle state.
- Submit one small test job first.
- Monitor progress on Home screen (`running`, `completed`, `current_item`, `error`).

## 4) Review output

Results are written as job log files in `frontend/api/files/`.
Use the Data screen or `/api/files` endpoints to inspect them.

See:

- [Interpreting Results](results.md)
- [Web Frontend Reference](../api/gui/jubilee-gui.md)

## 5) Safety notes

- Do not bypass configured motion transitions.
- If machine enters `error`, reconnect before starting a new job.
- Prefer small validation batches before full production runs.
