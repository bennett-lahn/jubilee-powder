"""
Settings Screen.

Configure hardware parameters before connecting to Jubilee.
Settings are locked when connected to prevent configuration conflicts.
"""

from kivymd.uix.screen import MDScreen
from kivymd.uix.dialog import (
    MDDialog,
    MDDialogHeadlineText,
    MDDialogSupportingText,
    MDDialogContentContainer,
    MDDialogButtonContainer,
)
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDButton, MDButtonText  # KivyMD 2.0 (MD3 buttons)
from kivy.uix.widget import Widget
from kivy.metrics import dp
from kivy.properties import BooleanProperty, StringProperty, ObjectProperty
import threading


class SettingsScreen(MDScreen):
    """
    Settings Screen.
    
    Features:
        - Hardware configuration (dispensers, pistons)
        - Jubilee network settings
        - Connection management
        - Extensible settings list
        - Locked when connected to prevent conflicts
    """
    
    is_connected = BooleanProperty(False)
    valid_inputs = BooleanProperty(False)
    total_pistons_text = StringProperty("Total Pistons: --")
    view_model = ObjectProperty(None)
    app = ObjectProperty(None)

    def on_kv_post(self, base_widget):
        self.update_total_pistons()
        self.update_validation()
    
    def update_total_pistons(self, *args):
        """Update total pistons calculation."""
        try:
            num_disp = int(self.ids.num_dispensers.text or 0)
            pistons_per = int(self.ids.pistons_per_dispenser.text or 0)
            total = num_disp * pistons_per
            self.total_pistons_text = f"Total Pistons: {total}"
        except ValueError:
            self.total_pistons_text = "Total Pistons: --"

    def update_validation(self, *args):
        """Update validation state for required inputs."""
        self.valid_inputs = self._inputs_valid()

    def _inputs_valid(self) -> bool:
        """Return True when required inputs are valid."""
        try:
            num_disp = int(self.ids.num_dispensers.text or 0)
            pistons_per = int(self.ids.pistons_per_dispenser.text or 0)
        except ValueError:
            return False
        return num_disp > 0 and pistons_per > 0
    
    def connect_to_jubilee(self, *args):
        """Connect to Jubilee system."""
        # Validate settings
        try:
            num_dispensers = int(self.ids.num_dispensers.text)
            pistons_per_dispenser = int(self.ids.pistons_per_dispenser.text)
            
            if num_dispensers <= 0 or pistons_per_dispenser <= 0:
                raise ValueError("Values must be positive")
            
            # Apply configuration to ViewModel
            self.view_model.set_hardware_config(num_dispensers, pistons_per_dispenser)
            
            # Show connecting dialog
            self.show_connecting_dialog()
            
            # Connect in background thread
            threading.Thread(target=self._connect_thread, daemon=True).start()
            
        except ValueError as e:
            self._show_error("Please enter valid positive numbers for hardware configuration.")
    
    def _connect_thread(self):
        """Connection thread to avoid blocking UI."""
        success = self.view_model.connect()
        # Connection state will be updated via app callback
    
    def show_connecting_dialog(self):
        """Show connecting dialog."""
        # KivyMD 2.0: Use MDCircularProgressIndicator
        from kivymd.uix.progressindicator import MDCircularProgressIndicator
        
        content = MDBoxLayout(
            orientation="vertical",
            spacing=dp(16),
            size_hint_y=None,
            height=dp(100)
        )
        
        spinner_widget = MDCircularProgressIndicator(
            size_hint=(None, None),
            size=(dp(46), dp(46)),
            pos_hint={"center_x": 0.5}
        )
        
        label = MDLabel(
            text="Connecting to Jubilee...",
            halign="center"
        )
        
        content.add_widget(spinner_widget)
        content.add_widget(label)
        
        self.connecting_dialog = MDDialog(
            MDDialogHeadlineText(text="Connecting", halign="left"),
            MDDialogContentContainer(content, orientation="vertical"),
            auto_dismiss=False,
        )
        self.connecting_dialog.open()
        
        # Auto-dismiss after connection (handled by callback)
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: self.check_connection_complete(), 2)
    
    def check_connection_complete(self):
        """Check if connection is complete and dismiss dialog."""
        if hasattr(self, 'connecting_dialog'):
            self.connecting_dialog.dismiss()
    
    def disconnect_from_jubilee(self, *args):
        """Disconnect from Jubilee system."""
        self.view_model.disconnect()
    
    def update_connection_state(self, connected: bool):
        """Update UI based on connection state (called by app)."""
        self.is_connected = connected
    
    def _show_error(self, message: str):
        """Show error dialog."""
        dialog = MDDialog(
            MDDialogHeadlineText(text="Error", halign="left"),
            MDDialogSupportingText(text=message, halign="left"),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="OK"), style="text", on_release=lambda x: dialog.dismiss()),
                spacing="8dp",
            ),
        )
        dialog.open()
