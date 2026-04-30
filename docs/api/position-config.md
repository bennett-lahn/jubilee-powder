# Position Configuration Reference

`jubilee_api_config/motion_platform_positions.json` is the single file that defines every named location the Jubilee can move to, every action it can perform, and the safety constraints that govern both. The state machine loads this file once at connection time and enforces movement between these positions. This means no code changes are needed for routine calibration or layout adjustments, instead `motion_platform_positions.json` should be modified instead.

!!! note "Restart required after edits"
    The configuration is read once during `connect()`. Restart the Python process (or reconnect) after making any changes.

---

## When to edit this file

| Task | What to change |
|------|---------------|
| Machine was moved or a position drifted | Update `coordinates` on the affected position(s) |
| Physical layout changed (e.g., scale repositioned) | Update `coordinates`, verify `allowed_origins` / `allowed_destinations` still reflect the real risk of collisions between positions |
| Adding a new mold slot | Add a new `MOLD_READY` position entry following the existing pattern, update `position_scope` list for `pick_up_mold`, `put_down_mold` |
| Adding a new dispenser | Add a new `DISPENSER_READY` position entry and update action `position_scope` lists |
| Changing required machine state before a move | Update `requirements` on the target position |

---

## Updating position coordinates

This is the most common edit. After physically calibrating a position on the machine, update its `x`, `y`, `z`, and `v` values:

```json
{
  "id": "scale_ready",
  "type": "SCALE_READY",
  ...
  "coordinates": {
    "x": 150.0,
    "y": 143.0,
    "z": 27.0,
    "v": 67.0
  }
}
```

A `z` value of `"USE_Z_HEIGHT_POLICY"` means the Z coordinate is taken from the active z-height at runtime rather than being hardcoded. Leave this string as-is unless you specifically want to fix the Z at a literal value.

---

## File structure

The file has four top-level keys:

```json
{
  "z_heights":            { ... },
  "coordinate_tolerance": { ... },
  "positions":            [ ... ],
  "actions":              [ ... ]
}
```

**`z_heights`** - named Z levels (e.g., `"mold_transfer_safe"`). Positions whose `z` is `"USE_Z_HEIGHT_POLICY"` resolve their Z to one of these positions from the context's active z-height at runtime.

**`coordinate_tolerance`** - maximum allowed deviation (mm) between the machine's reported position and a position's stored coordinates before the state machine considers the machine "out of position".

**`positions`** - the main array. Every named location is an entry here.

**`actions`** - tool operations (pick mold, retrieve piston, etc.). These are validated and executed without changing the current position.

---

## Positions

### Naming and type conventions

Every position has an `id` (lowercase) and a `type` (UPPER_CASE). The type determines which group a position belongs to when `allowed_origins` / `allowed_destinations` reference it by type name.

| `type` | `id` pattern | Example |
|--------|-------------|---------|
| `GLOBAL_READY` | `global_ready` | `"global_ready"` |
| `SCALE_READY` | `scale_ready`, `scale_active` | `"scale_ready"` |
| `DISPENSER_READY` | `dispenser_ready_N` | `"dispenser_ready_0"` |
| `MOLD_READY` | `mold_ready_N` | `"mold_ready_3"` |

When referencing positions in `allowed_origins` or `allowed_destinations`, you can use either a specific ID (`"dispenser_ready_0"`) or a type name (`"DISPENSER_READY"`). A type name expands to all positions of that type at load time. E.g. `"DISPENSER_READY"` evaluates to `"dispenser_ready_N"` for all `N` dispenser ready positions.

### Position fields

```json
{
  "id": "dispenser_ready_0",
  "type": "DISPENSER_READY",
  "description": "...",
  "coordinates": { "x": 298.0, "y": 140.0, "z": 95.0, "v": 34.0 },
  "allows_tool_engagement": true,
  "allowed_origins": [ "DISPENSER_READY", "GLOBAL_READY" ],
  "allowed_destinations": [ "DISPENSER_READY", "GLOBAL_READY" ],
  "requirements": {
    "active_tool_id": "manipulator",
    "payload_state": "mold_without_top_piston"
  },
  "z_height_policy": {
    "allowed": [ "mold_transfer_safe" ],
    "required": "mold_transfer_safe"
  },
  "engagement": {
    "requirements": { ... }
  }
}
```

---

### `allowed_origins` and `allowed_destinations`

These two fields together define the transitions of the state machine. Before any move is executed, the state machine checks **both**:

- The current position's `allowed_destinations` contains the target position.
- The target position's `allowed_origins` contains the current position.

Both must pass. If either fails, the move is rejected with a message describing the violation.

**Current transition rules:**

| From | To |
|------|----|
| `GLOBAL_READY` | `GLOBAL_READY`, `SCALE_READY`, `DISPENSER_READY`, `MOLD_READY` |
| `SCALE_READY` | `SCALE_READY`, `GLOBAL_READY` |
| `DISPENSER_READY` | `DISPENSER_READY`, `GLOBAL_READY` |
| `MOLD_READY` | `MOLD_READY`, `GLOBAL_READY` |

Notably: moving between a mold slot and a dispenser requires passing through `global_ready`.

---

### `requirements`

`requirements` is a dict of `MotionContext` field names mapped to the value they must have before the move is permitted. This is checked before each move or action executes.

The context fields you can use as requirement keys:

| Key | Type | Meaning |
|-----|------|---------|
| `active_tool_id` | string or `null` | Which tool is currently picked up (`"manipulator"` or `null`) |
| `payload_state` | string | What the manipulator is carrying: `"empty"`, `"mold_without_top_piston"`, `"mold_with_top_piston"` |
| `mold_on_scale` | bool | Whether a mold is currently resting on the scale |
| `z_height_id` | string | The active named Z-height (e.g., `"mold_transfer_safe"`) |

A requirement value can be a scalar (must match exactly) or a list (actual value must be one of the listed options).

!!! warning "requirements on the target position are a pre-condition, not a post-condition"
    `requirements` is checked **before** the machine moves. It describes what must already be true in context for the move to be safe. It does not describe what will be true after the move — that is managed by the validated methods in `MotionPlatformStateMachine`, which update context fields like `payload_state` and `mold_on_scale` after a successful operation.

**Example:** `dispenser_ready_0` requires `payload_state: mold_without_top_piston`. This prevents the machine from moving to a dispenser if the manipulator is empty or the mold already has its piston.

---

### `z_height_policy`

Controls which Z-heights are valid when arriving at this position.

```json
"z_height_policy": {
  "allowed": [ "mold_transfer_safe" ],
  "required": "mold_transfer_safe"
}
```

- **`allowed`** - a list of z-height names that are acceptable.
- **`required`** - if set, the context must be at exactly this z-height. More restrictive than `allowed`.

If both are omitted or empty, no z-height is permitted for that position, so any moves/actions will always be rejected.

---

### `allows_tool_engagement` and `engagement`

`"allows_tool_engagement": true` marks positions where the tool can be lowered into an engaged state (currently only the scale positions). Attempting to engage the tool at a position where this is `false` will be rejected.

The `engagement` block holds a nested `requirements` dict that is checked specifically during tool engagement and disengagement. If omitted, the position's top-level `requirements` are used as a fallback.

```json
"engagement": {
  "requirements": {
    "active_tool_id": "manipulator",
    "payload_state": "mold_without_top_piston"
  }
}
```

---

## Actions

Actions are tool operations that are validated and executed without changing `context.position_id`. They are defined in the `actions` array and referenced by ID from code.

### Action fields

```json
{
  "id": "retrieve_piston",
  "description": "...",
  "required_tool_id": "manipulator",
  "requires_tool_engaged": false,
  "blocked_when_engaged": true,
  "position_scope": [ "dispenser_ready_0", "dispenser_ready_1" ],
  "requirements": {
    "active_tool_id": "manipulator",
    "payload_state": "mold_without_top_piston"
  },
  "excludes": {}
}
```

| Field | Meaning |
|-------|---------|
| `required_tool_id` | The tool that must be active (`"manipulator"` or omitted for any/none) |
| `requires_tool_engaged` | If `true`, the FSM must be in the `Tool Engaged` state |
| `blocked_when_engaged` | If `true`, the action is rejected while the tool is engaged |
| `position_scope` | List of position IDs (or type names) where this action is permitted. Empty list means any position |
| `requirements` | Same semantics as position requirements — context must match before the action runs |
| `excludes` | Inverse of requirements — context must **not** match. E.g., `"payload_state": "empty"` blocks the action when carrying nothing |

---

## Maintaining state machine invariants

When editing this file, keep the following invariants intact so the state machine remains consistent:

**1. Every reachable position must have consistent two-way transitions.**
If position A lists B in `allowed_destinations`, then B must list A in `allowed_origins`. Asymmetric entries cause confusing one-way failures at runtime.

**2. `requirements` must reflect what is physically true at that location.**
A position's requirements describe the context that must hold before the machine can safely be there. If you loosen requirements (e.g., removing `payload_state`), the state machine will permit moves it previously blocked. Make sure this is intentional and safe.

**3. Dispenser positions require `mold_without_top_piston`.**
This ensures the machine will never attempt to retrieve a second piston for a mold that already has one.

**4. `scale_active` is only entered via `place_mold_on_scale`, not via a normal move.**
The state machine sets `context.position_id = "scale_active"` and `context.mold_on_scale = True` together after the place action succeeds. Never add `scale_active` to the `allowed_destinations` of any position — doing so would allow the machine to navigate to it with an incorrect procedure, probably causing a collision.

**5. Action `position_scope` lists must stay in sync with `DISPENSER_READY` and `MOLD_READY` entries.**
When adding a new dispenser or mold slot, update the `position_scope` list on every action that should be permitted at that position (e.g., `retrieve_piston`, `pick_up_mold`, `put_down_mold`, `tamp_mold`).

---

## Adding a new mold slot

1. Copy an existing `MOLD_READY` entry and change `"id"` to `"mold_ready_N"` with the next available index.
2. Update `coordinates` to the calibrated position.
3. Add `"mold_ready_N"` to the `position_scope` list of every action that should be permitted there (`pick_up_mold`, `put_down_mold`, `tamp_mold`).
4. No changes to `allowed_origins` or `allowed_destinations` are needed — all mold slots use the same type reference `MOLD_READY`.

## Adding a new dispenser

1. Copy an existing `DISPENSER_READY` entry and change `"id"` to `"dispenser_ready_N"`.
2. Update `coordinates`.
3. Add `"dispenser_ready_N"` to the `position_scope` of the `retrieve_piston` action.
4. As with mold slots, `allowed_origins` / `allowed_destinations` use the `DISPENSER_READY` type reference and require no changes.
