"""Typed loader for ``api_config/system_config.json``.

The module exposes a process-wide ``config`` singleton that validates machine
settings at import time. Use :class:`ConfigLoader` directly only when loading
alternate paths in tests via :meth:`ConfigLoader.from_file`.

For position and action definitions, see
``api_config/motion_platform_positions.json`` and
:class:`~src.MotionPlatformStateMachine.PositionRegistry`.

Example:
    Read validated settings from the singleton::

        from src.ConfigLoader import config

        duet_ip = config.get_duet_ip()
        feedrate = config.system.machine.default_feedrate

Note:
    Required fields must live in JSON. This loader does not substitute inline
    defaults for missing machine config.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator


class ConfigError(Exception):
    """Raised when ``system_config.json`` is missing, malformed, or fails validation."""


class PathsConfig(BaseModel):
    """Filesystem paths section (``paths``)."""

    job_files_dir: str


class SafetyConfig(BaseModel):
    """Dispense safety limits (``safety``)."""

    max_weight_per_well: float
    weight_tolerance: float


class ServerConfig(BaseModel):
    """Web server and simulation settings (``server``)."""

    cors_origins: list[str]
    mock_hardware: bool


class MachineConfig(BaseModel):
    """Duet controller and hardware counts (``machine``)."""

    duet_ip: str
    default_feedrate: int
    tamper_travel_position: float
    scale_port: str
    num_dispensers: int
    pistons_per_dispenser: int


class ToolRef(BaseModel):
    """Tool index and registered name used by the Jubilee firmware."""

    index: int
    name: str


class ToolsConfig(BaseModel):
    """Registered toolheads (``tools``). Extra tool keys are allowed."""

    model_config = ConfigDict(extra="allow")
    manipulator: ToolRef


class ManipulatorConfig(BaseModel):
    """Tamper axis letter and depth/speed limits (``manipulator``)."""

    tamper_axis: str
    tamp_depth_min: float
    tamp_depth_max: float
    tamp_speed_min: int
    tamp_speed_max: int
    tamp_depth_default: float
    tamp_speed_default: int


class TricklerConfig(BaseModel):
    """Powder trickler tuning parameters (``trickler``)."""

    flow_ema_alpha: float
    yield_ema_alpha: float
    jam_yield_threshold: float
    jam_iter_threshold: int
    jam_auto_recovery_vibration_amplitude: float
    jam_auto_recovery_wait_seconds: float
    max_step_size_mm: float
    min_step_size_mm: float
    warmup_steps: int
    warmup_max_step_mm: float
    coarse_threshold_pct: float
    finish_threshold_pct: float
    coarse_target_steps: int
    coarse_feedrate: int
    fine_feedrate: int
    coarse_vibration_amplitude: float
    fine_vibration_amplitude: float
    max_dribble_step_mm: float


class GoogleDriveConfig(BaseModel):
    """Optional Google Drive backup settings (``google_drive``)."""

    enabled: bool
    credentials_file: str
    drive_folder_id: str
    retry_interval_seconds: int

    @model_validator(mode="after")
    def folder_id_when_enabled(self) -> "GoogleDriveConfig":
        """Require a non-empty folder id when backup is enabled."""
        if self.enabled and not self.drive_folder_id.strip():
            raise ValueError(
                "google_drive.drive_folder_id must be non-empty when google_drive.enabled is true"
            )
        return self


class ButtonServosConfig(BaseModel):
    """Servo angles for hardness tester front-panel buttons."""

    servo: str
    power_press_angle: int
    power_release_angle: int
    zero_press_angle: int
    zero_release_angle: int


class HardnessTesterToolConfig(BaseModel):
    """Hardness tester tool registration (index and name)."""

    index: int
    name: str


class HardnessTesterConfig(BaseModel):
    """Per-mode hardness tester hardware and calibration settings."""

    use_camera: bool
    tool: HardnessTesterToolConfig
    lcd_calibration_path: str
    tip_length_mm: float
    button_servos: ButtonServosConfig
    cam_usb_path: str


class HardnessTestersConfig(BaseModel):
    """Shore-A and Shore-D hardness tester profiles (``hardness_testers``)."""

    shore_a: HardnessTesterConfig
    shore_d: HardnessTesterConfig


class SystemConfig(BaseModel):
    """Root Pydantic model for ``system_config.json``."""

    paths: PathsConfig
    safety: SafetyConfig
    server: ServerConfig
    machine: MachineConfig
    tools: ToolsConfig
    manipulator: ManipulatorConfig
    trickler: TricklerConfig
    google_drive: GoogleDriveConfig
    hardness_testers: HardnessTestersConfig


def _parse_system_config(raw: dict[str, Any], path: Path) -> SystemConfig:
    try:
        return SystemConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"Invalid system_config ({path}): {exc}") from exc


class ConfigLoader:
    """Singleton loader for validated ``system_config.json``.

    Access the process-wide instance via the module-level ``config`` object or
    construct with ``ConfigLoader()`` (returns the same singleton). For tests,
    use :meth:`from_file` or :meth:`reset_singleton_for_tests`.

    Attributes:
        system: Validated :class:`SystemConfig` parsed from disk.

    Note:
        Prefer ``config.system.<section>.<field>`` when reading several values
        from one section; use typed getters for single fields.
    """

    _instance: "ConfigLoader" | None = None

    def __new__(cls) -> "ConfigLoader":
        """Return the singleton instance, creating it on first access."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Load ``system_config.json`` from the project ``api_config`` directory."""
        if getattr(self, "_initialized", False):
            return
        self._project_root = Path(__file__).parent.parent
        self._system_config_path = (
            self._project_root / "api_config" / "system_config.json"
        )
        self._load_config()
        self._initialized = True

    @classmethod
    def from_file(
        cls, config_path: Path, project_root: Path | None = None
    ) -> "ConfigLoader":
        """Load config from an arbitrary path without touching the singleton.

        Args:
            config_path: Path to a ``system_config.json`` file.
            project_root: Project root used to resolve relative paths in config.
                When omitted, inferred from ``config_path`` when it lives under
                ``api_config/``.

        Returns:
            A standalone :class:`ConfigLoader` instance bound to ``config_path``.
        """
        loader = object.__new__(cls)
        loader._initialized = False
        config_path = config_path.resolve()
        if project_root is not None:
            loader._project_root = project_root.resolve()
        elif config_path.parent.name == "api_config":
            loader._project_root = config_path.parent.parent
        else:
            loader._project_root = Path(__file__).parent.parent
        loader._system_config_path = config_path
        loader._load_config()
        loader._initialized = True
        return loader

    @classmethod
    def reset_singleton_for_tests(cls) -> None:
        """Clear the singleton so the next ``ConfigLoader()`` reloads from disk."""
        cls._instance = None

    @property
    def project_root(self) -> Path:
        """Repository root directory (parent of ``src/``)."""
        return self._project_root

    @property
    def system(self) -> SystemConfig:
        """Validated root config model."""
        return self._system

    def _load_config(self) -> None:
        with open(self._system_config_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        self._system = _parse_system_config(raw, self._system_config_path)

    def get_api_config_dir(self) -> Path:
        """Return the ``api_config`` directory under :attr:`project_root`."""
        return self._project_root / "api_config"

    def get_system_config_path(self) -> Path:
        """Return the resolved path to the loaded ``system_config.json``."""
        return self._system_config_path

    def get_motion_config_path(self) -> Path:
        """Return the path to ``motion_platform_positions.json``."""
        return self.get_api_config_dir() / "motion_platform_positions.json"

    def get_job_files_dir(self) -> Path:
        """Return ``paths.job_files_dir``, resolved relative to :attr:`project_root` when needed."""
        path = Path(self._system.paths.job_files_dir)
        if not path.is_absolute():
            path = self._project_root / path
        return path

    def get_max_weight_per_well(self) -> float:
        """Return ``safety.max_weight_per_well`` in grams."""
        return self._system.safety.max_weight_per_well

    def get_weight_tolerance(self) -> float:
        """Return ``safety.weight_tolerance`` in grams."""
        return self._system.safety.weight_tolerance

    def get_duet_ip(self) -> str:
        """Return ``machine.duet_ip``."""
        return self._system.machine.duet_ip

    def get_default_feedrate(self) -> int:
        """Return ``machine.default_feedrate`` (mm/min)."""
        return self._system.machine.default_feedrate

    def get_tamper_travel_position(self) -> float:
        """Return ``machine.tamper_travel_position``."""
        return self._system.machine.tamper_travel_position

    def get_scale_port(self) -> str:
        """Return ``machine.scale_port`` serial device path."""
        return self._system.machine.scale_port

    def get_num_dispensers(self) -> int:
        """Return ``machine.num_dispensers``."""
        return self._system.machine.num_dispensers

    def get_pistons_per_dispenser(self) -> int:
        """Return ``machine.pistons_per_dispenser``."""
        return self._system.machine.pistons_per_dispenser

    def get_tamp_depth_min(self) -> float:
        """Return ``manipulator.tamp_depth_min``."""
        return self._system.manipulator.tamp_depth_min

    def get_tamp_depth_max(self) -> float:
        """Return ``manipulator.tamp_depth_max``."""
        return self._system.manipulator.tamp_depth_max

    def get_tamp_speed_min(self) -> int:
        """Return ``manipulator.tamp_speed_min``."""
        return self._system.manipulator.tamp_speed_min

    def get_tamp_speed_max(self) -> int:
        """Return ``manipulator.tamp_speed_max``."""
        return self._system.manipulator.tamp_speed_max

    def get_tamp_defaults(self) -> tuple[float, int]:
        """Return default tamp depth and speed from ``manipulator`` config."""
        m = self._system.manipulator
        return m.tamp_depth_default, m.tamp_speed_default

    def get_cors_origins(self) -> list[str]:
        """Return a copy of ``server.cors_origins``."""
        return list(self._system.server.cors_origins)

    def get_mock_hardware(self) -> bool:
        """Return ``server.mock_hardware``."""
        return self._system.server.mock_hardware

    def get_google_drive_enabled(self) -> bool:
        """Return ``google_drive.enabled``."""
        return self._system.google_drive.enabled

    def get_google_drive_credentials_file(self) -> Path:
        """Return ``google_drive.credentials_file``, resolved relative to :attr:`project_root` when needed."""
        path = Path(self._system.google_drive.credentials_file)
        if not path.is_absolute():
            path = self._project_root / path
        return path

    def get_google_drive_folder_id(self) -> str:
        """Return ``google_drive.drive_folder_id``."""
        return self._system.google_drive.drive_folder_id

    def get_retry_interval_seconds(self) -> int:
        """Return ``google_drive.retry_interval_seconds``."""
        return self._system.google_drive.retry_interval_seconds

    def get_trickler_flow_ema_alpha(self) -> float:
        """Return ``trickler.flow_ema_alpha``."""
        return self._system.trickler.flow_ema_alpha

    def get_trickler_yield_ema_alpha(self) -> float:
        """Return ``trickler.yield_ema_alpha``."""
        return self._system.trickler.yield_ema_alpha

    def get_trickler_jam_yield_threshold(self) -> float:
        """Return ``trickler.jam_yield_threshold``."""
        return self._system.trickler.jam_yield_threshold

    def get_trickler_jam_iter_threshold(self) -> int:
        """Return ``trickler.jam_iter_threshold``."""
        return self._system.trickler.jam_iter_threshold

    def get_trickler_jam_auto_recovery_vibration_amplitude(self) -> float:
        """Return ``trickler.jam_auto_recovery_vibration_amplitude``."""
        return self._system.trickler.jam_auto_recovery_vibration_amplitude

    def get_trickler_jam_auto_recovery_wait_seconds(self) -> float:
        """Return ``trickler.jam_auto_recovery_wait_seconds``."""
        return self._system.trickler.jam_auto_recovery_wait_seconds

    def get_trickler_max_step_size_mm(self) -> float:
        """Return ``trickler.max_step_size_mm``."""
        return self._system.trickler.max_step_size_mm

    def get_trickler_min_step_size_mm(self) -> float:
        """Return ``trickler.min_step_size_mm``."""
        return self._system.trickler.min_step_size_mm

    def get_trickler_warmup_steps(self) -> int:
        """Return ``trickler.warmup_steps``."""
        return self._system.trickler.warmup_steps

    def get_trickler_warmup_max_step_mm(self) -> float:
        """Return ``trickler.warmup_max_step_mm``."""
        return self._system.trickler.warmup_max_step_mm

    def get_trickler_coarse_threshold_pct(self) -> float:
        """Return ``trickler.coarse_threshold_pct``."""
        return self._system.trickler.coarse_threshold_pct

    def get_trickler_finish_threshold_pct(self) -> float:
        """Return ``trickler.finish_threshold_pct``."""
        return self._system.trickler.finish_threshold_pct

    def get_trickler_coarse_target_steps(self) -> int:
        """Return ``trickler.coarse_target_steps``."""
        return self._system.trickler.coarse_target_steps

    def get_trickler_coarse_feedrate(self) -> int:
        """Return ``trickler.coarse_feedrate`` (mm/min)."""
        return self._system.trickler.coarse_feedrate

    def get_trickler_fine_feedrate(self) -> int:
        """Return ``trickler.fine_feedrate`` (mm/min)."""
        return self._system.trickler.fine_feedrate

    def get_trickler_coarse_vibration_amplitude(self) -> float:
        """Return ``trickler.coarse_vibration_amplitude``."""
        return self._system.trickler.coarse_vibration_amplitude

    def get_trickler_fine_vibration_amplitude(self) -> float:
        """Return ``trickler.fine_vibration_amplitude``."""
        return self._system.trickler.fine_vibration_amplitude

    def get_trickler_max_dribble_step_mm(self) -> float:
        """Return ``trickler.max_dribble_step_mm``."""
        return self._system.trickler.max_dribble_step_mm


config = ConfigLoader()
