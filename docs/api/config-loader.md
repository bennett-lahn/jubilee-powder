# ConfigLoader API Reference

`ConfigLoader` is the typed loader for `jubilee_api_config/system_config.json`. It validates machine, server, safety, manipulator, trickler, and hardness-tester settings at import time and exposes them through Pydantic models and typed accessors.

!!! note "Singleton in production"
    Import the module-level `config` singleton in application code. Use `ConfigLoader.from_file()` only in tests or tooling that needs an alternate config path.

## Overview

`ConfigLoader`:

- Loads and validates config using Pydantic models
- Exposes typed access via `config.system` and helper getters
- Fails fast with `ConfigError` on missing or invalid required fields

| Config file | Loader | Primary access |
|-------------|--------|----------------|
| `jubilee_api_config/system_config.json` | `ConfigLoader` | `config.system`, typed getters |
| `jubilee_api_config/motion_platform_positions.json` | `PositionRegistry` (`src/motion_config.py`) | [Position Configuration](position-config.md) |

## Class Reference

::: src.ConfigLoader
    options:
      members: true
      show_root_heading: true
      show_source: false
      group_by_category: true

## Basic usage

=== "Typed getters"

    ```python
    from src.ConfigLoader import config

    duet_ip = config.get_duet_ip()
    scale_port = config.get_scale_port()
    feedrate = config.get_default_feedrate()
    tamp_depth, tamp_speed = config.get_tamp_defaults()
    ```

=== "Pydantic models"

    ```python
    from src.ConfigLoader import config

    duet_ip = config.system.machine.duet_ip
    mock_hw = config.system.server.mock_hardware
    coarse_feedrate = config.system.trickler.coarse_feedrate
    ```

!!! tip "Pick one access style"
    Prefer `config.system.<section>.<field>` when you need several values from the same section. Use typed getters when a single accessor is enough.

## Test-only loading

???+ note "Alternate paths in tests and fixtures"
    Production code uses the import-time singleton. For temporary or fixture configs, construct a loader explicitly:

    ```python
    from pathlib import Path
    from src.ConfigLoader import ConfigLoader

    loader = ConfigLoader.from_file(
        Path("tmp/system_config.json"),
        project_root=Path("."),
    )
    ```

## Required config rule

!!! warning "Config is the source of truth"
    - Keep machine behavior in checked-in JSON under `jubilee_api_config/`.
    - Do not use silent fallback defaults in production paths (`src/`, `frontend/src/hardware_manager.py`, etc.).
    - Add new required fields to the corresponding Pydantic model so validation catches issues at load time.

    See the [Configuration Guide](../how-to/configuration.md) for the full edit workflow.

## See Also

- [Configuration Guide](../how-to/configuration.md) - editing `system_config.json`
- [Position Configuration](position-config.md) - `motion_platform_positions.json` schema and transitions
- [JubileeManager](jubilee-manager.md) - primary runtime entry point that consumes this config
- [MotionPlatformStateMachine](motion-platform.md) - loads position config at `connect()` time
