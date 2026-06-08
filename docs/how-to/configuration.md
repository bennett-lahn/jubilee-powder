# Configuration Guide

Machine behavior is configured from checked-in JSON in `jubilee_api_config/`.
Production code should read these values through typed loaders, not inline defaults.

## Source of truth

- `jubilee_api_config/system_config.json` - machine, server, safety, manipulator, trickler, and hardness tester settings.
- `jubilee_api_config/motion_platform_positions.json` - named positions, transitions, and z-height policies.

## How configuration is loaded

- System config: `src/ConfigLoader.py` (`config.system` and typed accessors).
- Motion positions: `PositionRegistry.from_config_file()` via `src/motion_config.py`.

If required fields are missing or wrong type, load fails with `ConfigError`.

## Typical edits

### Change machine address

Update `machine.duet_ip` in `system_config.json`:

```json
{
  "machine": {
    "duet_ip": "192.168.1.200"
  }
}
```

### Change default feedrate

Update `machine.default_feedrate`:

```json
{
  "machine": {
    "default_feedrate": 2800
  }
}
```

### Change tamp defaults and limits

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

## Validation workflow

1. Edit the JSON value.
2. If adding a new required field, add it to the corresponding Pydantic model in `src/ConfigLoader.py`.
3. Read it from typed config access in code (`config.system...` or typed accessor).
4. Run tests and smoke checks.

## Do not do this

- Do not use fallback defaults for machine/safety/trickler config in production code.
- Do not use `dict.get(..., default)` as a substitute for required config.

## Related pages

- [Position Config API](../api/position-config.md)
- [ConfigLoader API](../api/config-loader.md)
- [Architecture](../concepts/architecture.md)
