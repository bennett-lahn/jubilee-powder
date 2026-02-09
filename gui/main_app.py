"""
Main Jubilee GUI Application.

This is a complete rewrite using KivyMD with Material Design principles.
Features a navigation drawer with 5 screens and a bottom status bar.

Architecture:
    - KivyMD components exclusively
    - Yellow/Black color scheme (matching Jubilee branding)
    - Modular screen-based design
    - MVVM pattern with JubileeViewModel
    - Extensible component system

Screens:
    - Powder Dispensing: Configure and run powder dispensing jobs
    - Hardness Testing: Configure and run hardness testing
    - Data: Browse results and data files
    - Manual Control: Access Jubilee web UI
    - Settings: Configure hardware before connection

Usage:
    python gui/main_app.py
"""

# Suppress clipboard warnings on systems without xclip/xsel (WSL/Linux)
import os
os.environ['KIVY_CLIPBOARD'] = 'dummy'

from kivymd.app import MDApp
from kivy.lang import Builder
from kivy.resources import resource_add_path
from kivy.properties import StringProperty, NumericProperty, BooleanProperty
from kivy.clock import Clock

# Import screens
from screens.powder_dispensing_screen import PowderDispensingScreen
from screens.hardness_testing_screen import HardnessTestingScreen
from screens.data_screen import DataScreen
from screens.manual_control_screen import ManualControlScreen
from screens.settings_screen import SettingsScreen

# Import components
from components.bottom_bar import BottomStatusBar

# Import ViewModel
from jubilee_view_model import JubileeViewModel


class JubileeGUIApp(MDApp):
    """
    Main Jubilee GUI Application.
    
    Features:
        - Material Design with yellow/black theme
        - Navigation drawer with 5 screens
        - Bottom status bar with connection and progress
        - Extensible modular architecture
    """
    
    # Connection state
    connected = BooleanProperty(False)
    connection_status = StringProperty("Disconnected")
    
    # Job state
    job_running = BooleanProperty(False)
    job_progress = NumericProperty(0)
    job_completed = NumericProperty(0)
    job_total = NumericProperty(0)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.view_model = None
        self.navigation_drawer = None
        
    def build(self):
        """Build the application UI."""
        # Configure theme
        # Lock to light mode regardless of OS theme, so Jubilee colors are stable.
        self.theme_cls.theme_style = "Light"

        # Use a known-good palette name for this KivyMD build.
        # (Some palette names can crash scheme generation in 2.0.1.dev0.)
        self.theme_cls.primary_palette = "Yellow"
        self.theme_cls.primary_hue = "700"  # Darker yellow
        self.theme_cls.accent_palette = "Amber"
        
        # Set window title
        self.title = "Jubilee Automation System"
        
        # Initialize ViewModel with callbacks
        self.view_model = JubileeViewModel(
            on_connection_changed=self._on_connection_changed,
            on_weight_changed=self._on_weight_changed,
            on_status_changed=self._on_status_changed,
            on_job_progress=self._on_job_progress,
            on_job_completed=self._on_job_completed,
            on_error=self._on_error
        )
        
        # Build main layout from KV
        gui_dir = os.path.normpath(os.path.abspath(os.path.dirname(__file__)))
        resource_add_path(gui_dir)
        resource_add_path(os.path.join(gui_dir, "screens"))
        kv_path = os.path.join(gui_dir, "main.kv")
        screens_dir = os.path.join(gui_dir, "screens")
        kv_files = [
            os.path.join(screens_dir, "powder_dispensing_screen.kv"),
            os.path.join(screens_dir, "hardness_testing_screen.kv"),
            os.path.join(screens_dir, "data_screen.kv"),
            os.path.join(screens_dir, "manual_control_screen.kv"),
            os.path.join(screens_dir, "settings_screen.kv"),
        ]
        for kv_file in kv_files:
            Builder.load_file(kv_file)
        root = Builder.load_file(kv_path)

        # Store references for callback usage
        self.screen_manager = root.ids.screen_manager
        self.top_bar_title = root.ids.top_bar_title
        self.bottom_bar = root.ids.bottom_bar

        return root

    def apply_alpha(self, color, alpha: float):
        """Return color with the specified alpha."""
        return [color[0], color[1], color[2], alpha]

    def nav_icon_color(self, screen_name: str):
        """Return nav icon color based on active screen."""
        if not getattr(self, "screen_manager", None):
            return self.apply_alpha(self.theme_cls.textColor, 0.6)
        if self.screen_manager.current == screen_name:
            return self.theme_cls.primaryColor
        return self.apply_alpha(self.theme_cls.textColor, 0.6)
    
    def switch_screen(self, screen_name: str, title: str):
        """Switch to a different screen."""
        self.screen_manager.current = screen_name
        if hasattr(self, "top_bar_title"):
            self.top_bar_title.text = title
    
    # ViewModel Callbacks
    def _on_connection_changed(self, connected: bool):
        """Called when connection state changes."""
        def update(dt):
            self.connected = connected
            self.connection_status = "Connected" if connected else "Disconnected"
            
            # Disable settings when connected
            if hasattr(self.screen_manager, 'get_screen'):
                settings_screen = self.screen_manager.get_screen('settings')
                settings_screen.update_connection_state(connected)
        
        Clock.schedule_once(update, 0)
    
    def _on_weight_changed(self, weight: float):
        """Called when scale weight changes."""
        def update(dt):
            # Notify current screen if it has weight display
            current_screen = self.screen_manager.current_screen
            if hasattr(current_screen, 'update_weight'):
                current_screen.update_weight(weight)
        
        Clock.schedule_once(update, 0)
    
    def _on_status_changed(self, status: str):
        """Called when status message changes."""
        def update(dt):
            # Update bottom bar or show snackbar
            if hasattr(self.bottom_bar, 'update_status'):
                self.bottom_bar.update_status(status)
        
        Clock.schedule_once(update, 0)
    
    def _on_job_progress(self, completed: int, total: int, current_well: str):
        """Called when job progress updates."""
        def update(dt):
            self.job_completed = completed
            self.job_total = total
            self.job_progress = (completed / total * 100) if total > 0 else 0
            
            # Notify current screen
            current_screen = self.screen_manager.current_screen
            if hasattr(current_screen, 'update_job_progress'):
                current_screen.update_job_progress(completed, total, current_well)
        
        Clock.schedule_once(update, 0)
    
    def _on_job_completed(self):
        """Called when job completes successfully."""
        def update(dt):
            self.job_running = False
            
            # Show completion dialog
            from kivymd.uix.dialog import MDDialog, MDDialogHeadlineText, MDDialogSupportingText, MDDialogButtonContainer
            from kivy.uix.widget import Widget
            from kivymd.uix.button import MDButton, MDButtonText  # KivyMD 2.0 (MD3 buttons)
            
            dialog = MDDialog(
                MDDialogHeadlineText(text="Job Completed"),
                MDDialogSupportingText(text="All dispensing operations completed successfully!"),
                MDDialogButtonContainer(
                    Widget(),
                    MDButton(MDButtonText(text="OK"), style="text", on_release=lambda x: dialog.dismiss()),
                    spacing="8dp",
                ),
            )
            dialog.open()
        
        Clock.schedule_once(update, 0)
    
    def _on_error(self, error_message: str):
        """Called when an error occurs."""
        def update(dt):
            from kivymd.uix.dialog import MDDialog, MDDialogHeadlineText, MDDialogSupportingText, MDDialogButtonContainer
            from kivy.uix.widget import Widget
            from kivymd.uix.button import MDButton, MDButtonText  # KivyMD 2.0 (MD3 buttons)
            
            dialog = MDDialog(
                MDDialogHeadlineText(text="Error"),
                MDDialogSupportingText(text=error_message),
                MDDialogButtonContainer(
                    Widget(),
                    MDButton(MDButtonText(text="OK"), style="text", on_release=lambda x: dialog.dismiss()),
                    spacing="8dp",
                ),
            )
            dialog.open()
        
        Clock.schedule_once(update, 0)
    
    def on_stop(self):
        """Cleanup when app stops."""
        if self.view_model:
            self.view_model.disconnect()


if __name__ == '__main__':
    JubileeGUIApp().run()
