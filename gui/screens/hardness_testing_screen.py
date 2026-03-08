"""
Hardness Testing Screen.

Placeholder for future hardness testing functionality.
Will use a similar approach to powder dispensing but with different bed layout.
"""

from kivymd.uix.screen import MDScreen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText
from kivy.properties import ObjectProperty, BooleanProperty, StringProperty
from kivy.metrics import dp
from typing import Set


class HardnessSampleWidget(MDBoxLayout):
    sample_id = StringProperty("")
    selected = BooleanProperty(False)
    test_mode = StringProperty("none")

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self.selected = not self.selected
            return True
        return super().on_touch_down(touch)


class HardnessSampleGrid(MDBoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cols = 6
        self.rows = 4
        self.samples = {}
        self.sample_widgets = {}

    def on_kv_post(self, base_widget):
        self.populate_samples()
        self.populate_row_col_buttons()

    def populate_samples(self):
        if self.sample_widgets:
            return
        grid = self.ids.samples_grid
        for idx in range(self.rows * self.cols):
            sample_id = str(idx)
            sample = HardnessSampleWidget(sample_id=sample_id)
            self.samples[sample_id] = {"mode": "none"}
            self.sample_widgets[sample_id] = sample
            grid.add_widget(sample)

    def populate_row_col_buttons(self):
        if self.ids.row_buttons.children or self.ids.col_buttons.children:
            return
        for row in range(self.rows):
            btn = MDButton(
                MDButtonText(text=str(row + 1)),
                style="text",
                on_release=lambda x, r=row: self.select_row(r),
                size_hint=(None, None),
                size=(dp(24), dp(24)),
            )
            self.ids.row_buttons.add_widget(btn)
        for col in range(self.cols):
            btn = MDButton(
                MDButtonText(text=str(col + 1)),
                style="text",
                on_release=lambda x, c=col: self.select_col(c),
                size_hint=(None, None),
                size=(dp(24), dp(24)),
            )
            self.ids.col_buttons.add_widget(btn)

    def get_selected_samples(self) -> Set[str]:
        return {sid for sid, sample in self.sample_widgets.items() if sample.selected}

    def set_sample_selected(self, sample_id: str, selected: bool):
        if sample_id in self.sample_widgets:
            self.sample_widgets[sample_id].selected = selected

    def select_all(self):
        for sample in self.sample_widgets.values():
            sample.selected = True

    def clear_selection(self):
        for sample in self.sample_widgets.values():
            sample.selected = False

    def select_row(self, row_index: int):
        for col in range(self.cols):
            sample_id = str(row_index * self.cols + col)
            self.set_sample_selected(sample_id, True)

    def select_col(self, col_index: int):
        for row in range(self.rows):
            sample_id = str(row * self.cols + col_index)
            self.set_sample_selected(sample_id, True)

    def set_sample_mode(self, sample_id: str, mode: str):
        if sample_id in self.samples:
            self.samples[sample_id]["mode"] = mode
        if sample_id in self.sample_widgets:
            self.sample_widgets[sample_id].test_mode = mode


class HardnessTestingScreen(MDScreen):
    """Hardness Testing Screen."""
    view_model = ObjectProperty(None)
    app = ObjectProperty(None)

    def select_all_samples(self, *args):
        self.ids.sample_grid.select_all()

    def clear_selection(self, *args):
        self.ids.sample_grid.clear_selection()

    def set_mode_for_selected(self, mode: str):
        selected = self.ids.sample_grid.get_selected_samples()
        for sample_id in selected:
            self.ids.sample_grid.set_sample_mode(sample_id, mode)
