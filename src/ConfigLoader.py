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


DEFAULT_PROFILE_NAME = "Default"


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


class HardnessTestingConfig(BaseModel):
    """Runtime hardness-testing behavior toggles (``hardness_testing``)."""

    enable_monotonic_drop_check: bool


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


class PowderDispenserCoverConfig(BaseModel):
    """Servo configuration for powder dispenser cover actuation."""

    servo: str
    open_angle: int
    closed_angle: int


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
    bypass_cv: bool
    tool: HardnessTesterToolConfig
    lcd_calibration_path: str
    button_servos: ButtonServosConfig
    cam_usb_path: str


class HardnessTestersConfig(BaseModel):
    """Shore-A and Shore-D hardness tester profiles (``hardness_testers``)."""

    shore_a: HardnessTesterConfig
    shore_d: HardnessTesterConfig


class HardnessTesterProfileConfig(BaseModel):
    """Per-tester hardness settings inside a shared named profile."""

    model_config = ConfigDict(extra="forbid")

    use_camera: bool
    bypass_cv: bool
    lcd_calibration_path: str
    button_servos: ButtonServosConfig
    cam_usb_path: str


class HardnessProfileConfig(BaseModel):
    """Shared hardness profile with per-tester hardware sections."""

    num_digits: int
    shore_a: HardnessTesterProfileConfig
    shore_d: HardnessTesterProfileConfig
    monotonic_drop_threshold: float
    threshold_bias: int
    sharpen_strength: float
    sharpen_blur_radius: int
    morph_kernel_size: int
    morph_iterations: int
    morph_open: bool


class TricklerProfilesConfig(BaseModel):
    """Named trickler profile library with active selection."""

    active_profile: str
    profiles: dict[str, TricklerConfig]

    @model_validator(mode="after")
    def validate_profile_library(self) -> "TricklerProfilesConfig":
        if DEFAULT_PROFILE_NAME not in self.profiles:
            raise ValueError(
                f"trickler_profiles must include a '{DEFAULT_PROFILE_NAME}' profile"
            )
        if self.active_profile not in self.profiles:
            raise ValueError(
                f"active_profile '{self.active_profile}' is not defined in trickler profiles"
            )
        return self


class HardnessProfilesConfig(BaseModel):
    """Named hardness profile library with active selection."""

    active_profile: str
    profiles: dict[str, HardnessProfileConfig]

    @model_validator(mode="after")
    def validate_profile_library(self) -> "HardnessProfilesConfig":
        if DEFAULT_PROFILE_NAME not in self.profiles:
            raise ValueError(
                f"hardness_profiles must include a '{DEFAULT_PROFILE_NAME}' profile"
            )
        if self.active_profile not in self.profiles:
            raise ValueError(
                f"active_profile '{self.active_profile}' is not defined in hardness profiles"
            )
        return self


class SystemConfig(BaseModel):
    """Root Pydantic model for ``system_config.json``."""

    paths: PathsConfig
    safety: SafetyConfig
    server: ServerConfig
    machine: MachineConfig
    tools: ToolsConfig
    manipulator: ManipulatorConfig
    hardness_testing: HardnessTestingConfig
    trickler: TricklerConfig
    powder_dispenser_cover: PowderDispenserCoverConfig
    google_drive: GoogleDriveConfig
    hardness_testers: HardnessTestersConfig


def _parse_system_config(raw: dict[str, Any], path: Path) -> SystemConfig:
    """Validate raw system config payload and raise ``ConfigError`` on failure."""
    try:
        return SystemConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"Invalid system_config ({path}): {exc}") from exc


def _parse_trickler_profiles(
    raw: dict[str, Any], path: Path
) -> TricklerProfilesConfig:
    """Validate raw trickler profile payload and raise ``ConfigError`` on failure."""
    try:
        return TricklerProfilesConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"Invalid trickler_profiles ({path}): {exc}") from exc


def _parse_hardness_profiles(
    raw: dict[str, Any], path: Path
) -> HardnessProfilesConfig:
    """Validate raw hardness profile payload and raise ``ConfigError`` on failure."""
    try:
        return HardnessProfilesConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"Invalid hardness_profiles ({path}): {exc}") from exc


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
        self._trickler_profiles_path = (
            self._project_root / "api_config" / "trickler_profiles.json"
        )
        self._hardness_profiles_path = (
            self._project_root / "api_config" / "hardness_profiles.json"
        )
        self._trickler_profiles: TricklerProfilesConfig | None = None
        self._hardness_profiles: HardnessProfilesConfig | None = None
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
        loader._trickler_profiles_path = (
            loader._project_root / "api_config" / "trickler_profiles.json"
        )
        loader._hardness_profiles_path = (
            loader._project_root / "api_config" / "hardness_profiles.json"
        )
        loader._trickler_profiles = None
        loader._hardness_profiles = None
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
        """Load config files and hydrate runtime system sections from profiles."""
        with open(self._system_config_path, "r", encoding="utf-8") as f:
            system_raw = json.load(f)
        self._trickler_profiles = self._load_trickler_profiles()
        self._hardness_profiles = self._load_hardness_profiles()
        hydrated_raw = self._hydrate_system_config(
            system_raw=system_raw,
            trickler_profiles=self._trickler_profiles,
            hardness_profiles=self._hardness_profiles,
        )
        self._system = _parse_system_config(hydrated_raw, self._system_config_path)

    def _load_trickler_profiles(self) -> TricklerProfilesConfig:
        """Load trickler profiles from the dedicated profile JSON file."""
        if not self._trickler_profiles_path.exists():
            raise ConfigError(
                f"Missing trickler_profiles file: {self._trickler_profiles_path}"
            )
        with open(self._trickler_profiles_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return _parse_trickler_profiles(raw, self._trickler_profiles_path)

    def _load_hardness_profiles(self) -> HardnessProfilesConfig:
        """Load hardness profiles from the dedicated profile JSON file."""
        if not self._hardness_profiles_path.exists():
            raise ConfigError(
                f"Missing hardness_profiles file: {self._hardness_profiles_path}"
            )
        with open(self._hardness_profiles_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return _parse_hardness_profiles(raw, self._hardness_profiles_path)

    def _hydrate_system_config(
        self,
        system_raw: dict[str, Any],
        trickler_profiles: TricklerProfilesConfig,
        hardness_profiles: HardnessProfilesConfig,
    ) -> dict[str, Any]:
        """Inject active profile values into ``system_raw`` before validation."""
        active_trickler = trickler_profiles.profiles[trickler_profiles.active_profile]
        active_hardness = hardness_profiles.profiles[hardness_profiles.active_profile]
        tools = system_raw.get("tools", {})

        shore_a_tool = tools.get("shore_a_hardness_tester")
        if shore_a_tool is None:
            raise ConfigError(
                "tools.shore_a_hardness_tester is required in system_config.json"
            )
        shore_d_tool = tools.get("shore_d_hardness_tester")
        if shore_d_tool is None:
            raise ConfigError(
                "tools.shore_d_hardness_tester is required in system_config.json"
            )

        hydrated = dict(system_raw)
        hydrated["trickler"] = active_trickler.model_dump()
        hydrated["hardness_testers"] = {
            "shore_a": {
                "use_camera": active_hardness.shore_a.use_camera,
                "bypass_cv": active_hardness.shore_a.bypass_cv,
                "tool": shore_a_tool,
                "lcd_calibration_path": active_hardness.shore_a.lcd_calibration_path,
                "button_servos": active_hardness.shore_a.button_servos.model_dump(),
                "cam_usb_path": active_hardness.shore_a.cam_usb_path,
            },
            "shore_d": {
                "use_camera": active_hardness.shore_d.use_camera,
                "bypass_cv": active_hardness.shore_d.bypass_cv,
                "tool": shore_d_tool,
                "lcd_calibration_path": active_hardness.shore_d.lcd_calibration_path,
                "button_servos": active_hardness.shore_d.button_servos.model_dump(),
                "cam_usb_path": active_hardness.shore_d.cam_usb_path,
            },
        }
        return hydrated

    def _write_json_file(self, path: Path, payload: dict[str, Any]) -> None:
        """Write JSON payload with stable formatting, creating parent directories."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.write("\n")

    def get_api_config_dir(self) -> Path:
        """Return the ``api_config`` directory under :attr:`project_root`."""
        return self._project_root / "api_config"

    def get_system_config_path(self) -> Path:
        """Return the resolved path to the loaded ``system_config.json``."""
        return self._system_config_path

    def get_trickler_profiles_path(self) -> Path:
        """Return the resolved path to ``trickler_profiles.json``."""
        return self._trickler_profiles_path

    def get_hardness_profiles_path(self) -> Path:
        """Return the resolved path to ``hardness_profiles.json``."""
        return self._hardness_profiles_path

    def get_motion_config_path(self) -> Path:
        """Return the path to ``motion_platform_positions.json``."""
        return self.get_api_config_dir() / "motion_platform_positions.json"

    @property
    def trickler_profiles(self) -> TricklerProfilesConfig:
        """Validated trickler profile library."""
        if self._trickler_profiles is None:
            raise ConfigError("trickler profiles were not loaded")
        return self._trickler_profiles

    @property
    def hardness_profiles(self) -> HardnessProfilesConfig:
        """Validated hardness profile library."""
        if self._hardness_profiles is None:
            raise ConfigError("hardness profiles were not loaded")
        return self._hardness_profiles

    def get_active_trickler_profile(self) -> TricklerConfig:
        """Return the currently selected trickler profile."""
        active_name = self._trickler_profiles.active_profile
        return self._trickler_profiles.profiles[active_name]

    def get_active_hardness_profile(self) -> HardnessProfileConfig:
        """Return the currently selected hardness profile."""
        active_name = self._hardness_profiles.active_profile
        return self._hardness_profiles.profiles[active_name]

    def set_trickler_profiles(self, payload: dict[str, Any]) -> TricklerProfilesConfig:
        """Validate and persist full trickler profile library payload."""
        validated = _parse_trickler_profiles(payload, self._trickler_profiles_path)
        self._write_json_file(self._trickler_profiles_path, validated.model_dump())
        self._trickler_profiles = validated
        self._load_config()
        return validated

    def set_hardness_profiles(self, payload: dict[str, Any]) -> HardnessProfilesConfig:
        """Validate and persist full hardness profile library payload."""
        validated = _parse_hardness_profiles(payload, self._hardness_profiles_path)
        self._write_json_file(self._hardness_profiles_path, validated.model_dump())
        self._hardness_profiles = validated
        self._load_config()
        return validated

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

    def get_hardness_monotonic_drop_check_enabled(self) -> bool:
        """Return ``hardness_testing.enable_monotonic_drop_check``."""
        return self._system.hardness_testing.enable_monotonic_drop_check

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

    def get_powder_dispenser_cover_servo(self) -> str:
        """Return ``powder_dispenser_cover.servo``."""
        return self._system.powder_dispenser_cover.servo

    def get_powder_dispenser_cover_open_angle(self) -> int:
        """Return ``powder_dispenser_cover.open_angle``."""
        return self._system.powder_dispenser_cover.open_angle

    def get_powder_dispenser_cover_closed_angle(self) -> int:
        """Return ``powder_dispenser_cover.closed_angle``."""
        return self._system.powder_dispenser_cover.closed_angle


config = ConfigLoader()
