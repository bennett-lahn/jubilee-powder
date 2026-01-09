#!/usr/bin/env python3
# TODO: on Raspbian: Install xsel or xclip for copy-paste support.
# TODO: Implement Abort and cancel when job is running
# TODO: Use .JSON to make jobs configurablen

# Theme configuration
THEME = {
    'background': (1, 1, 1, 1),  # White
    'surface': (0.98, 0.98, 0.98, 1),  # Light gray
    'primary': (0.13, 0.59, 0.95, 1),  # Blue
    'secondary': (0.30, 0.69, 0.31, 1),  # Green
    'warning': (0.96, 0.60, 0.0, 1),  # Orange
    'error': (0.96, 0.26, 0.21, 1),  # Red
    'text_primary': (0.13, 0.13, 0.13, 1),  # Dark gray
    'text_secondary': (0.6, 0.6, 0.6, 1),  # Medium gray
    'text_white': (1, 1, 1, 1),  # White text
    'border': (0.9, 0.9, 0.9, 1),  # Light border
}

import kivy
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.checkbox import CheckBox
from kivy.uix.progressbar import ProgressBar
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.widget import Widget
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.graphics import Color, Rectangle, Line, Ellipse
from kivy.properties import ObjectProperty, StringProperty, NumericProperty, BooleanProperty
from kivy.lang import Builder
from kivy.uix.relativelayout import RelativeLayout
import threading
import time
import json
from typing import List, Dict, Optional
from dataclasses import dataclass
import os
import sys
import subprocess

# Import Jubilee components
from science_jubilee.Machine import Machine
from src.Scale import Scale
from src.JubileeManager import JubileeManager

# Virtual Keyboard Management Class
class VirtualKeyboardManager:
    """Manages virtual keyboard visibility on Raspbian"""
    
    def __init__(self):
        self.keyboard_process = None
        self.keyboard_name = None
        self._detect_keyboard()
    
    def _detect_keyboard(self):
        """Detect available virtual keyboards on the system"""
        try:
            # Common virtual keyboard names on Raspbian
            possible_keyboards = [
                'matchbox-keyboard',
                'florence',
                'onboard',
                'xvkbd',
                'gok'
            ]
            
            for keyboard in possible_keyboards:
                result = subprocess.run(['which', keyboard], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    self.keyboard_name = keyboard
                    print(f"Detected virtual keyboard: {keyboard}")
                    break
            
            if not self.keyboard_name:
                print("No virtual keyboard detected. Install one with: sudo apt install matchbox-keyboard")
                
        except Exception as e:
            print(f"Error detecting keyboard: {e}")
    
    def show_keyboard(self):
        """Show the virtual keyboard"""
        if not self.keyboard_name:
            print("No virtual keyboard available")
            return False
        
        try:
            # Kill any existing keyboard process
            self.hide_keyboard()
            
            # Start new keyboard process
            if self.keyboard_name == 'matchbox-keyboard':
                self.keyboard_process = subprocess.Popen([
                    'matchbox-keyboard', '--xid'
                ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            elif self.keyboard_name == 'florence':
                self.keyboard_process = subprocess.Popen([
                    'florence', '--geometry', '800x300+0+0'
                ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            elif self.keyboard_name == 'onboard':
                self.keyboard_process = subprocess.Popen([
                    'onboard', '--xid'
                ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            else:
                self.keyboard_process = subprocess.Popen([self.keyboard_name])
            
            print(f"Virtual keyboard ({self.keyboard_name}) shown")
            return True
            
        except Exception as e:
            print(f"Error showing keyboard: {e}")
            return False
    
    def hide_keyboard(self):
        """Hide the virtual keyboard"""
        try:
            if self.keyboard_process:
                self.keyboard_process.terminate()
                self.keyboard_process.wait(timeout=2)
                self.keyboard_process = None
                print("Virtual keyboard hidden")
            
            # Also try to kill any remaining keyboard processes
            if self.keyboard_name:
                subprocess.run(['pkill', '-f', self.keyboard_name], 
                             capture_output=True)
                
        except Exception as e:
            print(f"Error hiding keyboard: {e}")
    
    def is_keyboard_visible(self):
        """Check if keyboard is currently visible"""
        if not self.keyboard_name:
            return False
        
        try:
            result = subprocess.run(['pgrep', '-f', self.keyboard_name], 
                                  capture_output=True)
            return result.returncode == 0
        except:
            return False

# Global keyboard manager instance
keyboard_manager = VirtualKeyboardManager()

# Configure Kivy for touch interface
Window.softinput_mode = 'below_target'
kivy.require('2.0.0')

# Set window to fullscreen
Window.fullscreen = 'auto'

class WeightWellButton(Button):
    """Custom button for weight wells with selection state"""
    selected = BooleanProperty(False)
    well_id = StringProperty('')
    weight = NumericProperty(0.0)  # Target weight (requested)
    actual_weight = NumericProperty(0.0)  # Actual measured weight
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(size=self._update_font_size)
        Clock.schedule_once(lambda dt: self._update_font_size(self, self.size), 0.1)
    
    def on_selected(self, instance, value):
        """Update color when selected state changes"""
        if value:
            self.background_color = THEME['primary']  # Blue when selected
            self.color = THEME['text_white']  # White text for selected
        else:
            # Color based on actual weight: red if 0, green if > 0
            if self.actual_weight > 0:
                self.background_color = THEME['secondary']  # Green when actual weight > 0
            else:
                self.background_color = THEME['error']  # Red when actual weight = 0
            self.color = THEME['text_white']  # White text for better contrast
    
    def on_weight(self, instance, value):
        """Update color when target weight changes"""
        if not self.selected:
            # Color is based on actual weight, not target weight
            if self.actual_weight > 0:
                self.background_color = THEME['secondary']  # Green when actual weight > 0
            else:
                self.background_color = THEME['error']  # Red when actual weight = 0
    
    def on_actual_weight(self, instance, value):
        """Update color when actual weight changes"""
        if not self.selected:
            if value > 0:
                self.background_color = THEME['secondary']  # Green when actual weight > 0
            else:
                self.background_color = THEME['error']  # Red when actual weight = 0
    
    def _update_font_size(self, instance, value):
        """Update font size when button size changes"""
        if value[0] <= 0 or value[1] <= 0:
            return
        # Calculate font size based on button size (responsive to smallest dimension)
        # Use sp for scale-independent sizing
        min_size = min(value[0], value[1])
        font_size = max(sp(8), min(sp(24), min_size * 0.15))
        self.font_size = font_size

class CustomButton(Button):
    """Custom button with responsive font sizing"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(size=self._update_font_size)
        Clock.schedule_once(lambda dt: self._update_font_size(self, self.size), 0.1)
    
    def _update_font_size(self, instance, value):
        """Update font size when button size changes"""
        if value[1] <= 0:
            return
        # Calculate font size based on button height (minimum 12sp, maximum 36sp)
        # Use sp for scale-independent sizing
        height = value[1]
        font_size = max(sp(12), min(sp(36), height * 0.35))
        self.font_size = font_size

class CustomLabel(Label):
    """Custom label with responsive font sizing"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(size=self._update_font_size)
        Clock.schedule_once(lambda dt: self._update_font_size(self, self.size), 0.1)
    
    def _update_font_size(self, instance, value):
        """Update font size when label size changes"""
        if value[1] <= 0:
            return
        # Calculate font size based on label height (minimum 10sp, maximum 36sp)
        # Use sp for scale-independent sizing
        height = value[1]
        font_size = max(sp(10), min(sp(36), height * 0.45))
        self.font_size = font_size

class CustomCheckBox(CheckBox):
    """Custom checkbox with blacker outline and touchscreen-friendly sizing"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Set minimum size for touchscreen use
        self.size_hint = (None, None)
        self.size = (dp(80), dp(80))  # Large size for touchscreen
        self.bind(size=self._on_size)
    
    def _on_size(self, instance, value):
        """Update checkbox appearance when size changes"""
        # The checkbox will automatically scale with its size
        pass
    
    def on_size(self, instance, value):
        """Called when the checkbox size changes"""
        # Ensure minimum touch-friendly size
        min_size = dp(60)
        if self.width < min_size or self.height < min_size:
            self.size = (max(self.width, min_size), max(self.height, min_size))

class CustomTextInput(TextInput):
    """Custom TextInput that manages virtual keyboard visibility"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(focus=self._on_focus_change)
        self.bind(text=self._on_text_change)
    
    def _on_focus_change(self, instance, value):
        """Handle focus changes to show/hide keyboard"""
        if value:  # TextInput gained focus
            # Show virtual keyboard
            keyboard_manager.show_keyboard()
            print("TextInput focused - showing keyboard")
        else:  # TextInput lost focus
            # Hide virtual keyboard after a short delay
            Clock.schedule_once(self._hide_keyboard_delayed, 0.5)
            print("TextInput unfocused - hiding keyboard")
    
    def _hide_keyboard_delayed(self, dt):
        """Hide keyboard with delay to allow for touch events"""
        # Only hide if no other TextInput is focused
        if not self.focus:
            keyboard_manager.hide_keyboard()
    
    def _on_text_change(self, instance, value):
        """Handle text changes"""
        # You can add custom text validation here if needed
        pass

# KV Language string for custom styling
KV = '''
#:import utils kivy.utils

# Global Popup styling
<Popup>:
    background: ''  # Remove default background
    background_color: 1, 1, 1, 1  # White background
    title_color: 0.13, 0.13, 0.13, 1  # Dark text

<CustomButton>:
    background_color: 0.13, 0.59, 0.95, 1  # Primary blue
    background_normal: ''
    color: 1, 1, 1, 1  # White text
    size_hint_y: None
    height: dp(60)
    font_size: sp(16)  # Scale-independent font size
    canvas.before:
        Color:
            rgba: 0.10, 0.46, 0.74, 1 if self.state == 'down' else 0.13, 0.59, 0.95, 1
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(8)]

<CustomLabel>:
    color: 0.13, 0.13, 0.13, 1  # Text primary
    font_size: sp(14)  # Scale-independent font size
    size_hint_y: None
    height: dp(40)

<CustomCheckBox>:
    size_hint: None, None
    size: dp(80), dp(80)  # Large size for touchscreen
    color: 0.13, 0.59, 0.95, 1  # Blue when checked
    canvas.before:
        # Blacker outline for better visibility
        Color:
            rgba: 0.1, 0.1, 0.1, 1  # Very dark gray/black outline
        Ellipse:
            pos: self.pos
            size: self.size
        # Background
        Color:
            rgba: 1, 1, 1, 1  # White background
        Ellipse:
            pos: self.x + dp(2), self.y + dp(2)
            size: self.width - dp(4), self.height - dp(4)
    canvas.after:
        # Check mark when active
        Color:
            rgba: 0.13, 0.59, 0.95, 1 if self.active else 0, 0, 0, 0
        Ellipse:
            pos: self.x + self.width * 0.2, self.y + self.height * 0.2
            size: self.width * 0.6, self.height * 0.6

<CustomTextInput>:
    background_color: 1, 1, 1, 1  # White background
    foreground_color: 0.13, 0.13, 0.13, 1  # Dark text
    cursor_color: 0.13, 0.59, 0.95, 1  # Blue cursor
    font_size: sp(16)  # Scale-independent font size
    size_hint_y: None
    height: dp(50)
    padding: dp(10)
    multiline: False
    canvas.before:
        Color:
            rgba: 0.8, 0.8, 0.8, 1  # Light gray border
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(5)]
        Color:
            rgba: self.background_color
        RoundedRectangle:
            pos: self.x + dp(2), self.y + dp(2)
            size: self.width - dp(4), self.height - dp(4)
            radius: [dp(3)]

<WeightWellButton>:
    background_color: 0.96, 0.26, 0.21, 1  # Default error color (actual_weight = 0)
    background_normal: ''
    color: 1, 1, 1, 1  # White text for better contrast
    size_hint: 1, 1  # Fill available space
    font_size: sp(12)  # Scale-independent font size (will be adjusted dynamically)
    text: f'{self.well_id}\\nTarget: {self.weight:.3f}g\\nActual: {self.actual_weight:.3f}g'
    canvas.before:
        Color:
            rgba: self.background_color
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(6)]

<MainScreen>:
    canvas.before:
        Color:
            rgba: 1, 1, 1, 1  # Background color
        Rectangle:
            pos: self.pos
            size: self.size
    BoxLayout:
        orientation: 'vertical'
        padding: dp(20)
        spacing: dp(10)
        
        # Header
        BoxLayout:
            size_hint_y: None
            height: dp(80)
            CustomLabel:
                text: 'Jubilee Powder Dispensing System'
                font_size: sp(24)
                bold: True
                halign: 'center'
                valign: 'middle'
                text_size: self.size
        
        # Platform visualization
        BoxLayout:
            orientation: 'horizontal'
            size_hint_y: 1
            
            # Left side - Scale
            BoxLayout:
                orientation: 'vertical'
                size_hint_x: 0.2
                padding: dp(10)
                
                CustomLabel:
                    text: 'Scale'
                    halign: 'center'
                    bold: True
                
                BoxLayout:
                    orientation: 'vertical'
                    canvas.before:
                        Color:
                            rgba: 1.0, 0.60, 0.0, 1  # Orange for scale
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [dp(8)]
                    
                    CustomLabel:
                        text: 'Connected' if root.scale_connected else 'Disconnected'
                        halign: 'center'
                        valign: 'middle'
                        text_size: self.size
                        color: 1, 1, 1, 1
                        font_size: sp(14)
                    
                    CustomLabel:
                        text: f'{root.current_weight:.3f}g'
                        halign: 'center'
                        valign: 'middle'
                        text_size: self.size
                        color: 1, 1, 1, 1
                        font_size: sp(18)
                        bold: True
            
            # Center - Platform
            BoxLayout:
                orientation: 'vertical'
                size_hint_x: 0.6
                size_hint_y: 1
                padding: dp(10)
                
                CustomLabel:
                    text: 'Jubilee Platform'
                    halign: 'center'
                    valign: 'middle'
                    text_size: self.size
                    bold: True
                    font_size: sp(16)
                
                GridLayout:
                    id: platform_grid
                    cols: 7
                    spacing: dp(5)
                    padding: dp(10)
                    size_hint: 1, 1  # Fill available space
                    canvas.before:
                        Color:
                            rgba: 0.98, 0.98, 0.98, 1  # Surface color
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [dp(8)]
                    
                    WeightWellButton:
                        text: 'A1\\n0.0g'
                        well_id: 'A1'
                        selected: root.is_well_selected('A1')
                        on_press: root.toggle_well('A1')
                    
                    WeightWellButton:
                        text: 'A2\\n0.0g'
                        well_id: 'A2'
                        selected: root.is_well_selected('A2')
                        on_press: root.toggle_well('A2')
                    
                    WeightWellButton:
                        text: 'A3\\n0.0g'
                        well_id: 'A3'
                        selected: root.is_well_selected('A3')
                        on_press: root.toggle_well('A3')
                    
                    WeightWellButton:
                        text: 'A4\\n0.0g'
                        well_id: 'A4'
                        selected: root.is_well_selected('A4')
                        on_press: root.toggle_well('A4')
                    
                    WeightWellButton:
                        text: 'A5\\n0.0g'
                        well_id: 'A5'
                        selected: root.is_well_selected('A5')
                        on_press: root.toggle_well('A5')
                    
                    WeightWellButton:
                        text: 'A6\\n0.0g'
                        well_id: 'A6'
                        selected: root.is_well_selected('A6')
                        on_press: root.toggle_well('A6')
                    
                    WeightWellButton:
                        text: 'A7\\n0.0g'
                        well_id: 'A7'
                        selected: root.is_well_selected('A7')
                        on_press: root.toggle_well('A7')
                    
                    WeightWellButton:
                        text: 'B1\\n0.0g'
                        well_id: 'B1'
                        selected: root.is_well_selected('B1')
                        on_press: root.toggle_well('B1')
                    
                    WeightWellButton:
                        text: 'B2\\n0.0g'
                        well_id: 'B2'
                        selected: root.is_well_selected('B2')
                        on_press: root.toggle_well('B2')
                    
                    WeightWellButton:
                        text: 'B3\\n0.0g'
                        well_id: 'B3'
                        selected: root.is_well_selected('B3')
                        on_press: root.toggle_well('B3')
                    
                    WeightWellButton:
                        text: 'B4\\n0.0g'
                        well_id: 'B4'
                        selected: root.is_well_selected('B4')
                        on_press: root.toggle_well('B4')
                    
                    WeightWellButton:
                        text: 'B5\\n0.0g'
                        well_id: 'B5'
                        selected: root.is_well_selected('B5')
                        on_press: root.toggle_well('B5')
                    
                    WeightWellButton:
                        text: 'B6\\n0.0g'
                        well_id: 'B6'
                        selected: root.is_well_selected('B6')
                        on_press: root.toggle_well('B6')
                    
                    WeightWellButton:
                        text: 'B7\\n0.0g'
                        well_id: 'B7'
                        selected: root.is_well_selected('B7')
                        on_press: root.toggle_well('B7')
                    
                    WeightWellButton:
                        text: 'C1\\n0.0g'
                        well_id: 'C1'
                        selected: root.is_well_selected('C1')
                        on_press: root.toggle_well('C1')
                    
                    WeightWellButton:
                        text: 'C2\\n0.0g'
                        well_id: 'C2'
                        selected: root.is_well_selected('C2')
                        on_press: root.toggle_well('C2')
                    
                    WeightWellButton:
                        text: 'C3\\n0.0g'
                        well_id: 'C3'
                        selected: root.is_well_selected('C3')
                        on_press: root.toggle_well('C3')
                    
                    WeightWellButton:
                        text: 'C4\\n0.0g'
                        well_id: 'C4'
                        selected: root.is_well_selected('C4')
                        on_press: root.toggle_well('C4')
            
            # Right side - Controls
            BoxLayout:
                orientation: 'vertical'
                size_hint_x: 0.2
                padding: dp(10)
                spacing: dp(10)
                
                CustomLabel:
                    text: 'Controls'
                    halign: 'center'
                    valign: 'middle'
                    text_size: self.size
                    bold: True
                    font_size: sp(16)
                
                CustomButton:
                    text: 'Select All'
                    on_press: root.select_all_wells()
                
                CustomButton:
                    text: 'Set Weights'
                    on_press: root.show_weight_dialog()
                
                CustomButton:
                    text: 'Start Job'
                    on_press: root.start_job()
                    disabled: not root.can_start_job()
                
                CustomButton:
                    text: 'Start Job (Bypass)'
                    on_press: root.start_job_bypass()
                    # disabled: not root.can_start_job_bypass()
                    background_color: 0.96, 0.60, 0.0, 1  # Warning color for bypass mode
                
                CustomButton:
                    text: 'Stop Job'
                    on_press: root.stop_job()
                    disabled: not root.job_running
                
                CustomButton:
                    text: 'Shutdown'
                    on_press: root.shutdown_system()
                    background_color: 0.96, 0.26, 0.21, 1  # Error color for shutdown
        
        # Status bar
        BoxLayout:
            size_hint_y: None
            height: dp(40)
            canvas.before:
                Color:
                    rgba: 0.95, 0.95, 0.95, 1  # Surface color for status bar
                Rectangle:
                    pos: self.pos
                    size: self.size
            
            CustomLabel:
                text: root.status_text
                halign: 'left'
                valign: 'middle'
                text_size: self.size
                font_size: sp(14)
                padding: dp(10), 0



<ChecklistDialog>:
    canvas.before:
        Color:
            rgba: 1, 1, 1, 1  # White background
        Rectangle:
            pos: self.pos
            size: self.size

<ProgressDialog>:
    canvas.before:
        Color:
            rgba: 1, 1, 1, 1  # Background color
        Rectangle:
            pos: self.pos
            size: self.size
    BoxLayout:
        orientation: 'vertical'
        padding: dp(40)
        spacing: dp(20)
        
        # Header
        CustomLabel:
            text: 'Job Progress'
            font_size: sp(32)
            bold: True
            halign: 'center'
            valign: 'middle'
            text_size: self.size
            color: 0.13, 0.13, 0.13, 1  # Text primary color
            size_hint_y: None
            height: dp(80)
        
        # Circular progress area
        BoxLayout:
            orientation: 'vertical'
            size_hint_y: 1
            padding: dp(20)
            
            # Circular progress container
            RelativeLayout:
                id: progress_container
                size_hint_y: None
                height: dp(300)
                
                # Circular progress bar
                Widget:
                    id: progress_circle
                    size_hint: None, None
                    size: dp(250), dp(250)
                    pos_hint: {'center_x': 0.5, 'center_y': 0.5}
                    canvas.before:
                        # Background circle
                        Color:
                            rgba: 0.9, 0.9, 0.9, 1  # Light gray background
                        Ellipse:
                            pos: self.pos
                            size: self.size
                        # Progress circle
                        Color:
                            rgba: 0.13, 0.59, 0.95, 1  # Blue progress
                        Line:
                            circle: self.center_x, self.center_y, min(self.width, self.height)/2 - dp(10), 0, root.progress_value * 3.6, 360
                            width: dp(15)
                
                # Center text overlay
                BoxLayout:
                    orientation: 'vertical'
                    size_hint: None, None
                    size: dp(200), dp(200)
                    pos_hint: {'center_x': 0.5, 'center_y': 0.5}
                    
                    CustomLabel:
                        text: f'{root.completed_wells}/{root.total_wells}'
                        font_size: sp(32)
                        bold: True
                        halign: 'center'
                        valign: 'middle'
                        text_size: self.size
                        color: 0.13, 0.13, 0.13, 1  # Text primary color
                        size_hint_y: None
                        height: dp(60)
                    
                    CustomLabel:
                        text: 'Completed'
                        font_size: sp(18)
                        halign: 'center'
                        valign: 'middle'
                        text_size: self.size
                        color: 0.13, 0.13, 0.13, 1  # Text primary color
                        size_hint_y: None
                        height: dp(40)
                    
                    CustomLabel:
                        text: f'{root.progress_value:.1f}%'
                        font_size: sp(24)
                        bold: True
                        halign: 'center'
                        valign: 'middle'
                        text_size: self.size
                        color: 0.13, 0.59, 0.95, 1  # Blue percentage
                        size_hint_y: None
                        height: dp(50)
        
        # Current well text
        CustomLabel:
            text: root.current_well_text
            halign: 'center'
            valign: 'middle'
            text_size: self.size
            color: 0.13, 0.13, 0.13, 1  # Text primary color
            font_size: sp(20)
            size_hint_y: None
            height: dp(60)
        
        # Control buttons
        BoxLayout:
            orientation: 'horizontal'
            size_hint_y: None
            height: dp(100)
            spacing: dp(20)
            
            CustomButton:
                text: 'Cancel'
                on_press: root.cancel_job()
                background_color: 0.96, 0.60, 0.0, 1  # Warning color
                color: 1, 1, 1, 1  # White text
                size_hint_x: 0.4
                font_size: sp(18)
        
        # Large abort button
        CustomButton:
            text: root.abort_button_text
            on_press: root.abort_job()
            background_color: root.abort_button_color
            color: 1, 1, 1, 1  # White text
            size_hint_y: None
            height: dp(120)
            font_size: sp(24)
            bold: True



<ErrorDialog>:
    canvas.before:
        Color:
            rgba: 1, 1, 1, 1  # White background
        Rectangle:
            pos: self.pos
            size: self.size
    BoxLayout:
        orientation: 'vertical'
        padding: dp(40)
        spacing: dp(20)
        
        CustomLabel:
            text: 'Error'
            font_size: sp(32)
            bold: True
            halign: 'center'
            valign: 'middle'
            text_size: self.size
            color: 0.96, 0.26, 0.21, 1  # Error color
            size_hint_y: None
            height: dp(80)
        
        ScrollView:
            CustomLabel:
                text: root.error_message
                halign: 'center'
                valign: 'top'
                text_size: self.width, None
                color: 0.13, 0.13, 0.13, 1  # Text primary color
                font_size: sp(18)
                size_hint_y: None
                height: self.texture_size[1] + dp(40)
        
        CustomButton:
            text: 'OK'
            on_press: root.dismiss()
            background_color: 0.96, 0.26, 0.21, 1  # Error color
            color: 1, 1, 1, 1  # White text
            font_size: sp(18)
            size_hint_y: None
            height: dp(80)
'''

Builder.load_string(KV)

@dataclass
class JobWell:
    """Represents a well in a dispensing job"""
    well_id: str
    target_weight: float
    current_weight: float = 0.0
    completed: bool = False

class MainScreen(Screen):
    """Main screen of the Jubilee GUI application"""
    
    # Properties
    status_text = StringProperty("Ready")
    current_weight = NumericProperty(0.0)
    scale_connected = BooleanProperty(False)
    job_running = BooleanProperty(False)
    selected_wells = ObjectProperty(set())
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.jubilee_manager = JubileeManager()
        self.selected_wells = set()
        self.well_weights = {}  # well_id -> target_weight
        self.actual_weights = {}  # well_id -> actual_weight
        self.job_wells = []
        self.current_job_thread = None
        
        # Bind to window size changes for responsive layout
        Window.bind(size=self._on_window_resize)
        
        # Start weight monitoring
        Clock.schedule_interval(self.update_weight, 0.5)
        
        # Try to connect
        self.connect_to_system()
        
        # Initialize well weights dictionary
        self._init_well_weights()
        
        # Update all well button texts to show current weights
        Clock.schedule_once(self.update_all_well_texts, 0.1)
    
    def _on_window_resize(self, instance, value):
        """Handle window resize events for responsive layout"""
        # Update all well button texts to ensure proper sizing
        Clock.schedule_once(lambda dt: self.update_all_well_texts(), 0.1)
    
    def _init_well_weights(self):
        """Initialize the well weights dictionary with all wells set to 0.0"""
        well_ids = ['A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7',
                   'B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 
                   'C1', 'C2', 'C3', 'C4']
        for well_id in well_ids:
            if well_id not in self.well_weights:
                self.well_weights[well_id] = 0.0
            if well_id not in self.actual_weights:
                self.actual_weights[well_id] = 0.0
        print(f"Initialized well_weights: {self.well_weights}")  # Debug print
        print(f"Initialized actual_weights: {self.actual_weights}")  # Debug print
        
        # Update all button texts after initialization
        Clock.schedule_once(self.update_all_well_texts, 0.1)
    
    def connect_to_system(self):
        """Connect to Jubilee system"""
        self.status_text = "Connecting..."
        threading.Thread(target=self._connect_thread, daemon=True).start()
    
    def _connect_thread(self):
        """Connection thread to avoid blocking UI"""
        success = self.jubilee_manager.connect()
        if success:
            self.status_text = "Connected"
            # Check if scale is available
            if self.jubilee_manager.scale and self.jubilee_manager.scale.is_connected:
                self.scale_connected = True
            else:
                self.scale_connected = False
        else:
            self.status_text = "Connection failed"
            self.scale_connected = False
    
    def update_weight(self, dt):
        """Update current weight display"""
        if self.jubilee_manager.connected:
            self.current_weight = self.jubilee_manager.get_weight_unstable()
    
    def toggle_well(self, well_id: str):
        """Toggle selection of a well"""
        wells = set(self.selected_wells)  # Convert to set for manipulation
        if well_id in wells:
            wells.remove(well_id)
        else:
            wells.add(well_id)
        self.selected_wells = wells
        
        # Update the button's selected property to trigger color change
        grid = self.ids.platform_grid
        for child in grid.children:
            if hasattr(child, 'well_id') and child.well_id == well_id:
                child.selected = well_id in wells
                break
    
    def select_all_wells(self):
        """Select all wells"""
        well_ids = ['A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7',
                   'B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 
                   'C1', 'C2', 'C3', 'C4']
        self.selected_wells = set(well_ids)
        
        # Update all button selected properties
        grid = self.ids.platform_grid
        for child in grid.children:
            if hasattr(child, 'well_id'):
                child.selected = child.well_id in well_ids
    
    def update_well_button_text(self, well_id: str):
        """Update the text of a specific well button to show target and actual weights"""
        grid = self.ids.platform_grid
        target_weight = self.well_weights.get(well_id, 0.0)
        actual_weight = self.actual_weights.get(well_id, 0.0)
        for child in grid.children:
            if hasattr(child, 'well_id') and child.well_id == well_id:
                child.weight = target_weight  # Target weight
                child.actual_weight = actual_weight  # Actual weight
                return
        print(f"Button {well_id} not found in grid. Available children: {[getattr(child, 'well_id', 'no_id') for child in grid.children]}")
    

    
    def update_all_well_texts(self, dt=None):
        """Update all well button texts to show current weights"""
        well_ids = ['A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7',
                   'B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 
                   'C1', 'C2', 'C3', 'C4']
        for well_id in well_ids:
            self.update_well_button_text(well_id)
    
    def is_well_selected(self, well_id: str) -> bool:
        """Check if a well is selected"""
        return well_id in self.selected_wells
    
    def can_start_job(self) -> bool:
        """Check if job can be started"""
        return len(self.selected_wells or set()) > 0 and not self.job_running
    
    def can_start_job_bypass(self) -> bool:
        """Check if job can be started in bypass mode (for testing)"""
        not self.job_running
    
    def show_weight_dialog(self):
        """Show weight setting dialog"""
        if not (self.selected_wells or set()):
            self.show_error("Please select at least one well first.")
            return
        
        dialog = WeightDialog(self, self.selected_wells or set(), self.well_weights)
        dialog.open()
    
    def start_job(self):
        """Start the dispensing job"""
        if not self.can_start_job():
            return
        
        # Show checklist first
        checklist = ChecklistDialog()
        checklist.bind(on_dismiss=self._on_checklist_dismiss)
        checklist.open()
    
    def start_job_bypass(self):
        """Start the dispensing job in bypass mode (for testing without hardware)"""
        # if not self.can_start_job_bypass():
        #     return
        
        # Show checklist first (same as regular job)
        checklist = ChecklistDialog()
        checklist.bind(on_dismiss=self._on_checklist_dismiss_bypass)
        checklist.open()
    
    def _on_checklist_dismiss(self, instance):
        """Handle checklist dismissal for regular job"""
        if hasattr(instance, 'job_confirmed') and instance.job_confirmed:
            self._start_job_execution()
    
    def _on_checklist_dismiss_bypass(self, instance):
        """Handle checklist dismissal for bypass job"""
        if hasattr(instance, 'job_confirmed') and instance.job_confirmed:
            self._start_job_execution_bypass()
    
    def _start_job_execution(self):
        """Start the actual job execution"""
        self.job_running = True
        self.status_text = "Job running..."
        
        # Reset actual weights for wells being processed
        for well_id in (self.selected_wells or set()):
            if self.well_weights.get(well_id, 0.0) > 0:
                self.actual_weights[well_id] = 0.0
                self.update_well_button_text(well_id)
        
        # Create job wells list - only include wells with target weights > 0
        self.job_wells = [
            JobWell(well_id=well_id, target_weight=self.well_weights.get(well_id, 0.0))
            for well_id in (self.selected_wells or set())
            if self.well_weights.get(well_id, 0.0) > 0
        ]
        
        # Start job in background thread
        self.current_job_thread = threading.Thread(target=self._job_thread, daemon=True)
        self.current_job_thread.start()
        
        # Show progress dialog
        self.show_progress_dialog()
    
    def _start_job_execution_bypass(self):
        """Start the actual job execution in bypass mode"""
        self.job_running = True
        self.status_text = "Job running (Bypass Mode)..."
        
        # Reset actual weights for wells being processed
        for well_id in (self.selected_wells or set()):
            if self.well_weights.get(well_id, 0.0) > 0:
                self.actual_weights[well_id] = 0.0
                self.update_well_button_text(well_id)
        
        # Create job wells list - only include wells with target weights > 0
        self.job_wells = [
            JobWell(well_id=well_id, target_weight=self.well_weights.get(well_id, 0.0))
            for well_id in (self.selected_wells or set())
            if self.well_weights.get(well_id, 0.0) > 0
        ]
        
        # Start job in background thread (bypass mode)
        self.current_job_thread = threading.Thread(target=self._job_thread_bypass, daemon=True)
        self.current_job_thread.start()
        
        # Show progress dialog
        self.show_progress_dialog()
    
    def _job_thread(self):
        """Background thread for job execution"""
        try:
            for i, job_well in enumerate(self.job_wells):
                if not self.job_running:
                    # Job was cancelled or aborted
                    Clock.schedule_once(lambda dt: self._job_cancelled(i), 0)
                    return
                
                # Update progress
                self.update_job_progress(i, len(self.job_wells), job_well.well_id)
                
                # Dispense to well
                success = self.jubilee_manager.dispense_to_well(job_well.well_id, job_well.target_weight)
                if not success:
                    self.show_error(f"Failed to dispense to well {job_well.well_id}")
                    return
                
                job_well.completed = True
                
                # Update the actual weight in the main screen to show completion
                # In real mode, this would be the actual measured weight from the scale
                # For now, use target weight as actual weight (simulation)
                self.actual_weights[job_well.well_id] = job_well.target_weight
                self.update_well_button_text(job_well.well_id)
                
                # Update progress after completion
                self.update_job_progress(i + 1, len(self.job_wells), f"Completed {job_well.well_id}")
            
            # Job completed successfully
            Clock.schedule_once(lambda dt: self._job_completed(), 0)
            
        except Exception as e:
            Clock.schedule_once(lambda dt: self.show_error(f"Job error: {str(e)}"), 0)
        finally:
            Clock.schedule_once(lambda dt: setattr(self, 'job_running', False), 0)
    
    def _job_thread_bypass(self):
        """Background thread for job execution in bypass mode (for testing)"""
        try:
            for i, job_well in enumerate(self.job_wells):
                if not self.job_running:
                    # Job was cancelled or aborted
                    Clock.schedule_once(lambda dt: self._job_cancelled(i), 0)
                    return
                
                # Update progress
                self.update_job_progress(i, len(self.job_wells), f"Simulating {job_well.well_id}")
                
                # Simulate dispensing (wait 1.5 seconds to simulate work - faster for debugging)
                time.sleep(1.5)
                
                job_well.completed = True
                
                # Update the actual weight in the main screen to show completion
                # In simulation, use target weight as actual weight
                self.actual_weights[job_well.well_id] = job_well.target_weight
                self.update_well_button_text(job_well.well_id)
                
                # Update progress after completion
                self.update_job_progress(i + 1, len(self.job_wells), f"Completed {job_well.well_id}")
            
            # Job completed successfully
            Clock.schedule_once(lambda dt: self._job_completed(), 0)
            
        except Exception as e:
            Clock.schedule_once(lambda dt: self.show_error(f"Job error: {str(e)}"), 0)
        finally:
            Clock.schedule_once(lambda dt: setattr(self, 'job_running', False), 0)
    
    def update_job_progress(self, completed: int, total: int, current_well: str):
        """Update job progress (called from background thread)"""
        def update(dt):
            self.status_text = f"Processing {current_well} ({completed + 1}/{total})"
            
            # Update progress dialog if it exists
            if hasattr(self, 'progress_dialog') and self.progress_dialog:
                self.progress_dialog.completed_wells = completed
                self.progress_dialog.total_wells = total
                self.progress_dialog.current_well_text = current_well
                self.progress_dialog.progress_value = (completed / total) * 100 if total > 0 else 0
                
        Clock.schedule_once(update, 0)
    
    def _job_completed(self):
        """Handle job completion"""
        self.job_running = False
        self.status_text = "Job completed"
        
        # Update actual weights for completed wells
        self._update_actual_weights_from_job()
        
        self.show_finished_dialog()
    
    def _job_cancelled(self, completed_count: int):
        """Handle job cancellation"""
        self.job_running = False
        self.status_text = "Job cancelled"
        
        # Update actual weights only for wells that were actually completed
        self._update_actual_weights_from_job(completed_count)
        
        self.show_cancelled_dialog(completed_count)
    
    def _job_aborted(self, completed_count: int):
        """Handle job abort"""
        self.job_running = False
        self.status_text = "Job aborted"
        
        # Update actual weights only for wells that were actually completed
        self._update_actual_weights_from_job(completed_count)
        
        # Dismiss progress dialog and show aborted dialog
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.dismiss()
        
        self.show_aborted_dialog(completed_count)
    
    def _update_actual_weights_from_job(self, completed_count: int = None):
        """Update actual weights based on completed job wells"""
        if completed_count is None:
            # Use all completed wells (for successful completion)
            for job_well in self.job_wells:
                if job_well.completed:
                    # In real mode, this would be the actual measured weight
                    # For now, use target weight as actual weight (simulation)
                    self.actual_weights[job_well.well_id] = job_well.target_weight
                    self.update_well_button_text(job_well.well_id)
        else:
            # Use only the first N completed wells (for cancellation/abort)
            for i, job_well in enumerate(self.job_wells):
                if i < completed_count and job_well.completed:
                    # In real mode, this would be the actual measured weight
                    # For now, use target weight as actual weight (simulation)
                    self.actual_weights[job_well.well_id] = job_well.target_weight
                    self.update_well_button_text(job_well.well_id)
    
    def stop_job(self):
        """Stop the current job"""
        self.job_running = False
        self.status_text = "Job stopped"
    
    def stop_job_abort(self):
        """Stop the current job with abort flag"""
        self.job_running = False
        self.status_text = "Job aborted"
    
    def show_error(self, message: str):
        """Show error dialog"""
        dialog = ErrorDialog(error_message=message)
        dialog.open()
    
    def show_text_input_dialog(self):
        """Show text input dialog for testing virtual keyboard"""
        text_dialog = TextInputDialog()
        text_dialog.open()
    
    def show_progress_dialog(self):
        """Show progress dialog"""
        self.progress_dialog = ProgressDialog(
            completed_wells=0,
            total_wells=len(self.job_wells),
            current_well_text="Starting..."
        )
        self.progress_dialog.bind(on_dismiss=self._on_progress_dismiss)
        self.progress_dialog.open()
        
        # Flag to track if dialog is being dismissed due to abort/cancel
        self.progress_dialog_being_dismissed = False

        # Add a clock to auto-close the progress dialog when job ends
        def auto_close_progress_dialog(dt):
            if not self.job_running and self.progress_dialog and not self.progress_dialog_being_dismissed:
                self.progress_dialog.dismiss()
            else:
                # Reschedule if still running
                Clock.schedule_once(auto_close_progress_dialog, 0.5)
        Clock.schedule_once(auto_close_progress_dialog, 0.5)
    
    def _on_progress_dismiss(self, instance):
        """Handle progress dialog dismissal"""
        self.progress_dialog = None
        # Only call stop_job if not being dismissed due to abort/cancel
        if not hasattr(self, 'progress_dialog_being_dismissed') or not self.progress_dialog_being_dismissed:
            self.stop_job()
    
    def show_finished_dialog(self):
        """Show job finished dialog"""
        dialog = FinishedDialog()
        dialog.open()
    
    def show_cancelled_dialog(self, completed_count: int):
        """Show job cancelled dialog"""
        dialog = CancelledDialog(completed_count=completed_count, total_count=len(self.job_wells))
        dialog.open()
    
    def show_aborted_dialog(self, completed_count: int):
        """Show job aborted dialog"""
        dialog = AbortedDialog(completed_count=completed_count, total_count=len(self.job_wells))
        dialog.open()
    
    def shutdown_system(self):
        """Comprehensive shutdown procedure"""
        # Stop any running job first
        if self.job_running:
            self.stop_job()
        
        # Show shutdown confirmation dialog
        dialog = ShutdownDialog()
        dialog.bind(on_dismiss=self._on_shutdown_confirmed)
        dialog.open()
    
    def _on_shutdown_confirmed(self, instance):
        """Handle shutdown confirmation"""
        if hasattr(instance, 'confirmed') and instance.confirmed:
            self._perform_shutdown()
    
    def _perform_shutdown(self):
        """Perform the actual shutdown procedure"""
        try:
            self.status_text = "Shutting down..."
            
            # Step 1: Stop any running job
            if self.job_running:
                self.job_running = False
                self.status_text = "Stopping job..."
                time.sleep(1)
            
            # Step 2: Stow tools and return to home position (if connected)
            if self.jubilee_manager.connected and self.jubilee_manager.machine_read_only:
                self.status_text = "Stowing tools and returning to home..."
                self._stow_tools_and_home()
            
            # Step 3: Disconnect from all components
            self.status_text = "Disconnecting components..."
            self._disconnect_all()
            
            # Step 4: Additional shutdown procedures can be added here
            # Examples:
            # - Save configuration files
            # - Log shutdown event
            # - Clean up temporary files
            # - Send shutdown notification
            # - Power down connected devices
            
            # Step 5: Close the application
            self.status_text = "Shutdown complete"
            time.sleep(1)
            
            # Exit the application
            App.get_running_app().stop()
            
        except Exception as e:
            self.show_error(f"Shutdown error: {str(e)}")
    
    def _stow_tools_and_home(self):
        """Stow tools and return to home position"""
        try:
            machine = self.jubilee_manager.machine_read_only
            if not machine:
                return
            
            # Move to a safe position first
            machine.move_to(x=0, y=0, z=50)
            time.sleep(0.5)
            
            # Stow any loaded tools (assuming tool index 0)
            machine.stow_tool(0)
            time.sleep(1)
            
            # Return to home position
            machine.home()
            time.sleep(2)
            
        except Exception as e:
            print(f"Error during tool stowing: {e}")
            # Continue with shutdown even if this fails
    
    def _disconnect_all(self):
        """Disconnect from all components"""
        try:
            # Disconnect from Jubilee manager (includes machine and scale)
            if self.jubilee_manager:
                self.jubilee_manager.disconnect()
            
            # Clear any remaining callbacks
            Clock.unschedule(self.update_weight)
            
        except Exception as e:
            print(f"Error during disconnection: {e}")
            # Continue with shutdown even if this fails

class WeightDialog(Popup):
    """Dialog for setting target weights for all selected wells"""
    
    def __init__(self, main_screen, selected_wells: set, current_weights: dict, **kwargs):
        self.main_screen = main_screen
        super().__init__(**kwargs)
        self.selected_wells = selected_wells
        self.current_weights = current_weights
        # Responsive sizing based on screen size
        self.size_hint = (min(0.9, max(0.5, 600 / Window.width)), min(0.6, max(0.3, 400 / Window.height)))
        self.title = "Set Target Weight"
        self.background = ''  # Remove default background
        self.background_color = THEME['background']  # Theme background color
        self.title_color = THEME['text_primary']  # Theme text color
        self.title_size = sp(18)
        
        # Bind to window resize
        Window.bind(size=self._on_window_resize)
        
        # Create the dialog content
        self._create_content()
    
    def _on_window_resize(self, instance, value):
        """Handle window resize for responsive sizing"""
        self.size_hint = (min(0.9, max(0.5, 600 / value[0])), min(0.6, max(0.3, 400 / value[1])))
    
    def _create_content(self):
        """Create the dialog content"""
        layout = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(15))
        
        # Selected wells info
        wells_text = ', '.join(sorted(self.selected_wells))
        layout.add_widget(Label(
            text=f'Selected wells: {wells_text}',
            size_hint_y=None,
            height=dp(80),
            halign='center',
            valign='middle',
            font_size=sp(18),
            color=THEME['text_primary']  # Theme text color
        ))
        
        # Weight input
        layout.add_widget(Label(
            text='Target Weight (g):',
            size_hint_y=None,
            height=dp(60),
            halign='center',
            valign='middle',
            font_size=sp(20),
            color=THEME['text_primary']  # Theme text color
        ))
        
        self.weight_input = TextInput(
            text='0.0',
            multiline=False,
            size_hint_y=None,
            height=dp(80),
            input_filter='float',
            halign='center',
            font_size=sp(24),
            background_color=THEME['surface'],  # Theme surface color
            foreground_color=THEME['text_primary'],  # Theme text color
            cursor_color=THEME['primary']  # Theme primary color
        )
        layout.add_widget(self.weight_input)
        
        # Buttons
        button_layout = BoxLayout(size_hint_y=None, height=dp(100), spacing=dp(20))
        
        cancel_btn = Button(
            text='Cancel',
            background_color=THEME['error'],  # Theme error color
            color=THEME['text_white'],  # Theme white text
            on_press=self.dismiss,
            font_size=sp(18)
        )
        button_layout.add_widget(cancel_btn)
        
        apply_btn = Button(
            text='Apply to All',
            background_color=THEME['primary'],  # Theme primary color
            color=THEME['text_white'],  # Theme white text
            on_press=self.apply_weight,
            font_size=sp(18)
        )
        button_layout.add_widget(apply_btn)
        
        layout.add_widget(button_layout)
        
        # Set the content
        self.content = layout
    
    def apply_weight(self, instance):
        """Apply the weight to all selected wells"""
        try:
            weight = float(self.weight_input.text)
            print(f"Applying weight {weight} to wells: {self.selected_wells}")  # Debug print
            
            # Update main screen weights for all selected wells
            if hasattr(self.main_screen, 'well_weights'):
                for well_id in self.selected_wells:
                    self.main_screen.well_weights[well_id] = weight
                    self.main_screen.update_well_button_text(well_id)
                
                # Print current weights for debugging
                print(f"Current well_weights: {self.main_screen.well_weights}")
            else:
                print("Main screen has no well_weights attribute")
            
            self.dismiss()
        except ValueError:
            # Show error for invalid input
            print("Invalid weight value entered")
            pass

class ChecklistDialog(Popup):
    """Pre-job confirmation dialog"""
    
    def __init__(self, **kwargs):
        self.job_confirmed = False
        
        super().__init__(**kwargs)
        # Responsive sizing based on screen size
        self.size_hint = (min(0.95, max(0.7, 700 / Window.width)), min(0.9, max(0.6, 600 / Window.height)))
        self.title = "Pre-Job Confirmation"
        self.background = ''  # Remove default background
        self.background_color = THEME['background']  # Theme background color
        self.title_color = THEME['text_primary']  # Theme text color
        self.title_size = sp(18)
        
        # Bind to window resize
        Window.bind(size=self._on_window_resize_checklist)
        
        self._create_content()
    
    def _on_window_resize_checklist(self, instance, value):
        """Handle window resize for responsive sizing"""
        self.size_hint = (min(0.95, max(0.7, 700 / value[0])), min(0.9, max(0.6, 600 / value[1])))
    
    def _create_content(self):
        """Create confirmation content"""
        layout = BoxLayout(orientation='vertical', padding=dp(40), spacing=dp(20))
        
        # Header
        header_label = CustomLabel(
            text="Please confirm the following requirements are fulfilled:",
            bold=True,
            size_hint_y=None,
            height=dp(80),
            color=THEME['text_primary'],
            font_size=sp(20),
            halign='center',
            valign='middle'
        )
        layout.add_widget(header_label)
        
        # Requirements list
        requirements = [
            "• Powder reservoir is attached with correct material",
            "• Scale is connected and stable",
            "• Work area is clean with no obstructions in the machine"
        ]
        
        for requirement in requirements:
            req_label = CustomLabel(
                text=requirement,
                size_hint_y=None,
                height=dp(60),
                color=THEME['text_primary'],
                font_size=sp(18),
                halign='left',
                valign='middle'
            )
            layout.add_widget(req_label)
        
        # Add some spacing
        layout.add_widget(Widget(size_hint_y=1))
        
        # Buttons
        button_layout = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(100),
            spacing=dp(20)
        )
        
        cancel_btn = CustomButton(
            text='Cancel',
            on_press=self.dismiss,
            background_color=THEME['error'],
            color=THEME['text_white'],
            font_size=sp(18)
        )
        button_layout.add_widget(cancel_btn)
        
        confirm_btn = CustomButton(
            text='Confirm & Start Job',
            on_press=self.confirm_job,
            background_color=THEME['secondary'],
            color=THEME['text_white'],
            font_size=sp(18)
        )
        button_layout.add_widget(confirm_btn)
        
        layout.add_widget(button_layout)
        
        # Set the content
        self.content = layout
    
    def confirm_job(self, instance):
        """Confirm the job requirements and start"""
        self.job_confirmed = True
        self.dismiss()
    
    def on_open(self):
        """Called when the dialog opens"""
        super().on_open()
        # Schedule content recreation after the dialog is fully opened
        Clock.schedule_once(self._adjust_sizing, 0.2)
    
    def _adjust_sizing(self, dt):
        """Adjust sizing for different screen sizes"""
        try:
            # Recreate content with updated sizing
            self._create_content()
        except Exception as e:
            print(f"Error adjusting confirmation dialog sizing: {e}")
            import traceback
            traceback.print_exc()
    
    def on_size(self, instance, value):
        """Called when the dialog size changes"""
        # Schedule sizing adjustment when size changes
        Clock.schedule_once(self._adjust_sizing, 0.1)

class ProgressDialog(Popup):
    """Job progress dialog"""
    
    completed_wells = NumericProperty(0)
    total_wells = NumericProperty(1)
    progress_value = NumericProperty(0)
    current_well_text = StringProperty("")
    abort_button_text = StringProperty("ABORT")
    abort_button_color = ObjectProperty(THEME['error'])  # Theme error color
    
    def __init__(self, completed_wells: int, total_wells: int, current_well_text: str, **kwargs):
        super().__init__(**kwargs)
        self.completed_wells = completed_wells
        self.total_wells = total_wells
        self.current_well_text = current_well_text
        # Fullscreen or large dialog based on screen size
        self.size_hint = (min(1.0, max(0.9, 800 / Window.width)), min(1.0, max(0.85, 700 / Window.height)))
        self.title = "Job Progress"
        self.background = ''  # Remove default background
        self.background_color = THEME['background']  # Theme background color
        self.title_color = THEME['text_primary']  # Theme text color
        self.title_size = sp(18)
        
        # Update progress
        self.progress_value = (completed_wells / total_wells) * 100 if total_wells > 0 else 0
        
        # Abort button state
        self.abort_pressed_once = False
        self.abort_timer = None
        
        # Schedule responsive sizing
        Clock.schedule_once(self._adjust_sizing, 0.1)
        
        # Bind to window size changes
        Window.bind(size=self._on_window_resize)
    
    def _adjust_sizing(self, dt):
        """Adjust sizing for smaller screens"""
        try:
            # Get the progress circle widget and container
            if not hasattr(self, 'ids') or 'progress_circle' not in self.ids:
                print("Progress circle not found in ids")
                return
                
            progress_circle = self.ids.progress_circle
            progress_container = self.ids.progress_container
            
            # Calculate available space
            available_width = self.width - dp(80)  # Account for padding
            available_height = self.height - dp(200)  # Account for header, buttons, etc.
            
            # Ensure we have positive dimensions
            if available_width <= 0 or available_height <= 0:
                print(f"Invalid dimensions: width={available_width}, height={available_height}")
                return
            
            # Calculate maximum circle size (use the smaller dimension)
            max_size = min(available_width, available_height, dp(250))
            
            # Ensure minimum size
            max_size = max(max_size, dp(60))
            
            # Update container size to accommodate the circle with some padding
            container_size = max_size + dp(40)  # Add padding around the circle
            progress_container.height = container_size
            
            # Update circle size
            progress_circle.size = (max_size, max_size)
            
            # Find the center text BoxLayout (it should be the first child of the RelativeLayout)
            relative_layout = progress_circle.parent
            if relative_layout and hasattr(relative_layout, 'children') and len(relative_layout.children) > 0:
                center_text = relative_layout.children[0]  # The center text BoxLayout
                if hasattr(center_text, 'children'):
                    # Update center text container size
                    center_text_size = max_size * 0.8
                    center_text.size = (center_text_size, center_text_size)
                    
                    # Update font sizes for children
                    for child in center_text.children:
                        if hasattr(child, 'font_size'):
                            # Scale font sizes proportionally
                            if 'Completed' in child.text:
                                child.font_size = max(sp(16), max_size * 0.08)
                            elif '%' in child.text:
                                child.font_size = max(sp(20), max_size * 0.1)
                            else:  # The main count text
                                child.font_size = max(sp(24), max_size * 0.15)
                
        except Exception as e:
            print(f"Error adjusting progress dialog sizing: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_window_resize(self, instance, value):
        """Handle window resize events"""
        Clock.schedule_once(self._adjust_sizing, 0.1)
    
    def on_open(self):
        """Called when the dialog opens"""
        super().on_open()
        # Adjust sizing after the dialog is fully opened
        Clock.schedule_once(self._adjust_sizing, 0.2)
    
    def on_dismiss(self):
        """Called when the dialog is dismissed"""
        # Unbind from window size changes
        Window.unbind(size=self._on_window_resize)
        super().on_dismiss()
    
    def cancel_job(self):
        """Cancel the job with confirmation"""
        # Show confirmation dialog
        content = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(15))
        content.add_widget(Label(
            text='Are you sure you want to cancel the job?',
            halign='center',
            valign='middle',
            size_hint_y=None,
            height=dp(80),
            font_size=sp(20),
            color=THEME['text_primary']  # Theme text color
        ))
        
        button_layout = BoxLayout(size_hint_y=None, height=dp(100), spacing=dp(20))
        
        cancel_btn = Button(
            text='No, Continue',
            background_color=THEME['primary'],  # Theme primary color
            color=THEME['text_white'],  # Theme white text
            on_press=lambda x: confirm_popup.dismiss(),
            font_size=sp(18)
        )
        button_layout.add_widget(cancel_btn)
        
        confirm_btn = Button(
            text='Yes, Cancel',
            background_color=THEME['warning'],  # Theme warning color
            color=THEME['text_white'],  # Theme white text
            on_press=lambda x: self._confirm_cancel(confirm_popup),
            font_size=sp(18)
        )
        button_layout.add_widget(confirm_btn)
        
        content.add_widget(button_layout)
        
        confirm_popup = Popup(
            title='Confirm Cancel',
            content=content,
            size_hint=(0.6, 0.4),
            background='',  # Remove default background
            background_color=THEME['background'],  # Theme background color
            title_color=THEME['text_primary'],  # Theme text color
            title_size=dp(18)
        )
        confirm_popup.open()
    
    def _confirm_cancel(self, popup):
        """Confirm job cancellation"""
        popup.dismiss()
        # Get main screen and call cancel method with completed count
        try:
            main_screen = App.get_running_app().root.get_screen('main')
            completed_count = self.completed_wells
            main_screen._job_cancelled(completed_count)
        except:
            pass
        self.dismiss()
    
    def abort_job(self):
        """Abort the job (requires double press)"""
        if not self.abort_pressed_once:
            # First press - start timer
            self.abort_pressed_once = True
            self.abort_timer = Clock.schedule_once(self._reset_abort_state, 2.0)  # 2 second window
            
            # Update button text and color using properties
            self.abort_button_text = 'PRESS AGAIN TO ABORT'
            self.abort_button_color = (0.8, 0.2, 0.2, 1)  # Darker red
        else:
            # Second press - abort immediately
            if self.abort_timer:
                self.abort_timer.cancel()
            self._abort_job_hardware()
            # Get main screen and call abort method
            try:
                main_screen = App.get_running_app().root.get_screen('main')
                # Get the current completed count from the progress dialog
                completed_count = self.completed_wells
                # Set flag to prevent auto-close
                main_screen.progress_dialog_being_dismissed = True
                main_screen._job_aborted(completed_count)
            except:
                import traceback
                print("Error calling _job_aborted")
                traceback.print_exc()
            self.dismiss()
    
    def _reset_abort_state(self, dt):
        """Reset abort button state after timeout"""
        self.abort_pressed_once = False
        
        # Reset button text and color using properties
        self.abort_button_text = 'ABORT'
        self.abort_button_color = THEME['error']  # Theme error color
    
    def _cancel_job_hardware(self):
        """Cancel job with hardware control"""
        # Send M25 command to pause/resume the current job
        try:
            main_screen = App.get_running_app().root.get_screen('main')
            if main_screen.jubilee_manager.connected and main_screen.jubilee_manager.machine_read_only:
                main_screen.jubilee_manager.machine_read_only.gcode("M25")  # Pause/resume command
                print("Sent M25 command to pause job")
        except Exception as e:
            print(f"Error sending M25 command: {e}")
        
        # Get main screen and call cancel method with completed count
        try:
            main_screen = App.get_running_app().root.get_screen('main')
            completed_count = self.completed_wells
            main_screen._job_cancelled(completed_count)
        except:
            pass
    
    def _abort_job_hardware(self):
        """Abort job with emergency hardware control"""
        # Send M112 command for emergency stop
        try:
            main_screen = App.get_running_app().root.get_screen('main')
            if main_screen.jubilee_manager.connected and main_screen.jubilee_manager.machine_read_only:
                main_screen.jubilee_manager.machine_read_only.gcode("M112")  # Emergency stop command
                print("Sent M112 emergency stop command")
        except Exception as e:
            print(f"Error sending M112 command: {e}")

class FinishedDialog(Popup):
    """Job finished dialog"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Responsive sizing based on screen size
        self.size_hint = (min(0.8, max(0.5, 500 / Window.width)), min(0.6, max(0.3, 350 / Window.height)))
        self.title = "Job Completed"
        self.background = ''  # Remove default background
        self.background_color = THEME['background']  # Theme background color
        self.title_color = THEME['text_primary']  # Theme text color
        self.title_size = sp(18)
        
        # Bind to window resize
        Window.bind(size=self._on_window_resize_finished)
        
        # Create the dialog content
        self._create_content()
    
    def _on_window_resize_finished(self, instance, value):
        """Handle window resize for responsive sizing"""
        self.size_hint = (min(0.8, max(0.5, 500 / value[0])), min(0.6, max(0.3, 350 / value[1])))
    
    def _create_content(self):
        """Create the dialog content"""
        layout = BoxLayout(orientation='vertical', padding=dp(40), spacing=dp(20))
        
        # Success message
        layout.add_widget(Label(
            text='Job Completed Successfully!',
            size_hint_y=None,
            height=dp(80),
            halign='center',
            valign='middle',
            font_size=sp(32),
            color=THEME['secondary'],  # Green color
            bold=True
        ))
        
        layout.add_widget(Label(
            text='All wells have been filled successfully.',
            size_hint_y=None,
            height=dp(60),
            halign='center',
            valign='middle',
            font_size=sp(24),
            color=THEME['text_primary']  # Theme text color
        ))
        
        # OK button
        ok_btn = Button(
            text='OK',
            background_color=THEME['secondary'],  # Theme secondary color
            color=THEME['text_white'],  # Theme white text
            on_press=self.dismiss,
            font_size=sp(18),
            size_hint_y=None,
            height=dp(80)
        )
        layout.add_widget(ok_btn)
        
        # Set the content
        self.content = layout

class CancelledDialog(Popup):
    """Job cancelled dialog"""
    
    def __init__(self, completed_count: int, total_count: int, **kwargs):
        self.completed_count = completed_count
        self.total_count = total_count
        super().__init__(**kwargs)
        # Responsive sizing based on screen size
        self.size_hint = (min(0.85, max(0.6, 600 / Window.width)), min(0.7, max(0.4, 450 / Window.height)))
        self.title = "Job Cancelled"
        self.background = ''  # Remove default background
        self.background_color = THEME['background']  # Theme background color
        self.title_color = THEME['text_primary']  # Theme text color
        self.title_size = sp(18)
        
        # Bind to window resize
        Window.bind(size=self._on_window_resize_cancelled)
        
        # Create the dialog content
        self._create_content()
    
    def _on_window_resize_cancelled(self, instance, value):
        """Handle window resize for responsive sizing"""
        self.size_hint = (min(0.85, max(0.6, 600 / value[0])), min(0.7, max(0.4, 450 / value[1])))
    
    def _create_content(self):
        """Create the dialog content"""
        layout = BoxLayout(orientation='vertical', padding=dp(40), spacing=dp(20))
        
        # Cancelled message
        layout.add_widget(Label(
            text='Job Cancelled',
            size_hint_y=None,
            height=dp(80),
            halign='center',
            valign='middle',
            font_size=sp(32),
            color=THEME['warning'],  # Orange color
            bold=True
        ))
        
        # Progress info
        layout.add_widget(Label(
            text=f'Completed {self.completed_count} of {self.total_count} wells before cancellation.',
            size_hint_y=None,
            height=dp(60),
            halign='center',
            valign='middle',
            font_size=sp(20),
            color=THEME['text_primary']  # Theme text color
        ))
        
        layout.add_widget(Label(
            text='Only completed wells have been filled with powder.',
            size_hint_y=None,
            height=dp(60),
            halign='center',
            valign='middle',
            font_size=sp(18),
            color=THEME['text_secondary']  # Theme secondary text color
        ))
        
        # OK button
        ok_btn = Button(
            text='OK',
            background_color=THEME['warning'],  # Theme warning color
            color=THEME['text_white'],  # Theme white text
            on_press=self.dismiss,
            font_size=sp(18),
            size_hint_y=None,
            height=dp(80)
        )
        layout.add_widget(ok_btn)
        
        # Set the content
        self.content = layout

class AbortedDialog(Popup):
    """Job aborted dialog"""
    
    def __init__(self, completed_count: int, total_count: int, **kwargs):
        self.completed_count = completed_count
        self.total_count = total_count
        super().__init__(**kwargs)
        # Responsive sizing based on screen size
        self.size_hint = (min(0.95, max(0.7, 700 / Window.width)), min(0.9, max(0.7, 650 / Window.height)))
        self.title = "Job Aborted"
        self.background = ''  # Remove default background
        self.background_color = THEME['background']  # Theme background color
        self.title_color = THEME['text_primary']  # Theme text color
        self.title_size = sp(18)
        
        # Bind to window resize
        Window.bind(size=self._on_window_resize_aborted)
        
        # Create the dialog content
        self._create_content()
    
    def _on_window_resize_aborted(self, instance, value):
        """Handle window resize for responsive sizing"""
        self.size_hint = (min(0.95, max(0.7, 700 / value[0])), min(0.9, max(0.7, 650 / value[1])))
    
    def _create_content(self):
        """Create the dialog content"""
        layout = BoxLayout(orientation='vertical', padding=dp(40), spacing=dp(20))
        
        # Aborted message
        layout.add_widget(Label(
            text='Job Aborted',
            size_hint_y=None,
            height=dp(80),
            halign='center',
            valign='middle',
            font_size=sp(32),
            color=THEME['error'],  # Red color
            bold=True
        ))
        
        # Progress info
        layout.add_widget(Label(
            text=f'Completed {self.completed_count} of {self.total_count} wells before abort.',
            size_hint_y=None,
            height=dp(60),
            halign='center',
            valign='middle',
            font_size=sp(20),
            color=THEME['text_primary']  # Theme text color
        ))
        
        layout.add_widget(Label(
            text='Only completed wells have been filled with powder.',
            size_hint_y=None,
            height=dp(60),
            halign='center',
            valign='middle',
            font_size=sp(18),
            color=THEME['text_secondary']  # Theme secondary text color
        ))
        
        # Important warning
        warning_layout = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(180))
        
        with warning_layout.canvas.before:
            Color(rgba=THEME['error'])
            Rectangle(pos=warning_layout.pos, size=warning_layout.size)
        
        warning_layout.add_widget(Label(
            text='IMPORTANT:',
            size_hint_y=None,
            height=dp(40),
            halign='center',
            valign='middle',
            font_size=sp(24),
            color=THEME['text_white'],  # White text on red background
            bold=True
        ))
        
        warning_layout.add_widget(Label(
            text='The toolhead must be manually returned to the tool rack before the Jubilee is restarted.',
            size_hint_y=None,
            height=dp(60),
            halign='center',
            valign='middle',
            font_size=sp(18),
            color=THEME['text_white'],  # White text on red background
        ))
        
        warning_layout.add_widget(Label(
            text='The power on the Jubilee must be cycled (turned off and on) before restarting.',
            size_hint_y=None,
            height=dp(60),
            halign='center',
            valign='middle',
            font_size=sp(18),
            color=THEME['text_white'],  # White text on red background
        ))
        
        layout.add_widget(warning_layout)
        
        # OK button
        ok_btn = Button(
            text='OK',
            background_color=THEME['error'],  # Theme error color
            color=THEME['text_white'],  # Theme white text
            on_press=self.dismiss,
            font_size=sp(18),
            size_hint_y=None,
            height=dp(80)
        )
        layout.add_widget(ok_btn)
        
        # Set the content
        self.content = layout

class ShutdownDialog(Popup):
    """Shutdown confirmation dialog"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Responsive sizing based on screen size
        self.size_hint = (min(0.8, max(0.5, 550 / Window.width)), min(0.6, max(0.35, 400 / Window.height)))
        self.title = "Confirm Shutdown"
        self.background = ''  # Remove default background
        self.background_color = THEME['background']  # Theme background color
        self.title_color = THEME['text_primary']  # Theme text color
        self.title_size = sp(18)
        self.confirmed = False
        
        # Bind to window resize
        Window.bind(size=self._on_window_resize_shutdown)
        
        # Create the dialog content
        self._create_content()
    
    def _on_window_resize_shutdown(self, instance, value):
        """Handle window resize for responsive sizing"""
        self.size_hint = (min(0.8, max(0.5, 550 / value[0])), min(0.6, max(0.35, 400 / value[1])))
    
    def _create_content(self):
        """Create the dialog content"""
        layout = BoxLayout(orientation='vertical', padding=dp(40), spacing=dp(20))
        
        # Warning message
        layout.add_widget(Label(
            text='Are you sure you want to shutdown?',
            size_hint_y=None,
            height=dp(80),
            halign='center',
            valign='middle',
            font_size=sp(32),
            color=THEME['text_primary']  # Theme text color
        ))
        
        layout.add_widget(Label(
            text='This will:\n• Stop any running job\n• Stow tools and return to home\n• Disconnect all components\n• Close the application',
            size_hint_y=None,
            height=dp(120),
            halign='center',
            valign='middle',
            font_size=sp(24),
            color=THEME['text_primary']  # Theme text color
        ))
        
        # Buttons
        button_layout = BoxLayout(size_hint_y=None, height=dp(100), spacing=dp(20))
        
        cancel_btn = Button(
            text='Cancel',
            background_color=THEME['primary'],  # Theme primary color
            color=THEME['text_white'],  # Theme white text
            on_press=self.dismiss,
            font_size=sp(18)
        )
        button_layout.add_widget(cancel_btn)
        
        shutdown_btn = Button(
            text='Shutdown',
            background_color=THEME['error'],  # Theme error color
            color=THEME['text_white'],  # Theme white text
            on_press=self.confirm_shutdown,
            font_size=sp(18)
        )
        button_layout.add_widget(shutdown_btn)
        
        layout.add_widget(button_layout)
        
        # Set the content
        self.content = layout
    
    def confirm_shutdown(self, instance):
        """Confirm the shutdown"""
        self.confirmed = True
        self.dismiss()

class ErrorDialog(Popup):
    """Error dialog"""
    
    error_message = StringProperty("")
    
    def __init__(self, error_message: str, **kwargs):
        super().__init__(**kwargs)
        self.error_message = error_message
        # Responsive sizing based on screen size
        self.size_hint = (min(0.9, max(0.7, 650 / Window.width)), min(0.75, max(0.5, 500 / Window.height)))
        self.title = "Error"
        self.background = ''  # Remove default background
        self.background_color = THEME['background']  # Theme background color
        self.title_color = THEME['text_primary']  # Theme text color
        self.title_size = sp(18)
        
        # Bind to window resize
        Window.bind(size=self._on_window_resize_error)
    
    def _on_window_resize_error(self, instance, value):
        """Handle window resize for responsive sizing"""
        self.size_hint = (min(0.9, max(0.7, 650 / value[0])), min(0.75, max(0.5, 500 / value[1])))

class TextInputDialog(Popup):
    """Example dialog with text input that shows virtual keyboard"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Responsive sizing based on screen size
        self.size_hint = (min(0.9, max(0.7, 650 / Window.width)), min(0.75, max(0.5, 500 / Window.height)))
        self.title = "Enter Text"
        self.background = ''  # Remove default background
        self.background_color = THEME['background']  # Theme background color
        self.title_color = THEME['text_primary']  # Theme text color
        self.title_size = sp(18)
        
        # Bind to window resize
        Window.bind(size=self._on_window_resize_textinput)
        
        # Create the dialog content
        self._create_content()
    
    def _on_window_resize_textinput(self, instance, value):
        """Handle window resize for responsive sizing"""
        self.size_hint = (min(0.9, max(0.7, 650 / value[0])), min(0.75, max(0.5, 500 / value[1])))
    
    def _create_content(self):
        """Create the dialog content"""
        layout = BoxLayout(orientation='vertical', padding=dp(40), spacing=dp(20))
        
        # Instructions
        layout.add_widget(Label(
            text='Enter some text below.\nThe virtual keyboard will appear automatically.',
            size_hint_y=None,
            height=dp(80),
            halign='center',
            valign='middle',
            font_size=sp(18),
            color=THEME['text_primary']  # Theme text color
        ))
        
        # Text input
        self.text_input = CustomTextInput(
            text='',
            hint_text='Type here...',
            size_hint_y=None,
            height=dp(60)
        )
        layout.add_widget(self.text_input)
        
        # Buttons
        button_layout = BoxLayout(size_hint_y=None, height=dp(100), spacing=dp(20))
        
        cancel_btn = Button(
            text='Cancel',
            background_color=THEME['primary'],  # Theme primary color
            color=THEME['text_white'],  # Theme white text
            on_press=self.dismiss,
            font_size=sp(18)
        )
        button_layout.add_widget(cancel_btn)
        
        ok_btn = Button(
            text='OK',
            background_color=THEME['secondary'],  # Theme secondary color
            color=THEME['text_white'],  # Theme white text
            on_press=self._on_ok,
            font_size=sp(18)
        )
        button_layout.add_widget(ok_btn)
        
        layout.add_widget(button_layout)
        
        # Set the content
        self.content = layout
    
    def _on_ok(self, instance):
        """Handle OK button press"""
        print(f"Entered text: {self.text_input.text}")
        self.dismiss()

class JubileeGUIApp(App):
    """Main Jubilee GUI application"""
    
    def build(self):
        """Build the application"""
        # Set fullscreen mode
        Window.fullscreen = 'auto'
        
        # Create screen manager
        sm = ScreenManager()
        sm.add_widget(MainScreen(name='main'))
        return sm
    
    def on_start(self):
        """Called when the app starts"""
        # Ensure fullscreen mode is set
        Window.fullscreen = 'auto'
        
        # Bind keyboard events
        Window.bind(on_keyboard=self.on_keyboard)
        
        # Hide keyboard on startup
        keyboard_manager.hide_keyboard()
        print("Jubilee GUI started - keyboard hidden")
    
    def on_keyboard(self, window, key, scancode, codepoint, modifier):
        """Handle keyboard events"""
        # F11 to toggle fullscreen
        if key == 290:  # F11 key
            if Window.fullscreen:
                Window.fullscreen = False
            else:
                Window.fullscreen = 'auto'
            return True
        # Escape to exit fullscreen and hide keyboard
        elif key == 27:  # Escape key
            Window.fullscreen = False
            keyboard_manager.hide_keyboard()
            return True
        return False
    
    def on_stop(self):
        """Clean up when app stops"""
        # Ensure keyboard is hidden when app closes
        keyboard_manager.hide_keyboard()
        
        # Disconnect from Jubilee system
        main_screen = self.root.get_screen('main')
        if hasattr(main_screen, 'jubilee_manager'):
            main_screen.jubilee_manager.disconnect()
        
        print("Jubilee GUI stopped - keyboard hidden")
    
    def on_pause(self):
        """Called when the application is paused (e.g., minimized)"""
        # Hide keyboard when app is paused
        keyboard_manager.hide_keyboard()
        return True
    
    def on_resume(self):
        """Called when the application resumes"""
        # Keyboard will be shown automatically when TextInput gains focus
        pass

if __name__ == '__main__':
    JubileeGUIApp().run() 