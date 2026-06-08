# ConfigLoader API Reference

`ConfigLoader` is the typed loader for `jubilee_api_config/system_config.json`.

## Responsibilities

- Load and validate config using Pydantic models.
- Expose typed access via `config.system` and helper getters.
- Fail fast with `ConfigError` on missing/invalid required fields.

## Module docs

::: src.ConfigLoader
    options:
      members: true
      show_root_heading: true
      show_source: false

## Basic usage

```python
from src.ConfigLoader import config

duet_ip = config.get_duet_ip()
scale_port = config.get_scale_port()
feedrate = config.get_default_feedrate()
tamp_depth, tamp_speed = config.get_tamp_defaults()
```

or read typed models directly:

```python
from src.ConfigLoader import config

duet_ip = config.system.machine.duet_ip
mock_hw = config.system.server.mock_hardware
coarse_feedrate = config.system.trickler.coarse_feedrate
```

## Test-only loading

Use `from_file()` for fixture/temp config:

```python
from pathlib import Path
from src.ConfigLoader import ConfigLoader

loader = ConfigLoader.from_file(
    Path("tmp/system_config.json"),
    project_root=Path("."),
)
```

## Required config rule

- Keep machine behavior in JSON.
- Do not use silent fallback defaults in production paths.
- Add new required fields to the corresponding Pydantic model so validation catches issues at load time.

## Related pages

- [Configuration Guide](../how-to/configuration.md)
- [Position Config API](position-config.md)
