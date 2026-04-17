; tpre0.g
; Runs after freeing the previous tool if the next tool is tool-0.
; Note: tool offsets are not applied at this point!

G90                    ; Ensure the machine is in absolute mode before issuing movements.
G0 Z90                 ; Ensure Z is clear of molds, trickler resevoir
G0 X40.0 F5000         ; Rapid to the approach position without any current tool.
G0 Y260.0 F5000        ; Follow dogleg pattern to ensure trickler is safe
; G0 X40.0 Y260.0 F6000 ; Tool 0 ready position (kept for reference)  
G60 S0                 ; Save this position as the reference point from which to later apply new tool offsets.