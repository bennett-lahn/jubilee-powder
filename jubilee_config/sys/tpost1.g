; tpost1.g
; Shore-A Hardness Tester
; called after firmware thinks Tool1 is selected
; Note: tool offsets are applied at this point!
; Note that commands preempted with G53 will NOT apply the tool offset.

; M116 P1                  ; Wait for set temperatures to be reached
; M302 P1                  ; Prevent Cold Extrudes, just in case temp setpoints are at 0

G90                        ; Ensure the machine is in absolute mode before issuing movements.
G1 Z150                    ; Ensure tool will clear trickler when tool is removed
M98 P"/macros/tool_lock.g" ; Lock the tool
G1 Y260.0 F1000         ; Back off the tool post
G1 Y80.0 F3000          ; Move back to global ready position in dogleg shape to avoid hitting trickler
G1 X150.0 F3000
G1 Z95