"""
Manual Control Screen.

Provides access to Jubilee web UI for advanced manual control.
Warning: Using manual control invalidates the automation system state.
"""

from kivymd.uix.screen import MDScreen
from kivymd.uix.button import MDButton, MDButtonText  # KivyMD 2.0 (MD3 buttons)
from kivymd.uix.dialog import MDDialog, MDDialogHeadlineText, MDDialogSupportingText, MDDialogButtonContainer
from kivy.uix.widget import Widget
from kivy.properties import ObjectProperty, StringProperty
import webbrowser


class ManualControlScreen(MDScreen):
    """
    Manual Control Screen.
    
    Features:
        - Warning about manual control implications
        - Access to Jubilee web UI
        - System state reset warning
        - Advanced users only
    """
    
    view_model = ObjectProperty(None)
    app = ObjectProperty(None)
    jubilee_ip = StringProperty("jubilee.local")
    
    def confirm_open_web_ui(self, *args):
        """Show confirmation dialog before opening web UI."""
        dialog = MDDialog(
            MDDialogHeadlineText(text="Confirm Manual Control", halign="left"),
            MDDialogSupportingText(
                text="Are you sure you want to open the Jubilee web UI?\n\n"
                     "This will invalidate the automation system state and require "
                     "reconnection afterward.",
                halign="left",
            ),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="CANCEL"), style="text", on_release=lambda x: dialog.dismiss()),
                MDButton(MDButtonText(text="I UNDERSTAND - PROCEED"), style="text", on_release=lambda x: self.open_web_ui(dialog)),
                spacing="8dp",
            ),
        )
        dialog.open()
    
    def open_web_ui(self, dialog):
        """Open Jubilee web UI in browser."""
        dialog.dismiss()
        
        try:
            # Open in default browser
            url = f"http://{self.jubilee_ip}"
            webbrowser.open(url)
            
            # Disconnect from system to invalidate state
            if self.app.connected:
                self.view_model.disconnect()
            
            # Show success message
            success_dialog = MDDialog(
                MDDialogHeadlineText(text="Web UI Opened", halign="left"),
                MDDialogSupportingText(
                    text=f"Jubilee web UI opened at {url}\n\n"
                         "The automation system has been disconnected.\n"
                         "Remember to reconnect in Settings after using manual control.",
                    halign="left",
                ),
                MDDialogButtonContainer(
                    Widget(),
                    MDButton(MDButtonText(text="OK"), style="text", on_release=lambda x: success_dialog.dismiss()),
                    spacing="8dp",
                ),
            )
            success_dialog.open()
            
        except Exception as e:
            error_dialog = MDDialog(
                MDDialogHeadlineText(text="Error", halign="left"),
                MDDialogSupportingText(
                    text=f"Could not open web browser:\n{str(e)}\n\n"
                         f"Please manually navigate to: http://{self.jubilee_ip}",
                    halign="left",
                ),
                MDDialogButtonContainer(
                    Widget(),
                    MDButton(MDButtonText(text="OK"), style="text", on_release=lambda x: error_dialog.dismiss()),
                    spacing="8dp",
                ),
            )
            error_dialog.open()
    
    def update_jubilee_ip(self, ip: str):
        """Update Jubilee IP address (called from settings)."""
        self.jubilee_ip = ip
        # Update display if needed
