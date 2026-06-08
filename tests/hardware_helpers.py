class TestError(Exception):
    """Exception raised when a manual hardware test encounters an error."""


def print_step(step_num: int, description: str) -> None:
    """Print a formatted step header."""
    print(f"\n{'=' * 60}")
    print(f"STEP {step_num}: {description}")
    print(f"{'=' * 60}")


def print_success(message: str) -> None:
    """Print a success message."""
    print(f"✓ {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    print(f"✗ ERROR: {message}")


def move_to_global_ready(state_machine) -> tuple[bool, str | None]:
    """Move to global_ready with z-height policy resolution."""
    global_ready = state_machine._registry.get("global_ready")
    if not global_ready or not global_ready.coordinates:
        raise TestError("global_ready position not found or has no coordinates")

    coords = global_ready.coordinates
    ready_z = None
    if coords.z == "USE_Z_HEIGHT_POLICY":
        if not state_machine.context.z_height_id:
            state_machine.context.z_height_id = "mold_transfer_safe"
        z_heights = state_machine._registry.z_heights
        if state_machine.context.z_height_id in z_heights:
            z_config = z_heights[state_machine.context.z_height_id]
            if isinstance(z_config, dict):
                ready_z = z_config.get("z_coordinate")
    elif coords.z is not None:
        ready_z = coords.z

    result = state_machine._validate_and_execute_move(
        target_position_id="global_ready",
        execution_func=state_machine._executor.execute_move_to_position,
        x=coords.x,
        y=coords.y,
        z=ready_z,
        v=coords.v,
    )
    return result.valid, result.reason if not result.valid else None
