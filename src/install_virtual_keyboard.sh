#!/bin/bash

# Virtual Keyboard Installation Script for Raspbian
# This script installs and configures virtual keyboards for the Jubilee GUI

echo "Installing virtual keyboard for Jubilee GUI..."

# Update package list
sudo apt update

# Install matchbox-keyboard (recommended for touchscreens)
echo "Installing matchbox-keyboard..."
sudo apt install -y matchbox-keyboard

# Install alternative keyboards as backup
echo "Installing alternative virtual keyboards..."
sudo apt install -y florence onboard xvkbd

# Create a desktop file for matchbox-keyboard (optional)
cat > ~/.local/share/applications/matchbox-keyboard.desktop << EOF
[Desktop Entry]
Name=Matchbox Keyboard
Comment=Virtual keyboard for touchscreens
Exec=matchbox-keyboard
Icon=input-keyboard
Terminal=false
Type=Application
Categories=Utility;Accessibility;
EOF

# Set up autostart for matchbox-keyboard (optional - uncomment if needed)
# mkdir -p ~/.config/autostart
# cp ~/.local/share/applications/matchbox-keyboard.desktop ~/.config/autostart/

echo "Virtual keyboard installation complete!"
echo ""
echo "Available virtual keyboards:"
echo "- matchbox-keyboard (recommended)"
echo "- florence"
echo "- onboard"
echo "- xvkbd"
echo ""
echo "The Jubilee GUI will automatically detect and use the available keyboard."
echo "To test, run the Jubilee GUI and open a dialog with text input." 