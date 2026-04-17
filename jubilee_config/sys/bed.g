; This macro should ONLY be called from homez.g, as it assumes it is in a safe position to move
; to the front left probe point.
M290 R0 S0                  ; Reset baby stepping
M561                        ; Disable any Mesh Bed Compensation
G90                         ; Ensure the machine is in absolute mode

G1 Z60 F5000                     ; pop bed down
G1 X273.3 Y175 F5000                    
G30 P0 X273.3 Y175 Z-99999  ; probe near front left leadscrew
G1 Z60 F5000
G1 Y163 F5000                     ; Move out of way of trickler
G1 X52 F5000
G1 Y177 F5000
G30 P1 X52 Y177 Z-99999     ; probe near front right leadscrew and calibrate 3 motors
G1 Z60 F5000
G1 Y0 F5000                  ; move near back leadscrew, avoiding trickler
G1 X137 F5000
G30 P2 X137 Y0 Z-99999 S3   ; probe near back leadscrew
G1 Z95 F5000                ; Move bed to mold transfer height when finished
; G29 S2                    ; Disable Mesh Bed Compensation (height map not accurate for current bed)
G1 X150.0 Y80.0 F5000       ; Move to global ready position