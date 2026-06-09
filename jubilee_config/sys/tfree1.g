; tfree1.g
; Shore-A Hardness Tester
; Runs at the start of a toolchange if the current tool is tool-1.

G1 Z150                       ; Move Z so trickler is clear of molds.
G1 X91.0 F3000                ; Move to the pickup position with tool-1.
G1 Y260.0 F3000

; G53 G0 X91.0 Y260.0 F300   ; Ready point, kept for reference

G1 Y300 F1000               ; Controlled move to the park position with tool-1. (park_x, park_y)
                             ; This y position is different from picking up the tool because the tool typically
                             ; does not sit as deep when being replaced
M98 P"/macros/tool_unlock.g" ; Unlock the tool
G1 Y260.0 F1000               ; Retract the pin.
G1 Y80.0 F3000                ; Return to global ready
G1 X150.0 F3000    
G1 Z95     
