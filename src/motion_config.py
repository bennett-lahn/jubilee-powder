"""
Pydantic models for jubilee_api_config/motion_platform_positions.json.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from src.ConfigLoader import ConfigError

_REQUIRED_Z_HEIGHT_IDS = frozenset({"mold_transfer_safe", "hardness_tester_safe"})
_SAFETY_CRITICAL_ACTIONS = frozenset({"retrieve_piston", "tamp_mold"})


class ZHeightEntry(BaseModel):
    description: str = ""
    z_coordinate: float


class ZHeightPolicyConfig(BaseModel):
    allowed: list[str] = Field(default_factory=list)
    required: str | None = None


class CoordinatesConfig(BaseModel):
    x: float | None = None
    y: float | None = None
    z: float | str | None = None
    v: float | None = None


class EngagementConfig(BaseModel):
    requirements: dict[str, Any] = Field(default_factory=dict)
    allowed_actions: list[str] = Field(default_factory=list)


class MotionPositionConfig(BaseModel):
    id: str
    type: str
    allowed_origins: list[str]
    allowed_destinations: list[str]
    requirements: dict[str, Any]
    z_height_policy: ZHeightPolicyConfig
    description: str = ""
    allows_tool_engagement: bool = False
    coordinates: CoordinatesConfig | None = None
    engagement: EngagementConfig | None = None
    resource_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def z_policy_when_use_z_height_policy(self) -> "MotionPositionConfig":
        if (
            self.coordinates is not None
            and self.coordinates.z == "USE_Z_HEIGHT_POLICY"
            and not self.z_height_policy.required
            and not self.z_height_policy.allowed
        ):
            raise ValueError(
                f"position {self.id!r}: z_height_policy must define allowed or required "
                "when coordinates.z is USE_Z_HEIGHT_POLICY"
            )
        return self


class MotionActionConfig(BaseModel):
    id: str
    position_scope: list[str] = Field(default_factory=list)
    requirements: dict[str, Any]
    description: str = ""
    excludes: dict[str, Any] = Field(default_factory=dict)
    required_tool_id: str | None = None
    requires_tool_engaged: bool = False
    blocked_when_engaged: bool = False

    @model_validator(mode="after")
    def safety_critical_action_fields(self) -> "MotionActionConfig":
        if self.id not in _SAFETY_CRITICAL_ACTIONS:
            return self
        if not self.position_scope:
            raise ValueError(f"action {self.id!r}: position_scope is required")
        if not self.requirements:
            raise ValueError(f"action {self.id!r}: requirements must be non-empty")
        return self


class MotionPlatformConfig(BaseModel):
    z_heights: dict[str, ZHeightEntry]
    positions: list[MotionPositionConfig] = Field(min_length=1)
    actions: list[MotionActionConfig]
    coordinate_tolerance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def required_z_height_ids(self) -> "MotionPlatformConfig":
        missing = _REQUIRED_Z_HEIGHT_IDS - set(self.z_heights.keys())
        if missing:
            raise ValueError(
                f"z_heights missing required ids: {', '.join(sorted(missing))}"
            )
        if not self.z_heights:
            raise ValueError("z_heights must be non-empty")
        return self


def load_motion_platform_config(payload: dict[str, Any]) -> MotionPlatformConfig:
    """Parse and validate motion platform JSON payload."""
    try:
        return MotionPlatformConfig.model_validate(payload)
    except Exception as exc:
        raise ConfigError(f"Invalid motion_platform_positions.json: {exc}") from exc


def supported_tool_ids_from_system_config() -> frozenset[str]:
    """Collect tool names from the validated ConfigLoader singleton."""
    from src.ConfigLoader import config as cfg

    tool_ids: set[str] = set()
    for tool in cfg.system.tools.model_dump().values():
        if isinstance(tool, dict):
            name = tool.get("name")
            if isinstance(name, str):
                tool_ids.add(name)
    for tester in (
        cfg.system.hardness_testers.shore_a,
        cfg.system.hardness_testers.shore_d,
    ):
        tool_ids.add(tester.tool.name)
    return frozenset(tool_ids)
