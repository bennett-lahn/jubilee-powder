"""
Jubilee Powder Dispensing GUI Application.

This module provides a touchscreen-friendly GUI for the Jubilee powder dispensing
system. Built with Kivy, it follows an MVVM architecture where this module serves
as the View layer.

The GUI provides:
    - Visual well selection (3x3 grid)
    - Target weight configuration
    - Real-time progress monitoring
    - Hardware configuration interface
    - Safety checklist before jobs
    - Live scale weight display

Architecture:
    The GUI communicates with hardware through JubileeViewModel, which coordinates
    operations with JubileeManager. This ensures clean separation between UI,
    coordination logic, and hardware operations.

Usage:
    Run the GUI application::
    
        python gui/jubilee_gui.py

Components:
    - MainScreen: Primary screen with well grid and controls
    - HardwareConfigDialog: Configure dispensers and pistons
    - WeightDialog: Set target weights for selected wells
    - ChecklistDialog: Pre-job safety checklist
    - ProgressDialog: Real-time job progress display
    - FinishedDialog: Job completion notification
    - ErrorDialog: Error message display
"""

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
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import ObjectProperty, StringProperty, NumericProperty, BooleanProperty
from kivy.lang import Builder
import threading
import time
import json
from typing import List, Dict, Optional
from dataclasses import dataclass

# Import Jubilee components
from jubilee_view_model import JubileeViewModel, DispensingJob

# Configure Kivy for touch interface
Window.softinput_mode = 'below_target'
kivy.require('2.0.0')

# KV Language string for custom styling
KV = '''
#:import utils kivy.utils

<CustomButton@Button>:
    background_color: utils.get_color_from_hex('#2196F3')
    background_normal: ''
    color: 1, 1, 1, 1
    size_hint_y: None
    height: dp(60)
    font_size: dp(18)
    canvas.before:
        Color:
            rgba: utils.get_color_from_hex('#1976D2') if self.state == 'down' else utils.get_color_from_hex('#2196F3')
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(8)]

<CustomLabel@Label>:
    color: utils.get_color_from_hex('#212121')
    font_size: dp(16)
    size_hint_y: None
    height: dp(40)

<WeightWellButton@Button>:
    background_color: utils.get_color_from_hex('#4CAF50') if self.selected else utils.get_color_from_hex('#E0E0E0')
    background_normal: ''
    color: 1, 1, 1, 1 if self.selected else 0, 0, 0, 1
    size_hint: None, None
    size: dp(80), dp(80)
    font_size: dp(12)
    canvas.before:
        Color:
            rgba: self.background_color
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(8)]

<MainScreen>:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(20)
        spacing: dp(10)
        
        # Header
        BoxLayout:
            size_hint_y: None
            height: dp(60)
            CustomLabel:
                text: 'Jubilee Powder Dispensing System'
                font_size: dp(24)
                bold: True
                halign: 'center'
        
        # Platform visualization
        BoxLayout:
            orientation: 'horizontal'
            size_hint_y: 0.6
            
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
                            rgba: utils.get_color_from_hex('#FF9800')
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [dp(8)]
                    
                    CustomLabel:
                        text: 'Connected' if root.scale_connected else 'Disconnected'
                        halign: 'center'
                        color: 1, 1, 1, 1
                    
                    CustomLabel:
                        text: f'{root.current_weight:.3f}g'
                        halign: 'center'
                        color: 1, 1, 1, 1
                        font_size: dp(20)
                        bold: True
            
            # Center - Platform
            BoxLayout:
                orientation: 'vertical'
                size_hint_x: 0.6
                padding: dp(10)
                
                CustomLabel:
                    text: 'Jubilee Platform'
                    halign: 'center'
                    bold: True
                
                GridLayout:
                    cols: 3
                    spacing: dp(5)
                    padding: dp(10)
                    canvas.before:
                        Color:
                            rgba: utils.get_color_from_hex('#F5F5F5')
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [dp(8)]
                    
                    WeightWellButton:
                        text: '0\\n0.0g'
                        well_id: '0'
                        selected: root.is_well_selected('0')
                        on_press: root.toggle_well('0')
                    
                    WeightWellButton:
                        text: '1\\n0.0g'
                        well_id: '1'
                        selected: root.is_well_selected('1')
                        on_press: root.toggle_well('1')
                    
                    WeightWellButton:
                        text: '2\\n0.0g'
                        well_id: '2'
                        selected: root.is_well_selected('2')
                        on_press: root.toggle_well('2')
                    
                    WeightWellButton:
                        text: '3\\n0.0g'
                        well_id: '3'
                        selected: root.is_well_selected('3')
                        on_press: root.toggle_well('3')
                    
                    WeightWellButton:
                        text: '4\\n0.0g'
                        well_id: '4'
                        selected: root.is_well_selected('4')
                        on_press: root.toggle_well('4')
                    
                    WeightWellButton:
                        text: '5\\n0.0g'
                        well_id: '5'
                        selected: root.is_well_selected('5')
                        on_press: root.toggle_well('5')
                    
                    WeightWellButton:
                        text: '6\\n0.0g'
                        well_id: '6'
                        selected: root.is_well_selected('6')
                        on_press: root.toggle_well('6')
                    
                    WeightWellButton:
                        text: '7\\n0.0g'
                        well_id: '7'
                        selected: root.is_well_selected('7')
                        on_press: root.toggle_well('7')
                    
                    WeightWellButton:
                        text: '8\\n0.0g'
                        well_id: '8'
                        selected: root.is_well_selected('8')
                        on_press: root.toggle_well('8')
            
            # Right side - Controls
            BoxLayout:
                orientation: 'vertical'
                size_hint_x: 0.2
                padding: dp(10)
                spacing: dp(10)
                
                CustomLabel:
                    text: 'Controls'
                    halign: 'center'
                    bold: True
                
                CustomButton:
                    text: 'Hardware Config'
                    on_press: root.show_hardware_config_dialog()
                    disabled: root.scale_connected
                
                CustomButton:
                    text: 'Set Weights'
                    on_press: root.show_weight_dialog()
                
                CustomButton:
                    text: 'Start Job'
                    on_press: root.start_job()
                    disabled: not root.can_start_job()
                
                CustomButton:
                    text: 'Stop Job'
                    on_press: root.stop_job()
                    disabled: not root.job_running
        
        # Status bar
        BoxLayout:
            size_hint_y: None
            height: dp(40)
            canvas.before:
                Color:
                    rgba: utils.get_color_from_hex('#E0E0E0')
                Rectangle:
                    pos: self.pos
                    size: self.size
            
            CustomLabel:
                text: root.status_text
                halign: 'left'
                valign: 'middle'
                text_size: self.size

<WeightDialog>:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(20)
        spacing: dp(10)
        
        CustomLabel:
            text: 'Set Target Weights'
            font_size: dp(20)
            bold: True
            halign: 'center'
        
        ScrollView:
            GridLayout:
                cols: 2
                spacing: dp(10)
                size_hint_y: None
                height: self.minimum_height
                
                CustomLabel:
                    text: 'Well'
                    bold: True
                
                CustomLabel:
                    text: 'Target Weight (g)'
                    bold: True
                
                # Dynamic weight inputs will be added here
                id: weight_inputs
        
        BoxLayout:
            size_hint_y: None
            height: dp(60)
            spacing: dp(10)
            
            CustomButton:
                text: 'Cancel'
                on_press: root.dismiss()
                background_color: utils.get_color_from_hex('#F44336')
            
            CustomButton:
                text: 'Apply'
                on_press: root.apply_weights()

<ChecklistDialog>:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(20)
        spacing: dp(10)
        
        CustomLabel:
            text: 'Pre-Job Checklist'
            font_size: dp(20)
            bold: True
            halign: 'center'
        
        ScrollView:
            GridLayout:
                cols: 2
                spacing: dp(10)
                size_hint_y: None
                height: self.minimum_height
                
                CustomLabel:
                    text: 'Check Item'
                    bold: True
                
                CustomLabel:
                    text: 'Status'
                    bold: True
                
                # Dynamic checklist items will be added here
                id: checklist_items
        
        BoxLayout:
            size_hint_y: None
            height: dp(60)
            spacing: dp(10)
            
            CustomButton:
                text: 'Cancel'
                on_press: root.dismiss()
                background_color: utils.get_color_from_hex('#F44336')
            
            CustomButton:
                text: 'Start Job'
                on_press: root.start_job()
                disabled: not root.all_checked()

<ProgressDialog>:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(20)
        spacing: dp(10)
        
        CustomLabel:
            text: 'Job Progress'
            font_size: dp(20)
            bold: True
            halign: 'center'
        
        CustomLabel:
            text: f'Completed: {root.completed_wells}/{root.total_wells}'
            halign: 'center'
            font_size: dp(18)
        
        ProgressBar:
            value: root.progress_value
            max: 100
            size_hint_y: None
            height: dp(30)
        
        CustomLabel:
            text: root.current_well_text
            halign: 'center'
        
        CustomButton:
            text: 'Stop Job'
            on_press: root.stop_job()
            background_color: utils.get_color_from_hex('#F44336')

<FinishedDialog>:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(20)
        spacing: dp(10)
        
        CustomLabel:
            text: 'Job Completed!'
            font_size: dp(24)
            bold: True
            halign: 'center'
            color: utils.get_color_from_hex('#4CAF50')
        
        CustomLabel:
            text: 'All wells have been filled successfully.'
            halign: 'center'
        
        CustomButton:
            text: 'OK'
            on_press: root.dismiss()
            background_color: utils.get_color_from_hex('#4CAF50')

<ErrorDialog>:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(20)
        spacing: dp(10)
        
        CustomLabel:
            text: 'Error'
            font_size: dp(20)
            bold: True
            halign: 'center'
            color: utils.get_color_from_hex('#F44336')
        
        ScrollView:
            CustomLabel:
                text: root.error_message
                halign: 'center'
                text_size: self.size
        
        CustomButton:
            text: 'OK'
            on_press: root.dismiss()
            background_color: utils.get_color_from_hex('#F44336')

<HardwareConfigDialog>:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(20)
        spacing: dp(10)
        
        CustomLabel:
            text: 'Hardware Configuration'
            font_size: dp(20)
            bold: True
            halign: 'center'
        
        CustomLabel:
            text: 'Configure hardware before connecting'
            halign: 'center'
            font_size: dp(14)
        
        GridLayout:
            cols: 2
            spacing: dp(10)
            size_hint_y: None
            height: dp(200)
            
            CustomLabel:
                text: 'Number of Dispensers:'
                halign: 'right'
            
            TextInput:
                id: num_dispensers_input
                text: str(root.num_dispensers)
                multiline: False
                input_filter: 'int'
                size_hint_y: None
                height: dp(40)
            
            CustomLabel:
                text: 'Pistons per Dispenser:'
                halign: 'right'
            
            TextInput:
                id: pistons_per_dispenser_input
                text: str(root.pistons_per_dispenser)
                multiline: False
                input_filter: 'int'
                size_hint_y: None
                height: dp(40)
            
            CustomLabel:
                text: 'Total Pistons:'
                halign: 'right'
                bold: True
            
            CustomLabel:
                text: str(root.total_pistons)
                halign: 'left'
                bold: True
                color: utils.get_color_from_hex('#4CAF50')
        
        BoxLayout:
            size_hint_y: None
            height: dp(60)
            spacing: dp(10)
            
            CustomButton:
                text: 'Cancel'
                on_press: root.dismiss()
                background_color: utils.get_color_from_hex('#F44336')
            
            CustomButton:
                text: 'Apply'
                on_press: root.apply_config()
'''

Builder.load_string(KV)




class MainScreen(Screen):
    """Main screen of the Jubilee GUI application"""
    
    # Properties
    status_text = StringProperty("Ready")
    current_weight = NumericProperty(0.0)
    scale_connected = BooleanProperty(False)
    job_running = BooleanProperty(False)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Create ViewModel with callbacks
        self.view_model = JubileeViewModel(
            on_connection_changed=self._on_connection_changed,
            on_weight_changed=self._on_weight_changed,
            on_status_changed=self._on_status_changed,
            on_job_progress=self._on_job_progress,
            on_job_completed=self._on_job_completed,
            on_error=self._on_error
        )
        
        self.selected_wells = set()
        self.well_weights = {}  # well_id -> target_weight
        self.current_progress_dialog = None
        
        # Try to connect
        self.connect_to_system()
    
    def connect_to_system(self):
        """Connect to Jubilee system"""
        self.status_text = "Connecting..."
        threading.Thread(target=self._connect_thread, daemon=True).start()
    
    def _connect_thread(self):
        """Connection thread to avoid blocking UI"""
        success = self.view_model.connect()
        # Callbacks will update UI state
    
    # ViewModel callback methods
    def _on_connection_changed(self, connected: bool):
        """Called when connection state changes"""
        def update(dt):
            self.scale_connected = connected
        Clock.schedule_once(update, 0)
    
    def _on_weight_changed(self, weight: float):
        """Called when weight changes"""
        def update(dt):
            self.current_weight = weight
        Clock.schedule_once(update, 0)
    
    def _on_status_changed(self, status: str):
        """Called when status message changes"""
        def update(dt):
            self.status_text = status
        Clock.schedule_once(update, 0)
    
    def _on_job_progress(self, completed: int, total: int, current_well: str):
        """Called when job progress updates"""
        def update(dt):
            # Update progress dialog if open
            if self.current_progress_dialog:
                self.current_progress_dialog.completed_wells = completed
                self.current_progress_dialog.total_wells = total
                self.current_progress_dialog.current_well_text = f"Processing {current_well}"
                self.current_progress_dialog.progress_value = (completed / total * 100) if total > 0 else 0
        Clock.schedule_once(update, 0)
    
    def _on_job_completed(self):
        """Called when job completes successfully"""
        def update(dt):
            self.job_running = False
            if self.current_progress_dialog:
                self.current_progress_dialog.dismiss()
                self.current_progress_dialog = None
            self.show_finished_dialog()
        Clock.schedule_once(update, 0)
    
    def _on_error(self, error_message: str):
        """Called when an error occurs"""
        def update(dt):
            self.show_error(error_message)
        Clock.schedule_once(update, 0)
    
    def toggle_well(self, well_id: str):
        """Toggle selection of a well"""
        if well_id in self.selected_wells:
            self.selected_wells.remove(well_id)
        else:
            self.selected_wells.add(well_id)
    
    def is_well_selected(self, well_id: str) -> bool:
        """Check if a well is selected"""
        return well_id in self.selected_wells
    
    def can_start_job(self) -> bool:
        """Check if job can be started"""
        return len(self.selected_wells) > 0 and not self.job_running
    
    def show_hardware_config_dialog(self):
        """Show hardware configuration dialog"""
        if self.view_model.connected:
            self.show_error("Cannot change hardware config while connected. Disconnect first.")
            return
        
        dialog = HardwareConfigDialog(self.view_model)
        dialog.open()
    
    def show_weight_dialog(self):
        """Show weight setting dialog"""
        if not self.selected_wells:
            self.show_error("Please select at least one well first.")
            return
        
        dialog = WeightDialog(self.selected_wells, self.well_weights)
        dialog.open()
    
    def start_job(self):
        """Start the dispensing job"""
        if not self.can_start_job():
            return
        
        # Show checklist first
        checklist = ChecklistDialog()
        checklist.bind(on_dismiss=self._on_checklist_dismiss)
        checklist.open()
    
    def _on_checklist_dismiss(self, instance):
        """Handle checklist dismissal"""
        if hasattr(instance, 'job_confirmed') and instance.job_confirmed:
            self._start_job_execution()
    
    def _start_job_execution(self):
        """Start the actual job execution"""
        self.job_running = True
        
        # Create job list from selected wells
        jobs = [
            DispensingJob(well_id=well_id, target_weight=self.well_weights.get(well_id, 0.0))
            for well_id in sorted(self.selected_wells)
        ]
        
        # Start job through ViewModel
        success = self.view_model.start_job(jobs)
        
        if success:
            # Show progress dialog
            self.show_progress_dialog()
        else:
            self.job_running = False
    
    def stop_job(self):
        """Stop the current job"""
        self.view_model.stop_job()
        self.job_running = False
    
    def show_error(self, message: str):
        """Show error dialog"""
        dialog = ErrorDialog(error_message=message)
        dialog.open()
    
    def show_progress_dialog(self):
        """Show progress dialog"""
        num_wells = len(self.selected_wells)
        self.current_progress_dialog = ProgressDialog(
            completed_wells=0,
            total_wells=num_wells,
            current_well_text="Starting...",
            view_model=self.view_model
        )
        self.current_progress_dialog.bind(on_dismiss=self._on_progress_dismiss)
        self.current_progress_dialog.open()
    
    def _on_progress_dismiss(self, instance):
        """Handle progress dialog dismissal"""
        self.stop_job()
        self.current_progress_dialog = None
    
    def show_finished_dialog(self):
        """Show job finished dialog"""
        dialog = FinishedDialog()
        dialog.open()

class WeightDialog(Popup):
    """Dialog for setting target weights"""
    
    def __init__(self, selected_wells: set, current_weights: dict, **kwargs):
        super().__init__(**kwargs)
        self.selected_wells = selected_wells
        self.current_weights = current_weights
        self.size_hint = (0.8, 0.8)
        self.title = "Set Target Weights"
        
        # Create weight inputs
        self._create_weight_inputs()
    
    def _create_weight_inputs(self):
        """Create weight input fields"""
        grid = self.ids.weight_inputs
        grid.clear_widgets()
        
        # Add header
        grid.add_widget(Label(text="Well", bold=True, size_hint_y=None, height=dp(40)))
        grid.add_widget(Label(text="Target Weight (g)", bold=True, size_hint_y=None, height=dp(40)))
        
        # Add inputs for each selected well
        for well_id in sorted(self.selected_wells):
            grid.add_widget(Label(text=well_id, size_hint_y=None, height=dp(40)))
            
            text_input = TextInput(
                text=str(self.current_weights.get(well_id, 0.0)),
                multiline=False,
                size_hint_y=None,
                height=dp(40),
                input_filter='float'
            )
            text_input.well_id = well_id
            grid.add_widget(text_input)
    
    def apply_weights(self):
        """Apply the entered weights"""
        grid = self.ids.weight_inputs
        new_weights = {}
        
        for child in grid.children:
            if isinstance(child, TextInput) and hasattr(child, 'well_id'):
                try:
                    weight = float(child.text)
                    new_weights[child.well_id] = weight
                except ValueError:
                    pass
        
        # Update main screen weights
        main_screen = self.parent.parent
        if hasattr(main_screen, 'well_weights'):
            main_screen.well_weights.update(new_weights)
        
        self.dismiss()

class ChecklistDialog(Popup):
    """Pre-job checklist dialog"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (0.8, 0.8)
        self.title = "Pre-Job Checklist"
        self.job_confirmed = False
        
        self._create_checklist()
    
    def _create_checklist(self):
        """Create checklist items"""
        grid = self.ids.checklist_items
        grid.clear_widgets()
        
        # Add header
        grid.add_widget(Label(text="Check Item", bold=True, size_hint_y=None, height=dp(40)))
        grid.add_widget(Label(text="Status", bold=True, size_hint_y=None, height=dp(40)))
        
        # Checklist items
        checklist_items = [
            "Scale is connected and stable",
            "Trickler tool is loaded and calibrated",
            "Powder container is filled",
            "All target wells are clean and ready",
            "Emergency stop is accessible",
            "Work area is clear of obstructions"
        ]
        
        self.checkboxes = []
        for item in checklist_items:
            grid.add_widget(Label(text=item, size_hint_y=None, height=dp(40)))
            
            checkbox = CheckBox(size_hint_y=None, height=dp(40))
            self.checkboxes.append(checkbox)
            grid.add_widget(checkbox)
    
    def all_checked(self) -> bool:
        """Check if all items are checked"""
        return all(checkbox.active for checkbox in self.checkboxes)
    
    def start_job(self):
        """Start the job if all items are checked"""
        if self.all_checked():
            self.job_confirmed = True
            self.dismiss()
        else:
            # Show error or highlight unchecked items
            pass

class ProgressDialog(Popup):
    """Job progress dialog"""
    
    completed_wells = NumericProperty(0)
    total_wells = NumericProperty(1)
    progress_value = NumericProperty(0)
    current_well_text = StringProperty("")
    
    def __init__(self, completed_wells: int, total_wells: int, current_well_text: str, view_model: JubileeViewModel, **kwargs):
        super().__init__(**kwargs)
        self.completed_wells = completed_wells
        self.total_wells = total_wells
        self.current_well_text = current_well_text
        self.view_model = view_model
        self.size_hint = (0.8, 0.6)
        self.title = "Job Progress"
        
        # Update progress
        self.progress_value = (completed_wells / total_wells) * 100 if total_wells > 0 else 0
    
    def stop_job(self):
        """Stop the current job"""
        self.view_model.stop_job()
        self.dismiss()

class FinishedDialog(Popup):
    """Job finished dialog"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (0.6, 0.4)
        self.title = "Job Completed"

class HardwareConfigDialog(Popup):
    """Hardware configuration dialog"""
    
    num_dispensers = NumericProperty(2)
    pistons_per_dispenser = NumericProperty(10)
    total_pistons = NumericProperty(20)
    
    def __init__(self, view_model: JubileeViewModel, **kwargs):
        super().__init__(**kwargs)
        self.view_model = view_model
        self.num_dispensers = view_model.num_dispensers
        self.pistons_per_dispenser = view_model.pistons_per_dispenser
        self.total_pistons = self.num_dispensers * self.pistons_per_dispenser
        self.size_hint = (0.7, 0.6)
        self.title = "Hardware Configuration"
        
        # Bind to update total when inputs change
        Clock.schedule_once(self._setup_bindings, 0.1)
    
    def _setup_bindings(self, dt):
        """Setup input field bindings"""
        if hasattr(self.ids, 'num_dispensers_input'):
            self.ids.num_dispensers_input.bind(text=self._update_total)
        if hasattr(self.ids, 'pistons_per_dispenser_input'):
            self.ids.pistons_per_dispenser_input.bind(text=self._update_total)
    
    def _update_total(self, instance, value):
        """Update total pistons calculation"""
        try:
            num_disp = int(self.ids.num_dispensers_input.text or 0)
            pistons_per = int(self.ids.pistons_per_dispenser_input.text or 0)
            self.total_pistons = num_disp * pistons_per
        except (ValueError, AttributeError):
            self.total_pistons = 0
    
    def apply_config(self):
        """Apply hardware configuration"""
        try:
            num_disp = int(self.ids.num_dispensers_input.text)
            pistons_per = int(self.ids.pistons_per_dispenser_input.text)
            
            if num_disp <= 0 or pistons_per <= 0:
                # Show error
                return
            
            # Update ViewModel configuration
            self.view_model.set_hardware_config(num_disp, pistons_per)
            self.dismiss()
            
        except ValueError:
            # Show error for invalid input
            pass

class ErrorDialog(Popup):
    """Error dialog"""
    
    error_message = StringProperty("")
    
    def __init__(self, error_message: str, **kwargs):
        super().__init__(**kwargs)
        self.error_message = error_message
        self.size_hint = (0.8, 0.6)
        self.title = "Error"

class JubileeGUIApp(App):
    """Main Jubilee GUI application"""
    
    def build(self):
        """Build the application"""
        # Create screen manager
        sm = ScreenManager()
        sm.add_widget(MainScreen(name='main'))
        return sm
    
    def on_stop(self):
        """Clean up when app stops"""
        # Disconnect from Jubilee system
        main_screen = self.root.get_screen('main')
        if hasattr(main_screen, 'view_model'):
            main_screen.view_model.disconnect()

if __name__ == '__main__':
    JubileeGUIApp().run() 