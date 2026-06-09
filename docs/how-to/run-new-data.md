# Run Operations on New Data

Use this workflow when you want to run jobs against a new recipe set or a different mold or sample selection.

## Overview

=== "Web UI (recommended)"

    For daily operation, use the browser interface:

    1. [Building and Running the Web UI](running.md) - start the server
    2. [Using the Jubilee Powder UI](using-gui.md) - configure, connect, and submit jobs
    3. [Interpreting Results](results.md) - review job logs on the Data screen

=== "Python scripts"

    For scripted runs, use `JubileeManager` with config-driven setup. See [Quick Start Guide](../getting-started/quickstart.md).

## Prerequisites

!!! info "Before your first run on new data"
    - [ ] `system_config.json` has correct machine IP, scale port, dispenser counts, and tamp or trickler settings
    - [ ] `motion_platform_positions.json` contains the positions used by your workflow
    - [ ] Deck is clear and labware matches configuration
    - [ ] Machine is idle and connected (or ready to connect)

See [Configuration Guide](configuration.md) and [Position Config API](../api/position-config.md).

## Steps

### 1. Verify configuration

Confirm `jubilee_api_config/` matches your physical setup. If you moved labware, update position config first.

### 2. Prepare input payload

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

### 3. Run and monitor

1. Start from idle state.
2. Submit one small test job first (single well or sample).
3. Monitor progress on the Home screen (`running`, `completed`, `current_item`, `error`).

!!! warning "Supervise the first run"
    Sit at the machine with access to the emergency stop for the first execution on new data. See [Best Practices](../concepts/best-practices.md).

### 4. Review output

Results are written as job log files in `frontend/api/files/`.
Use the Data screen or `/api/files` endpoints to inspect them.

See [Interpreting Results](results.md).

### 5. Scale up

After a successful validation batch, run the full recipe set.

## Safety Notes

- Do not bypass configured motion transitions.
- If the machine enters `error`, reconnect before starting a new job.
- Prefer small validation batches before full production runs.

## See Also

- [Using the Jubilee Powder UI](using-gui.md)
- [Interpreting Results](results.md)
- [Web Frontend Reference](../api/gui/jubilee-gui.md)
- [Best Practices](../concepts/best-practices.md)
