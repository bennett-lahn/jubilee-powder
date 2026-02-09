"""
Data Screen.

Browse and view data files, photos, and past run results.
"""

from kivymd.uix.screen import MDScreen
from kivymd.uix.label import MDLabel
from kivymd.uix.list import (
    MDListItem,
    MDListItemHeadlineText,
    MDListItemLeadingIcon,
    MDListItemSupportingText,
)
from kivymd.uix.button import MDButton, MDButtonText  # KivyMD 2.0 (MD3 buttons)
# Note: MDFileManager removed in KivyMD 2.0 - not needed, using native file opening
from kivymd.uix.dialog import MDDialog, MDDialogHeadlineText, MDDialogSupportingText, MDDialogButtonContainer
from kivy.uix.widget import Widget

from kivy.metrics import dp
from kivy.properties import ObjectProperty
from pathlib import Path
import os
import subprocess
import platform


class DataScreen(MDScreen):
    """
    Data Browser Screen.
    
    Features:
        - Browse data directory
        - View past run results
        - Access photos and output files
        - Open files with system default application
    """
    
    app = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.file_manager = None
        
        # Determine data directory
        self.data_dir = Path(__file__).parent.parent.parent / "data"
        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True, exist_ok=True)

    def on_kv_post(self, base_widget):
        self.file_list = self.ids.file_list
        self.ids.info_label.text = f"Data Directory: {self.data_dir}"
        self.refresh_file_list()
    
    def refresh_file_list(self, *args):
        """Refresh the file list."""
        self.file_list.clear_widgets()
        
        if not self.data_dir.exists():
            self.file_list.add_widget(
                MDLabel(
                    text="No data directory found",
                    halign="center",
                    theme_text_color="Secondary"
                )
            )
            return
        
        # Get all files in data directory
        files = sorted(self.data_dir.glob("*"))
        
        if not files:
            self.file_list.add_widget(
                MDLabel(
                    text="No files found in data directory",
                    halign="center",
                    theme_text_color="Secondary",
                    size_hint_y=None,
                    height=dp(60)
                )
            )
            return
        
        # Add file items
        for file_path in files:
            if file_path.is_file():
                icon = self._get_file_icon(file_path)
                secondary = f"{self._format_size(file_path.stat().st_size)} • {self._format_date(file_path.stat().st_mtime)}"
                
                # KivyMD 2.0 list item
                item = MDListItem(
                    MDListItemLeadingIcon(icon=icon),
                    MDListItemHeadlineText(text=file_path.name),
                    MDListItemSupportingText(text=secondary),
                    on_release=lambda x, fp=file_path: self.open_file(fp)
                )
                self.file_list.add_widget(item)
            
            elif file_path.is_dir():
                # KivyMD 2.0 list item
                item = MDListItem(
                    MDListItemLeadingIcon(icon="folder"),
                    MDListItemHeadlineText(text=file_path.name),
                    MDListItemSupportingText(text="Folder"),
                    on_release=lambda x, fp=file_path: self.open_folder(fp)
                )
                self.file_list.add_widget(item)
    
    def _get_file_icon(self, file_path: Path) -> str:
        """Get appropriate icon for file type."""
        suffix = file_path.suffix.lower()
        
        icon_map = {
            '.csv': 'file-delimited',
            '.json': 'code-json',
            '.txt': 'file-document',
            '.png': 'image',
            '.jpg': 'image',
            '.jpeg': 'image',
            '.pdf': 'file-pdf-box',
            '.xlsx': 'file-excel',
        }
        
        return icon_map.get(suffix, 'file')
    
    def _format_size(self, size: int) -> str:
        """Format file size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    
    def _format_date(self, timestamp: float) -> str:
        """Format timestamp to readable date."""
        from datetime import datetime
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M")
    
    def open_file(self, file_path: Path):
        """Open file with system default application."""
        try:
            if platform.system() == 'Windows':
                os.startfile(file_path)
            elif platform.system() == 'Darwin':  # macOS
                subprocess.run(['open', str(file_path)])
            else:  # Linux
                # Prefer explorer.exe when running under WSL.
                is_wsl = bool(os.environ.get("WSL_DISTRO_NAME")) or "microsoft" in Path("/proc/version").read_text().lower()
                if is_wsl:
                    subprocess.run(['explorer.exe', str(file_path)])
                else:
                    # Try a few common Linux openers.
                    for cmd in (['xdg-open', str(file_path)], ['gio', 'open', str(file_path)], ['kde-open5', str(file_path)], ['gnome-open', str(file_path)]):
                        try:
                            subprocess.run(cmd)
                            break
                        except FileNotFoundError:
                            continue
                    else:
                        raise FileNotFoundError("No file opener found (xdg-open/gio/kde-open5/gnome-open).")
        except Exception as e:
            dialog = MDDialog(
                MDDialogHeadlineText(text="Error"),
                MDDialogSupportingText(text=f"Could not open file:\n{str(e)}"),
                MDDialogButtonContainer(
                    Widget(),
                    MDButton(MDButtonText(text="OK"), style="text", on_release=lambda x: dialog.dismiss()),
                    spacing="8dp",
                ),
            )
            dialog.open()
    
    def open_folder(self, folder_path: Path):
        """Open folder in system file browser."""
        self.open_file(folder_path)
    
    def open_data_folder(self, *args):
        """Open the data directory in system file browser."""
        self.open_folder(self.data_dir)
