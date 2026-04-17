; tfree0.g
; Runs at the start of a toolchange if the current tool is tool-0.
; Note: tool offsets are applied at this point unless we preempt commands with G53!

G1 Z90                       ; Move Z so tool leadscrew is clear of molds. 90 is enough.
G1 X40.0 F3000                ; Move to the pickup position with tool-0. Follow dog-leg pattern to avoid trickler.
G1 Y260.0 F3000

; G53 G0 X40.0 Y260.0 F300   ; Ready point, kept for reference

G1 Y309.5 F1000               ; Controlled move to the park position with tool-1. (park_x, park_y)
                             ; This y position is different from picking up the tool because the tool typically
                             ; does not sit as deep when being replaced
M98 P"/macros/tool_unlock.g" ; Unlock the tool
G1 Y260.0 F1000               ; Retract the pin.
G1 V30                       ; Return tool to 30 position so that it will not try to re-home next time with
                             ; the limit switch already engaged. This position should only occur when tamping,
                             ; but better to be safe.
G1 Y80.0 F3000                ; Return to global ready
G1 X150.0 F3000         