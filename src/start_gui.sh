#!/bin/bash

# Jubilee GUI Launcher Script
# This script launches the Jubilee GUI application with proper environment setup

echo "Starting Jubilee Powder Dispensing GUI..."

# Set display for touch screen (adjust if needed)
export DISPLAY=:0

# Set environment variables for Kivy
export KIVY_GL_BACKEND=sdl2
export KIVY_WINDOW=sdl2

# Navigate to script directory
cd "$(dirname "$0")"

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    exit 1
fi

# Check if required packages are installed
if ! python3 -c "import kivy" &> /dev/null; then
    echo "Error: Kivy is not installed. Please run: pip3 install kivy"
    exit 1
fi

# Launch the GUI application
echo "Launching application..."
python3 jubilee_gui.py

# If the application exits with an error, show the error
if [ $? -ne 0 ]; then
    echo "Application exited with an error"
    read -p "Press Enter to continue..."
fi 