"""Pydantic models for ``api_config/motion_platform_positions.json``.

Validated JSON is converted into runtime descriptors by
:class:`~src.MotionPlatformStateMachine.PositionRegistry`. Tool names referenced
in position requirements come from :mod:`src.ConfigLoader`, not a second copy of
``system_config.json``.

Note:
    The state machine reads this file once at ``connect()``. Restart or
    reconnect after editing the JSON on disk.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from src.ConfigLoader import ConfigError

_REQUIRED_Z_HEIGHT_IDS = frozenset({"mold_transfer_safe", "hardness_tester_safe"})
_SAFETY_CRITICAL_ACTIONS = frozenset({"retrieve_piston", "tamp_mold"})


class ZHeightEntry(BaseModel):
    """Named Z level from the ``z_heights`` map."""

    description: str = ""
    z_coordinate: float


class ZHeightPolicyConfig(BaseModel):
    """Allowed and required z-height ids for a position."""

    allowed: list[str] = Field(default_factory=list)
    required: str | None = None


class CoordinatesConfig(BaseModel):
    """Axis coordinates for a position entry."""

    x: float | None = None
    y: float | None = None
    z: float | str | None = None
    v: float | None = None


class EngagementConfig(BaseModel):
    """Tool engagement requirements and permitted actions at a position."""

    requirements: dict[str, Any] = Field(default_factory=dict)
    allowed_actions: list[str] = Field(default_factory=list)


class MotionPositionConfig(BaseModel):
    """Single entry from the ``positions`` array.

    Attributes:
        id: Lowercase position identifier (for example ``scale_ready``).
        type: UPPER_CASE type name used for transition expansion.
        allowed_origins: Positions or types permitted as move sources.
        allowed_destinations: Positions or types permitted as move targets.
        requirements: Context fields that must match before arrival.
        z_height_policy: Allowed and required z-height ids at this position.
        coordinates: Optional axis coordinates; ``z`` may be
            ``USE_Z_HEIGHT_POLICY``.
        engagement: Optional tool-engagement requirements and allowed actions.
    """

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
        """Require z-height policy when ``coordinates.z`` is ``USE_Z_HEIGHT_POLICY``."""
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
    """Single entry from the ``actions`` array.

    Attributes:
        id: Action identifier referenced from validated FSM methods.
        position_scope: Position ids or types where the action may run.
        requirements: Context fields that must match before execution.
        excludes: Inverse of ``requirements``; matching values block the action.
        required_tool_id: Tool name that must be active, if any.
        requires_tool_engaged: Whether the tool must be in the engaged state.
        blocked_when_engaged: Whether engagement blocks this action.
    """

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
        """Enforce scope and requirements on safety-critical actions."""
        if self.id not in _SAFETY_CRITICAL_ACTIONS:
            return self
        if not self.position_scope:
            raise ValueError(f"action {self.id!r}: position_scope is required")
        if not self.requirements:
            raise ValueError(f"action {self.id!r}: requirements must be non-empty")
        return self


class MotionPlatformConfig(BaseModel):
    """Root model for ``motion_platform_positions.json``."""

    z_heights: dict[str, ZHeightEntry]
    positions: list[MotionPositionConfig] = Field(min_length=1)
    actions: list[MotionActionConfig]
    coordinate_tolerance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def required_z_height_ids(self) -> "MotionPlatformConfig":
        """Ensure required z-height ids are present."""
        missing = _REQUIRED_Z_HEIGHT_IDS - set(self.z_heights.keys())
        if missing:
            raise ValueError(
                f"z_heights missing required ids: {', '.join(sorted(missing))}"
            )
        if not self.z_heights:
            raise ValueError("z_heights must be non-empty")
        return self


def load_motion_platform_config(payload: dict[str, Any]) -> MotionPlatformConfig:
    """Parse and validate a motion platform JSON payload.

    Args:
        payload: Decoded contents of ``motion_platform_positions.json``.

    Returns:
        Validated :class:`MotionPlatformConfig`.

    Raises:
        ConfigError: If validation fails.
    """
    try:
        return MotionPlatformConfig.model_validate(payload)
    except Exception as exc:
        raise ConfigError(f"Invalid motion_platform_positions.json: {exc}") from exc


def supported_tool_ids_from_system_config() -> frozenset[str]:
    """Collect registered tool names from the :mod:`src.ConfigLoader` singleton.

    Includes manipulator and hardness tester tool names from
    ``system_config.json``.

    Returns:
        Frozen set of tool name strings.
    """
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
