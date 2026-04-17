; Home X Axis

; In case homex.g is called in isolation, ensure 
; (1) U axis is homed (which performs tool detection and sets machine tool state to a known state) and 
; (2) Y axis is homed (to prevent collisions with the tool posts)
; (3) Y axis is in a safe position (see 2)
; (4) No tools are loaded.
; Ask for user-intervention if either case fails.

G90                     ; Set absolute mode

if !move.axes[3].homed
  M291 R"Cannot Home X" P"U axis must be homed before X to prevent damage to tool. Press OK to home U or Cancel to abort" S3
  M98 P"homeu.g"

if !move.axes[1].homed
  M291 R"Cannot Home X" P"Y axis must be homed before x to prevent damage to tool. Press OK to home Y or Cancel to abort" S3
  M98 P"homey.g"
  
if move.axes[1].userPosition != 0
  M291 R"Cannot Home X" P"Y axis must be at Y=0 to prevent collision with back leadscrew. Press OK to *move Y to Y=0* or Cancel to abort" S3
  G0 Y0 F500            ; Slow move to safe y position to give user time to abort

if state.currentTool != -1
  M84 U
  M291 R"Cannot Home X" P"Tool must be deselected before homing. U has been unlocked, please manually dock tool and press OK to continue or Cancel to abort" S3
  M98 P"homeu.g"
  
G91                     ; Relative mode
G1 H2 Z25 F5000         ; Lower the bed
G1 X-330 F6000 H1       ; Big negative move to search for endstop
G1 X4 F600              ; Back off the endstop
G1 X-10 F600 H1         ; Find endstop again slowly
G1 H2 Z-25 F5000        ; Raise the bed
G90                     ; Set absolute mode
G1 X0 F5000             ; Move to edge of work space
