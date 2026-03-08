"""
Bottom Status Bar Component.

Displays connection status and job progress at the bottom of the screen.
"""

from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.progressindicator import MDLinearProgressIndicator
from kivy.properties import StringProperty, NumericProperty, BooleanProperty, ObjectProperty
from kivy.metrics import dp


class BottomStatusBar(MDBoxLayout):
    """
    Bottom status bar showing connection and job progress.
    
    Features:
        - Connection status with icon
        - Job progress bar
        - Completed/Total counter
        - Auto-hide when no job running
    """
    
    connection_status = StringProperty("Disconnected")
    job_progress = NumericProperty(0)
    job_text = StringProperty("0/0")
    job_visible = BooleanProperty(False)
    app = ObjectProperty(None)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Configure layout
        self.orientation = "horizontal"
        self.size_hint_y = None
        self.height = dp(48)
        self.padding = dp(16)
        self.spacing = dp(16)
        # Keep bottom bar neutral in light mode.
        self.md_bg_color = [1, 1, 1, 1]
        
        # Connection status section
        self.connection_label = MDLabel(
            text="Disconnected",
            size_hint_x = 0.3,
            theme_text_color="Secondary",
            font_style="Label",
            role="small",
        )
        
        # Job progress section
        self.progress_box = MDBoxLayout(
            orientation="horizontal",
            size_hint_x=0.7,
            spacing=dp(8),
            opacity=0  # Hidden by default
        )
        
        self.progress_label = MDLabel(
            text="Job Progress:",
            size_hint_x=None,
            width=dp(100),
            theme_text_color="Secondary",
            font_style="Label",
            role="small",
        )
        
        self.progress_bar = MDLinearProgressIndicator(
            value=0,
            size_hint_x=0.6,
        )
        
        self.progress_counter = MDLabel(
            text="0/0",
            size_hint_x=None,
            width=dp(60),
            theme_text_color="Secondary",
            font_style="Label",
            role="small",
            halign="right"
        )
        
        # Build progress box
        self.progress_box.add_widget(self.progress_label)
        self.progress_box.add_widget(self.progress_bar)
        self.progress_box.add_widget(self.progress_counter)
        
        # Add to main layout
        self.add_widget(self.connection_label)
        self.add_widget(self.progress_box)
        
        self.bind(app=self._on_app)

    def _on_app(self, *args):
        """Bind to app properties once app is set."""
        if not self.app:
            return
        self.app.bind(
            connected=self.update_connection,
            connection_status=self.update_connection,
            job_running=self.update_job_visibility,
            job_progress=self.update_progress,
            job_completed=self.update_counter,
            job_total=self.update_counter,
        )
        self.update_connection()
        self.update_job_visibility()
        self.update_progress()
        self.update_counter()
    
    def update_connection(self, *args):
        """Update connection status display."""
        if self.app and self.app.connected:
            status = "Connected"
            color = [0.2, 0.7, 0.2, 1]
        else:
            status = "Disconnected"
            color = [0.5, 0.5, 0.5, 1]
        
        self.connection_label.text = status
        self.connection_label.text_color = color
    
    def update_job_visibility(self, *args):
        """Show/hide job progress section."""
        if self.app.job_running:
            self.progress_box.opacity = 1
        else:
            self.progress_box.opacity = 0
    
    def update_progress(self, *args):
        """Update progress bar value."""
        self.progress_bar.value = self.app.job_progress
    
    def update_counter(self, *args):
        """Update completed/total counter."""
        self.progress_counter.text = f"{self.app.job_completed}/{self.app.job_total}"
    
    def update_status(self, status: str):
        """Update status message (can be extended to show snackbar)."""
        # Could show a snackbar here for status updates
        pass
