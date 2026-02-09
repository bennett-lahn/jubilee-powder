"""
Powder Dispensing Screen.

Provides a visual interface for selecting wells and configuring dispensing jobs.
Uses a silhouette layout matching the actual Jubilee bed configuration.
"""

from kivymd.uix.screen import MDScreen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDButton, MDButtonText  # KivyMD 2.0 (MD3 buttons)
from kivymd.uix.anchorlayout import MDAnchorLayout
from kivymd.uix.dialog import (
    MDDialog,
    MDDialogHeadlineText,
    MDDialogSupportingText,
    MDDialogContentContainer,
    MDDialogButtonContainer,
)
from kivy.uix.widget import Widget
from kivymd.uix.textfield import MDTextField
from kivy.properties import BooleanProperty, StringProperty, NumericProperty, ObjectProperty
from kivy.metrics import dp
from typing import Set

from jubilee_view_model import DispensingJob


class MoldWidget(Widget):
    """
    Visual representation of a single well on the bed.
    
    Features:
        - Circular display matching well appearance
        - Shows well ID
        - Shows target and current weight
        - Visual selection state (yellow when selected)
        - Touch interaction
    """
    
    mold_id = StringProperty("")
    selected = BooleanProperty(False)
    target_weight = NumericProperty(0.0)
    current_weight = NumericProperty(0.0)
    
    def on_touch_down(self, touch):
        """Handle touch/click on well."""
        if self.collide_point(*touch.pos):
            self.selected = not self.selected
            return True
        return super().on_touch_down(touch)


class BedVisualization(MDAnchorLayout):
    """
    Visual representation of the Jubilee bed with wells.
    
    Based on the actual bed layout with wells arranged in a grid pattern.
    Allows interactive selection of wells for dispensing operations.
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        self.cols = 6
        self.rows = 4
        self.molds = {}
        self.mold_widgets = {}

    def on_kv_post(self, base_widget):
        self.populate_molds()

    def populate_molds(self):
        """Populate the mold grid once."""
        if self.mold_widgets:
            return
        grid = self.ids.molds_grid
        for idx in range(self.rows * self.cols):
            mold_id = str(idx)
            mold = MoldWidget(mold_id=mold_id)
            self.molds[mold_id] = {"target_weight": 0.0, "current_weight": 0.0}
            self.mold_widgets[mold_id] = mold
            grid.add_widget(mold)

    def get_selected_molds(self) -> Set[str]:
        """Get set of selected mold IDs."""
        return {mid for mid, mold in self.mold_widgets.items() if mold.selected}

    def set_mold_selected(self, mold_id: str, selected: bool):
        """Set selection state of a mold."""
        if mold_id in self.mold_widgets:
            self.mold_widgets[mold_id].selected = selected

    def select_all(self):
        """Select all molds."""
        for mold in self.mold_widgets.values():
            mold.selected = True

    def clear_selection(self):
        """Clear all selections."""
        for mold in self.mold_widgets.values():
            mold.selected = False

    def set_mold_weight(self, mold_id: str, target: float = None, current: float = None):
        """Set weight information for a mold."""
        if mold_id in self.molds:
            if target is not None:
                self.molds[mold_id]["target_weight"] = target
            if current is not None:
                self.molds[mold_id]["current_weight"] = current

        if mold_id in self.mold_widgets:
            if target is not None:
                self.mold_widgets[mold_id].target_weight = target
            if current is not None:
                self.mold_widgets[mold_id].current_weight = current


class PowderDispensingScreen(MDScreen):
    """
    Powder Dispensing Screen.
    
    Features:
        - Visual bed layout with selectable wells
        - Configure target weights for selected wells
        - Start/stop dispensing jobs
        - Real-time progress display
        - Job status and weight updates
    """
    
    view_model = ObjectProperty(None)
    app = ObjectProperty(None)
    weight_dialog = None
    
    def select_all_wells(self, *args):
        """Select all wells."""
        self.ids.bed_viz.select_all()
    
    def clear_selection(self, *args):
        """Clear well selection."""
        self.ids.bed_viz.clear_selection()
    
    def show_weight_dialog(self, *args):
        """Show dialog to set weights for selected wells."""
        selected = self.ids.bed_viz.get_selected_molds()
        
        if not selected:
            self._show_error("Please select at least one well first.")
            return
        
        # Create dialog content
        content = MDBoxLayout(orientation="vertical", spacing=dp(12), size_hint_y=None)
        content.bind(minimum_height=content.setter('height'))
        
        # Add label
        content.add_widget(MDLabel(
            text=f"Set target weight for {len(selected)} wells:",
            size_hint_y=None,
            height=dp(40)
        ))
        
        # Weight input
        weight_input = MDTextField(
            hint_text="Target Weight (grams)",
            mode="outlined",
            size_hint_y=None,
            height=dp(56),
            input_filter="float"
        )
        content.add_widget(weight_input)
        
        # Create dialog (KivyMD 2.0 composed API)
        self.weight_dialog = MDDialog(
            MDDialogHeadlineText(text="Set Target Weights", halign="left"),
            MDDialogContentContainer(content, orientation="vertical"),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="CANCEL"), style="text", on_release=lambda x: self.weight_dialog.dismiss()),
                MDButton(MDButtonText(text="APPLY"), style="text", on_release=lambda x: self.apply_weights(weight_input.text, selected)),
                spacing="8dp",
            ),
        )
        self.weight_dialog.open()
    
    def apply_weights(self, weight_text: str, selected_wells: Set[str]):
        """Apply weight to selected wells."""
        try:
            weight = float(weight_text)
            if weight <= 0:
                raise ValueError("Weight must be positive")
            
            # Apply to all selected wells
            for mold_id in selected_wells:
                self.ids.bed_viz.set_mold_weight(mold_id, target=weight)
            
            if self.weight_dialog:
                self.weight_dialog.dismiss()
            self.ids.status_label.text = f"Target weight set to {weight}g for {len(selected_wells)} wells"
            
        except ValueError as e:
            self._show_error("Please enter a valid positive number.")
    
    def start_job(self, *args):
        """Start the dispensing job."""
        selected = self.ids.bed_viz.get_selected_molds()
        
        if not selected:
            self._show_error("Please select at least one well.")
            return
        
        # Check if weights are set
        molds_data = self.ids.bed_viz.molds
        has_weights = all(molds_data[mid]["target_weight"] > 0 for mid in selected)
        
        if not has_weights:
            self._show_error("Please set target weights for all selected wells.")
            return
        
        # Check connection
        if not self.app.connected:
            self._show_error("Not connected to Jubilee. Please configure and connect in Settings first.")
            return
        
        # Create jobs
        jobs = [
            DispensingJob(
                well_id=mid,
                target_weight=molds_data[mid]["target_weight"]
            )
            for mid in sorted(selected)
        ]
        
        # Start job through ViewModel
        self.app.job_running = True
        self.app.job_total = len(jobs)
        self.app.job_completed = 0
        
        success = self.view_model.start_job(jobs)
        
        if success:
            self.ids.status_label.text = f"Job started: {len(jobs)} wells"
        else:
            self.app.job_running = False
            self._show_error("Failed to start job. Check connection and try again.")
    
    def update_weight(self, weight: float):
        """Update current weight display (called by app)."""
        # This could update a live weight display if needed
        pass
    
    def update_job_progress(self, completed: int, total: int, current_well: str):
        """Update job progress display (called by app)."""
        self.ids.status_label.text = f"Processing well {current_well} ({completed}/{total})"
        
        # Update current weight for the well being processed
        if current_well in self.ids.bed_viz.molds:
            # Could update current weight display here
            pass
    
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
