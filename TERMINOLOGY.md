# Terminology Guide

This document defines the  terminology used throughout the codebase. All code, comments, documentation, and user-facing text should use these terms consistently.

## Core Components

### Trickler
**Definition:** The mechanism used to dispense powder into molds.

**Usage Notes:**
- The trickler is the primary mechanism for adding powder to molds
- Operations involving the trickler should use "fill" or "add powder" rather than "dispense" when referring to adding powder to molds
- The term "dispense" should be reserved exclusively referringn to the piston dispenser mechanism

### Piston Dispenser
**Definition:** Mechanism that holds top pistons before they are placed into molds.

**Usage Notes:**
- Each piston dispenser has an index (e.g., dispenser_0, dispenser_1)
- Tracks the number of available pistons
- Operations: "retrieve piston" (getting a piston from the dispenser)

### Top Piston
**Definition:** The piston component that gets placed into a mold after powder has been added.

**Usage Notes:**
- **Outdated term:** "cap" - this term should be replaced with "top piston" throughout the codebase
- A mold can have a state: `has_top_piston` (True/False)
- Payload states: `mold_without_top_piston` (replaces "mold_without_cap") and `mold_with_top_piston` (replaces "mold_with_cap")

### Mold
**Definition:** Vessel that holds powder. The top piston gets placed into the mold after powder filling.

**Usage Notes:**
- **Outdated term:** "WeightWell" - the class name and references should be updated to "Mold" where appropriate
- Each mold is associated with a specific slot (e.g., mold_ready_0, mold_ready_1)
- Molds track weight, validity, and top piston status

### Manipulator
**Definition:** Tool used to pick up and move molds. Also performs tamping operations.

**Usage Notes:**
- The manipulator is a toolhead that can be engaged/disengaged
- Operations: pick up mold, place mold, tamp mold, retrieve piston, place top piston

### Scale
**Definition:** Used to weigh mold/amount of powder filled.

**Usage Notes:**
- The scale is used during the powder filling process to measure weight
- Molds are placed on the scale for weighing operations
- Scale positions: `scale_ready`, `scale_active`

## Operations and Actions

### Filling
**Definition:** The process of adding powder to a mold using the trickler.

**Usage Notes:**
- **Preferred verbs:** "fill", "add powder", "fill mold with powder"
- **Avoid:** "dispense" when referring to adding powder to molds
- The trickler mechanism performs the filling operation
- This occurs while the mold is on the scale

### Retrieve Piston
**Definition:** The process of retrieving a top piston from the piston dispenser.

**Usage Notes:**
- **Reserved term:** "dispense" should only be used in relation to the piston dispenser
- Acceptable: "retrieve piston", avoid "dispense piston from dispenser"
- This operation places the piston into the mold being carried by the manipulator

### Tamping
**Definition:** The process of compacting powder within a mold using the manipulator's tamper mechanism.

**Usage Notes:**
- Only allowed when carrying a mold without a top piston
- Only allowed when the mold is on the scale
- Uses the tamper axis (typically 'V' axis)

### Picking Up / Placing Molds
**Definition:** Operations to move molds between locations.

**Usage Notes:**
- **Pick up:** Getting a mold from a location (mold slot, scale, etc.)
- **Place:** Putting a mold at a location (mold slot, scale, etc.)
- The manipulator tool must be engaged for these operations

### Retrieving / Placing Top Pistons
**Definition:** Operations involving top pistons.

**Usage Notes:**
- **Retrieve piston:** Getting a top piston from the piston dispenser and inserting it into the mold
- **Place top piston:** Alternative term for the same operation
- Only allowed when carrying a mold without a top piston
- Only allowed when not on the scale

<!-- ## States and Properties

### Mold States
- **Empty:** No mold is being carried by the manipulator
- **Mold without top piston:** Mold is being carried but has no top piston (payload_state: `mold_without_top_piston`)
- **Mold with top piston:** Mold is being carried and has a top piston (payload_state: `mold_with_top_piston`)
- **Mold on scale:** Boolean flag indicating if the current mold is positioned on the scale

### Mold Properties
- **valid:** Whether the mold should be used (contains a mold)
- **has_top_piston:** Whether the mold has a top piston inserted
- **current_weight:** Current weight of powder in the mold (grams)
- **target_weight:** Target weight of powder for the mold (grams)
- **max_weight:** Maximum weight capacity of the mold (grams) -->

## Position Types

### GLOBAL_READY
Initial/home position for the motion platform when no specific operation is being performed.

### MOLD_READY
Ready position for a specific mold slot (e.g., mold_ready_0, mold_ready_1, etc.).

### DISPENSER_READY
Ready position for a specific piston dispenser (e.g., dispenser_ready_0, dispenser_ready_1).

### SCALE_READY
Ready position for the scale. Includes `scale_active` for active weighing operations.

<!-- ## Outdated Terminology to Replace

### "Cap" → "Top Piston"
- All references to "cap" or "caps" should be replaced with "top piston" or "top pistons"
- Payload states: `mold_without_cap` → `mold_without_top_piston`, `mold_with_cap` → `mold_with_top_piston`

### "WeightWell" → "Mold"
- The class name `WeightWell` should be renamed to `Mold`
- References to "well" in the context of molds should be updated to "mold"
- Well IDs (e.g., "A1", "0") can remain as identifiers, but the object itself is a "mold"

### "Dispense" (for powder filling) → "Fill" or "Add Powder"
- When referring to adding powder to molds, use "fill" or "add powder"
- Reserve "dispense" exclusively for piston dispenser operations -->

## Additional Notes

### Z-Height Policies
- **dispenser_safe:** Safe Z height for operations near the piston dispenser
- **mold_transfer_safe:** Safe Z height for transferring molds between locations

### Action IDs
Standard action identifiers used in the state machine:
- `fill_mold`: Fill mold with powder using trickler
- `pick_up_mold`: Pick up a mold from a mold slot
- `put_down_mold`: Place a mold into a mold slot
- `retrieve_piston`: Retrieve a top piston from dispenser and insert into mold
- `tamp_mold`: Tamp the contents of a mold
- `pickup_tool`: Pick up the manipulator tool
- `home_all`: Home all axes
- `home_manipulator`: Home the manipulator/tamper axis
- `home_trickler`: Home the trickler axis

