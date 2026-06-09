# Configuration Guide

Machine behavior is configured from checked-in JSON in `jubilee_api_config/`.
Production code should read these values through typed loaders, not inline defaults.

## Overview

`system_config.json`
: Machine, server, safety, manipulator, trickler, and hardness tester settings.

`motion_platform_positions.json`
: Named positions, transitions, and z-height policies.

Loaders:

- System config: `src/ConfigLoader.py` (`config.system` and typed accessors)
- Motion positions: `PositionRegistry.from_config_file()` via `src/motion_config.py`

If required fields are missing or the wrong type, load fails with `ConfigError`.

!!! warning "No silent fallbacks in production code"
    Do not use `dict.get(..., default)` or inline defaults for required machine, safety, or trickler settings. Missing config must fail at load time.

## Typical Edits

=== "Google Drive backup"

    Enable upload of completed job logs (requires service account credentials and a parent folder ID):

    ```json
    {
      "google_drive": {
        "enabled": true,
        "credentials_file": "jubilee_api_config/service_account.json",
        "drive_folder_id": "your-drive-folder-id",
        "retry_interval_seconds": 300
      }
    }
    ```

    When `enabled` is true, `drive_folder_id` must be non-empty. See [Interpreting Results](results.md) for export layout.

=== "Machine address"

    Update `machine.duet_ip` in `system_config.json`:

    ```json
    {
      "machine": {
        "duet_ip": "192.168.1.200"
      }
    }
    ```

=== "Default feedrate"

    Update `machine.default_feedrate`:

    ```json
    {
      "machine": {
        "default_feedrate": 2800
      }
    }
    ```

=== "Tamp defaults and limits"

    Update values in `manipulator`:

    ```json
    {
      "manipulator": {
        "tamp_depth_min": 10.0,
        "tamp_depth_max": 60.0,
        "tamp_speed_min": 500,
        "tamp_speed_max": 5000,
        "tamp_depth_default": 40.0,
        "tamp_speed_default": 2000
      }
    }
    ```

## Validation Workflow

1. Edit the JSON value in `jubilee_api_config/`.
2. If adding a new required field, add it to the corresponding Pydantic model in `src/ConfigLoader.py`.
3. Read it from typed config access in code (`config.system...` or a typed accessor).
4. Restart the Python process (config is loaded once at launch).
5. Run tests and smoke checks.

!!! tip "Verify physical positions after edits"
    After changing positions in `motion_platform_positions.json`, jog to the new coordinates in Duet Web Control before running a full automation job.

## Do Not Do This

- Do not use fallback defaults for machine, safety, or trickler config in production code.
- Do not use `dict.get(..., default)` as a substitute for required config.
- Do not move labware without updating `motion_platform_positions.json` to match.

## See Also

- [Position Config API](../api/position-config.md)
- [ConfigLoader API](../api/config-loader.md)
- [Architecture](../concepts/architecture.md)
- [Best Practices](../concepts/best-practices.md)
