# Using the GUI

This guide walks through using the Jubilee GUI for powder dispensing operations.

## Overview

The Jubilee GUI provides a touchscreen-friendly interface for:

- Configuring hardware
- Selecting wells to fill
- Setting target weights
- Running dispensing jobs
- Monitoring progress in real-time

## Starting the GUI

### Prerequisites

Ensure all dependencies are installed:

```bash
pip install -r gui/requirements.txt
```

### Launch

From the project root:

```bash
python gui/jubilee_gui.py
```

The GUI will open and automatically attempt to connect to the hardware.

## Initial Setup

### Configure Hardware

If this is your first time or you've changed your hardware setup:

1. Click the **"Hardware Config"** button (top right)
2. Enter your configuration:
   - **Number of Dispensers**: How many piston dispensers you have (e.g., 2)
   - **Pistons per Dispenser**: How many pistons each dispenser holds (e.g., 10)
3. Note the **Total Pistons** displayed
4. Click **"Apply"**

!!! note
    Hardware configuration can only be changed when **disconnected**. If you need to change it after connecting, restart the application.

### Verify Connection

After launching, check the status:

- **Status Bar** (bottom): Should show "Connected"
- **Scale Panel** (left): Should show "Connected" and live weight
- **Connection** takes 30-60 seconds due to homing

If connection fails:

- Verify Jubilee IP in `jubilee_api_config/system_config.json`
- Check scale serial port connection
- Ensure hardware is powered on

## Running a Dispensing Job

### Step 1: Select Wells

Click wells in the 3x3 grid to select them:

- **Green wells**: Selected for dispensing
- **Gray wells**: Not selected
- Click again to deselect

You can select as many wells as you have pistons available.

### Step 2: Set Target Weights

1. Click **"Set Weights"** button
2. A dialog appears listing selected wells
3. Enter target weight in grams for each well
4. Click **"Apply"**

!!! tip
    If you need to select different wells, you can return to Step 1 and change your selection.

### Step 3: Start Job

1. Click **"Start Job"** button
2. A safety checklist dialog appears
3. Verify each item:
   - Scale is connected and stable
   - Trickler tool is loaded and calibrated
   - Powder container is filled
   - All target wells are clean and ready
   - Emergency stop is accessible
   - Work area is clear of obstructions
4. Check all items
5. Click **"Start Job"**

### Step 4: Monitor Progress

A progress dialog displays:

- **Current well** being processed
- **Progress bar** with percentage
- **Completed/total wells** count
- **Stop button** if you need to cancel

The status bar shows detailed operation status:

- "Processing well A1 (1/5)"
- "Moving to scale"
- "Filling to target weight"
- etc.

### Step 5: Completion

When all wells are complete:

- Progress dialog closes
- Completion dialog appears
- Status shows "Job completed successfully"
- Click **"OK"**

## Advanced Features

### Stopping a Job

If you need to stop a running job:

1. Click **"Stop Job"** button (main screen or progress dialog)
2. Job will stop **after current well completes**
3. Partially filled wells remain filled
4. Can restart job with remaining wells

!!! warning
    Job cannot stop immediately - it completes the current well first for safety.

### Monitoring Weight

The scale panel (left side) shows:

- **Connection status**: Connected/Disconnected
- **Current weight**: Updates every 500ms
- Weight shown even when not running a job

### Reloading Dispensers

If you manually reload a dispenser with more pistons:

!!! note
    Currently, dispenser reload requires updating code or restarting. Future versions may add a UI button for this.

## Understanding the Interface

### Main Screen Layout

```
┌────────────────────────────────────────────────────┐
│           Jubilee Powder Dispensing System          │
├──────────────┬─────────────────────┬────────────────┤
│   Scale      │   Jubilee Platform  │    Controls    │
│              │                     │                │
│ Connected    │    [A1] [A2] [A3]   │ Hardware Config│
│ 0.000g       │    [B1] [B2] [B3]   │ Set Weights    │
│              │    [C1] [C2] [C3]   │ Start Job      │
│              │                     │ Stop Job       │
└──────────────┴─────────────────────┴────────────────┘
│ Status: Ready                                        │
└──────────────────────────────────────────────────────┘
```

### Color Coding

- **Green**: Selected wells, connected status, success
- **Orange**: Scale panel, active elements
- **Red**: Errors, stop button, disconnected
- **Gray**: Inactive or unselected items
- **Blue**: Primary buttons and actions

### Button States

Buttons are enabled/disabled based on context:

- **Hardware Config**: Only when disconnected
- **Set Weights**: Only when wells selected
- **Start Job**: Only when wells selected and weights set
- **Stop Job**: Only when job is running

## Troubleshooting

### "Please select at least one well first"

You tried to set weights without selecting wells:

1. Click wells in the grid to select them (turn green)
2. Then click "Set Weights"

### "Not enough pistons"

Your job needs more pistons than available:

- Check Hardware Config for total pistons
- Either:
  - Select fewer wells
  - Reload dispensers with more pistons
  - Reconfigure in Hardware Config

### "Cannot change hardware config while connected"

You tried to change config after connection:

- Hardware config can only be changed when disconnected
- Restart the application to reconfigure

### Job Fails on Specific Well

If job fails at a specific well:

1. Check error message in dialog
2. Verify well ID exists in deck configuration
3. Ensure mold is accessible
4. Check for obstructions

Common causes:

- Mold not in slot
- Target weight too high
- Scale not responding
- Out of pistons

### Progress Dialog Not Updating

Progress updates happen between wells:

- Filling a well can take several minutes
- Status bar shows sub-steps
- Progress dialog updates when well completes

### Scale Shows 0.000g

Check scale connection:

- Verify scale serial port in configuration
- Check USB cable connection
- Restart application
- Check scale power

## Best Practices

### Before Each Job

1. Verify powder hopper is filled
2. Check molds are clean and in slots
3. Ensure dispensers have enough pistons
4. Calibrate scale if needed
5. Clear work area

### During Jobs

- Monitor status messages
- Watch for errors or warnings
- Don't disturb hardware
- Keep emergency stop accessible

### After Jobs

- Review completion status
- Verify weights are as expected
- Remove filled molds
- Refill dispensers if needed

## Tips for Efficiency

### Batch Similar Weights

Group wells with similar target weights together:

- Reduces trickler adjustments
- Faster overall completion
- More consistent results

### Start with Test Well

On first run:

1. Select single well
2. Run full cycle
3. Verify results
4. Then run full batch

### Plan Piston Usage

With 2 dispensers × 10 pistons = 20 total:

- Can run 20 wells before reload
- Plan batches accordingly
- Consider breaking large jobs into smaller runs

### Monitor First Few Wells

Stay present for first few wells:

- Verify operation is correct
- Watch for issues
- Confirm target weights are reasonable

## Next Steps

- Read [Architecture](../concepts/architecture.md) to understand system design
- Explore [JubileeViewModel API](../api/gui/jubilee-view-model.md) for customization
- Review [GUI Application API](../api/gui/jubilee-gui.md) for details
- Learn about [JubileeManager](../api/jubilee-manager.md) for underlying operations
