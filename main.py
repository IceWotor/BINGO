import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

from kivy.resources import resource_add_path
resource_add_path(BASE_DIR)

import sqlite3
import threading

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.properties import StringProperty

from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.textinput import TextInput
from reconstruction.terms import extract_terms
from reconstruction.textedit import (words_to_text, text_to_words,words_after_reconstruction)

import phone_io
from reconstruction import ocr_engine
import re
import random
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from reconstruction.damage import WEIGHTS, GAP_K, GAP_MID
from reconstruction.reconstruct import detect, reconstruct_words
from reconstruction.report import build_report_blocks, build_how_blocks, esc


class Database:

    def __init__(self, path="bingo.db"):
        self.connection = sqlite3.connect(path)
        self.cursor = self.connection.cursor()

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS review_sets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS terms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_set_id INTEGER NOT NULL,
                term TEXT NOT NULL,
                definition TEXT NOT NULL,
                FOREIGN KEY (review_set_id)
                    REFERENCES review_sets(id)
            )
        """)

        self.connection.commit()

    def create_review_set(self, name):
        self.cursor.execute(
            "INSERT INTO review_sets (name) VALUES (?)", (name,))
        self.connection.commit()
        return self.cursor.lastrowid

    def add_term(self, review_set_id, term, definition):
        self.cursor.execute(
            "INSERT INTO terms (review_set_id, term, definition) VALUES (?, ?, ?)",
            (review_set_id, term, definition))
        self.connection.commit()
        return self.cursor.lastrowid

    def get_terms(self, review_set_id):
        self.cursor.execute(
            "SELECT id, term, definition FROM terms WHERE review_set_id = ?",
            (review_set_id,))
        return self.cursor.fetchall()

    def get_term_count(self, review_set_id):
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM terms WHERE review_set_id = ?",
            (review_set_id,))
        return cursor.fetchone()[0]

    def delete_term(self, term_id):
        self.cursor.execute("DELETE FROM terms WHERE id = ?", (term_id,))
        self.connection.commit()

    def update_review_set_name(self, review_set_id, name):
        self.cursor.execute(
            "UPDATE review_sets SET name = ? WHERE id = ?",
            (name, review_set_id))
        self.connection.commit()

    def get_review_sets(self):
        self.cursor.execute(
            "SELECT id, name FROM review_sets ORDER BY created_at DESC")
        return self.cursor.fetchall()

    def delete_review_set(self, review_set_id):
        self.cursor.execute(
            "DELETE FROM terms WHERE review_set_id = ?", (review_set_id,))
        self.cursor.execute(
            "DELETE FROM review_sets WHERE id = ?", (review_set_id,))
        self.connection.commit()

    def close(self):
        self.connection.close()


class Home(Screen):
    def go_to_scan(self):
        self.manager.transition.direction = "left"
        self.manager.current = "scan"

    def go_to_manual(self):
        app = App.get_running_app()
        review_set_id = app.db.create_review_set("Untitled Review Set")
        manual = self.manager.get_screen("manual")
        manual.review_set_id = review_set_id
        manual.is_existing_set = False
        print("Created Review Set:", review_set_id)
        self.manager.transition.direction = "left"
        self.manager.current = "manual"

    def go_to_reviewset(self):
        self.manager.transition.direction = "left"
        self.manager.current = "reviewsets"


class Scan(Screen):
    append_to = None    # review set id when adding another picture to an existing set

    def go_back_home(self):
        self.manager.transition.direction = "right"
        if self.append_to is not None:
            self.append_to = None
            self.manager.current = "manual"
        else:
            self.manager.current = "home"

    def go_camera(self):
        phone_io.take_photo(self._on_image)

    def go_upload(self):
        phone_io.pick_image(self._on_image)

    @mainthread
    def _on_image(self, path):
        if not path:
            return                      # cancelled or failed
        preview = self.manager.get_screen("imagepreview")
        preview.image_path = path
        self.manager.transition.direction = "left"
        self.manager.current = "imagepreview"
        
class ImagePreview(Screen):

    image_path = ""

    def take_photo_again(self):
        self.manager.transition.direction = "right"
        self.manager.current = "scan"

    def on_enter(self):
        self.ids.preview_image.source = self.image_path
        self.ids.preview_image.reload()

    def use_photo(self):
        self.manager.get_screen("processing").mode = "ocr"
        self.manager.transition.direction = "left"
        self.manager.current = "processing"

class Processing(Screen):
    mode = "ocr"        # "ocr", "reconstruct" or "recheck"
    detection = None    # input for "reconstruct"
    result = None       # input for "recheck"

    def on_enter(self):
        if self.mode == "reconstruct":
            threading.Thread(target=self._reconstruct,
                             args=(self.detection,), daemon=True).start()
            return
        if self.mode == "recheck":
            threading.Thread(target=self._recheck,
                             args=(self.result,), daemon=True).start()
            return
        image_path = self.manager.get_screen("imagepreview").image_path
        try:
            ocr_engine.run_ocr_async(image_path, self._on_ocr)
        except Exception:
            import traceback
            traceback.print_exc()
            self._to_detection(None)

    # ---- OCR, then damage detection ----
    def _on_ocr(self, words, has_conf, error):
        if error or words is None:
            print("OCR failed:", error)
            self._to_detection(None)
            return
        threading.Thread(target=self._detect,
                         args=(words, has_conf), daemon=True).start()

    def _detect(self, words, has_conf):
        det = None
        try:
            det = detect(words, has_conf)
        except Exception:
            import traceback
            traceback.print_exc()
        self._to_detection(det, "scan")

    # ---- damage check again, on the reconstructed text ----
    def _recheck(self, result):
        det = None
        try:
            det = detect(words_after_reconstruction(result), True)
        except Exception:
            import traceback
            traceback.print_exc()
        self._to_detection(det, "reconstructed")

    @mainthread
    def _to_detection(self, det, back="scan"):
        self.manager.get_screen("detection").show(det, back)
        self.manager.transition.direction = "left"
        self.manager.current = "detection"

    # ---- reconstruction ----
    def _reconstruct(self, det):
        result = None
        try:
            result = reconstruct_words(det.words, det.has_conf, det)
        except Exception:
            import traceback
            traceback.print_exc()
        self._to_reconstructed(result, det)

    @mainthread
    def _to_reconstructed(self, result, det):
        back = self.manager.get_screen("detection").back_to
        self.manager.get_screen("reconstructed").show(result, det, back)
        self.manager.transition.direction = "left"
        self.manager.current = "reconstructed"
        
class ExtractedContent(Screen):
    ocr_text = StringProperty("")
    parsed_terms = []
    result = None

    def back_to_scan(self):
        self.manager.transition.direction = "right"
        self.manager.current = "scan"

    def open_report(self):
        if self.result is None:
            return
        report = self.manager.get_screen("report")
        report.load(self.result)
        self.manager.transition.direction = "left"
        self.manager.current = "report"

    def load_entries(self, terms):
        os.chdir(BASE_DIR)

        self.parsed_terms = terms
        self.ids.textEntriesContainer.clear_widgets()

        if not terms:
            self.ocr_text = "No terms could be extracted."
            return

        self.ocr_text = ""

        for number, item in enumerate(terms, start=1):
            entry = TextPreviewEntry(
                number=number,
                term=item.get("term", ""),
                definition=item.get("definition", ""),
                confidence=item.get("confidence", 0)
            )
            self.ids.textEntriesContainer.add_widget(entry)

    def continue_to_manual(self):
        if not self.parsed_terms:
            print("No terms to add.")
            return

        app = App.get_running_app()
        review_set_id = app.db.create_review_set("Untitled Review Set")

        manual = self.manager.get_screen("manual")
        manual.review_set_id = review_set_id
        manual.is_existing_set = False
        manual.ids.entriesContainer.clear_widgets()

        for item in self.parsed_terms:
            term = item.get("term", "").strip()
            definition = item.get("definition", "").strip()
            if not term or not definition:
                continue

            term_id = app.db.add_term(review_set_id, term, definition)
            entry = TermEntry(term_id=term_id, term=term, definition=definition)
            manual.ids.entriesContainer.add_widget(entry)

        manual.ids.entryCountLabel.text = str(app.db.get_term_count(review_set_id))

        self.manager.transition.direction = "left"
        self.manager.current = "manual"


class Report(Screen):

    def go_back(self):
        self.manager.transition.direction = "right"
        self.manager.current = "extractedcontent"

    def load(self, result):
        box = self.ids.reportContainer
        box.clear_widgets()
        for block in build_report_blocks(result):
            lbl = Label(text=block, markup=True,
                        font_name="./assets/fonts/PixelifySans.ttf",
                        font_size="11sp", color=(1, 1, 1, 1),
                        size_hint_y=None, halign="left", valign="top")
            lbl.bind(width=lambda i, v: setattr(i, "text_size", (v, None)))
            lbl.bind(texture_size=lambda i, v: setattr(i, "height", v[1] + dp(8)))
            box.add_widget(lbl)


class Manual(Screen):

    review_set_id = None
    review_set_name = ""
    is_existing_set = False

    def load_existing_set(self, review_set_id, name):
        app = App.get_running_app()

        self.review_set_id = review_set_id
        self.review_set_name = name
        self.is_existing_set = True

        self.ids.entriesContainer.clear_widgets()
        self.ids.termInput.text = ""
        self.ids.definitionInput.text = ""

        for term_id, term, definition in app.db.get_terms(review_set_id):
            entry = TermEntry(term_id=term_id, term=term, definition=definition)
            self.ids.entriesContainer.add_widget(entry)

        self.ids.entryCountLabel.text = str(app.db.get_term_count(review_set_id))

    def go_back_home(self, instance):
        app = App.get_running_app()

        if self.is_existing_set:
            self.is_existing_set = False
            self.review_set_id = None
            self.ids.entriesContainer.clear_widgets()
            self.ids.entryCountLabel.text = "0"
            self.ids.termInput.text = ""
            self.ids.definitionInput.text = ""
            self.manager.transition.direction = "right"
            self.manager.current = "reviewsets"
            return

        if self.review_set_id is None:
            self.manager.transition.direction = "right"
            self.manager.current = "home"
            return

        if app.db.get_term_count(self.review_set_id) == 0:
            app.db.delete_review_set(self.review_set_id)
            print("Deleted empty Review Set:", self.review_set_id)
            self.review_set_id = None
            self.manager.transition.direction = "right"
            self.manager.current = "home"
            return

        popup_content = GoBackPopup()

        popup = Popup(
            content=popup_content,
            size_hint=(None, None),
            size=(dp(300), dp(180)),
            auto_dismiss=False,
            separator_height=0,
            title="",
            title_size=0,
            background="",
            background_color=(0, 0, 0, 0)
        )

        popup_content.ids.leaveButton.bind(
            on_release=lambda instance: self.confirm_go_back(popup))
        popup_content.ids.stayButton.bind(on_release=popup.dismiss)

        popup.open()

    def confirm_go_back(self, popup):
        if self.review_set_id is not None:
            app = App.get_running_app()
            app.db.delete_review_set(self.review_set_id)
            print("Deleted Review Set:", self.review_set_id)
            self.review_set_id = None

        self.ids.entriesContainer.clear_widgets()
        self.ids.entryCountLabel.text = "0"
        self.ids.termInput.text = ""
        self.ids.definitionInput.text = ""

        popup.dismiss()

        self.manager.transition.direction = "right"
        self.manager.current = "home"

    def add_term(self, instance):
        term = self.ids.termInput.text.strip()
        definition = self.ids.definitionInput.text.strip()

        if not term and not definition:
            print("Please enter both a term and definition.")
            return
        elif not term:
            print("Please enter a term")
            return
        elif not definition:
            print("Please enter its definition")
            return

        if self.review_set_id is None:
            print("No review set selected.")
            return

        app = App.get_running_app()
        term_id = app.db.add_term(self.review_set_id, term, definition)

        entry = TermEntry(term_id=term_id, term=term, definition=definition)
        self.ids.entriesContainer.add_widget(entry)

        count = app.db.get_term_count(self.review_set_id)
        self.ids.entryCountLabel.text = f"{count}"

        self.ids.termInput.text = ""
        self.ids.definitionInput.text = ""

    def edit_entry(self, term_id, term, definition, entry_widget):
        app = App.get_running_app()

        self.ids.termInput.text = term
        self.ids.definitionInput.text = definition

        app.db.delete_term(term_id)
        self.ids.entriesContainer.remove_widget(entry_widget)

        count = app.db.get_term_count(self.review_set_id)
        self.ids.entryCountLabel.text = str(count)
        
    def scan_more(self, *args):
        if self.review_set_id is None:
            return
        scan = self.manager.get_screen("scan")
        scan.append_to = self.review_set_id
        self.manager.transition.direction = "left"
        self.manager.current = "scan"

    def go_to_content_review(self, instance):
        if self.review_set_id is None:
            print("No review set selected.")
            return

        content_review = self.manager.get_screen("contentreview")
        content_review.review_set_id = self.review_set_id
        if self.is_existing_set:
            content_review.ids.reviewSetName.text = self.review_set_name
        content_review.load_entries()

        self.manager.transition.direction = "left"
        self.manager.current = "contentreview"


class GoBackPopup(FloatLayout):
    has_entries = False


class TermEntry(FloatLayout):
    def __init__(self, term_id, term, definition, **kwargs):
        super().__init__(**kwargs)

        self.term_id = term_id
        self.term = term
        self.definition = definition

        self.size_hint_y = None

        term_label = Label(
            text=term,
            font_name="./assets/fonts/PressStart2P.ttf",
            font_size="8sp",
            color=(1, 0.749, 0.2, 1),
            size_hint=(1, None),
            halign="left",
            valign="top",
            pos_hint={"x": 0, "top": 1},
        )
        term_label.bind(
            width=lambda instance, value: setattr(instance, "text_size", (value, None)))
        term_label.bind(
            texture_size=lambda instance, value: setattr(instance, "height", value[1]))

        definition_label = Label(
            text=definition,
            font_name="./assets/fonts/PixelifySans.ttf",
            font_size="10sp",
            color=(0.604, 0.4, 0.894, 0.8),
            size_hint=(1, None),
            halign="left",
            valign="top",
            pos_hint={"x": 0},
        )
        definition_label.bind(
            width=lambda instance, value: setattr(instance, "text_size", (value, None)))
        definition_label.bind(
            texture_size=lambda instance, value: setattr(instance, "height", value[1]))

        divider = Image(
            source="./assets/pageAssets/manual/divider.png",
            size_hint=(1.5, None),
            pos_hint={"center_x": 0.65, "y": 0}
        )
        divider.bind(
            width=lambda instance, value: setattr(instance, "height", value * (3 / 323)))

        self.add_widget(term_label)
        self.add_widget(definition_label)
        self.add_widget(divider)

        def update_height(*args):
            self.height = (
                term_label.height + dp(1)
                + definition_label.height + dp(3)
                + divider.height
            )
            definition_label.top = self.top - term_label.height - dp(1)

        term_label.bind(texture_size=lambda *args: update_height())
        definition_label.bind(texture_size=lambda *args: update_height())
        divider.bind(height=lambda *args: update_height())
        self.bind(pos=update_height, height=update_height)

        Clock.schedule_once(lambda dt: update_height(), 0)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            manual = App.get_running_app().root.get_screen("manual")
            manual.edit_entry(self.term_id, self.term, self.definition, self)
            return True
        return super().on_touch_down(touch)


class ContentReview(Screen):

    review_set_id = None

    def printEdit(self, instance):
        print("Edit works")

    def go_back_manual(self, instance):
        self.manager.transition.direction = "right"
        self.manager.current = "manual"

    def load_entries(self):
        if self.review_set_id is None:
            return

        app = App.get_running_app()
        terms = app.db.get_terms(self.review_set_id)

        self.ids.contentEntriesContainer.clear_widgets()

        for number, (term_id, term, definition) in enumerate(terms, start=1):
            entry = ContentReviewEntry(
                number=number, term=term, definition=definition)
            self.ids.contentEntriesContainer.add_widget(entry)

    def complete_reviewer(self, instance):
        if self.review_set_id is None:
            print("No review set selected.")
            return

        app = App.get_running_app()

        name = self.ids.reviewSetName.text.strip()
        if not name:
            name = "Untitled Review Set"

        app.db.update_review_set_name(self.review_set_id, name)
        print("Saved Review Set:", self.review_set_id, "-", name)

        reviewsets = self.manager.get_screen("reviewsets")
        reviewsets.load_review_sets()

        # Start Bingo using the review set that was just completed.
        game = self.manager.get_screen("bingogame")
        game.start_game(self.review_set_id, name)
        self.manager.transition.direction = "left"
        self.manager.current = "bingogame"


class ContentReviewEntry(FloatLayout):

    def __init__(self, number, term, definition, **kwargs):
        super().__init__(**kwargs)

        self.size_hint_y = None

        entryBackground = Image(
            source="./assets/pageAssets/contentreview/entryBackground.png",
            size_hint=(0.15, None),
            pos_hint={"x": 0, "top": 1},
            fit_mode="contain",
        )
        entryBackground.bind(
            width=lambda instance, value: setattr(instance, "height", value * 37 / 40))
        self.add_widget(entryBackground)

        number_label = Label(
            text=str(number),
            font_name="./assets/fonts/PressStart2P.ttf",
            font_size="11sp",
            color=(1, 1, 1, 1),
            size_hint=(None, None),
            size=(dp(40), dp(40)),
            pos_hint={"x": 0.01},
            halign="center",
            valign="middle"
        )
        self.add_widget(number_label)

        term_label = Label(
            text=term,
            font_name="./assets/fonts/PixelifySans.ttf",
            font_size="17sp",
            color=(1, 0.749, 0.2, 1),
            size_hint=(0.8, None),
            pos_hint={"x": 0.16},
            halign="left",
            valign="top"
        )
        term_label.bind(
            width=lambda instance, value: setattr(instance, "text_size", (value, None)))
        term_label.bind(
            texture_size=lambda instance, value: setattr(instance, "height", value[1]))
        self.add_widget(term_label)

        definition_label = Label(
            text=definition,
            font_name="./assets/fonts/PixelifySans.ttf",
            font_size="12sp",
            color=(0.604, 0.4, 0.894, 1),
            size_hint=(0.8, None),
            pos_hint={"x": 0.16},
            halign="left",
            valign="top"
        )
        definition_label.bind(
            width=lambda instance, value: setattr(instance, "text_size", (value, None)))
        definition_label.bind(
            texture_size=lambda instance, value: setattr(instance, "height", value[1]))
        self.add_widget(definition_label)

        divider = Image(
            source="./assets/pageAssets/contentreview/divider.png",
            size_hint=(1.5, None),
            pos_hint={"center_x": 0.5}
        )
        divider.bind(
            width=lambda instance, value: setattr(instance, "height", value * (3 / 323)))
        self.add_widget(divider)

        def update_layout(*args):
            number_label.top = self.top + dp(4)
            term_label.top = self.top + dp(8)
            definition_label.top = term_label.y - dp(-3)
            divider.y = self.y + dp(8)
            self.height = (
                term_label.height + dp(5) + definition_label.height + dp(10)
            )

        term_label.bind(height=update_layout, y=update_layout)
        definition_label.bind(height=update_layout)
        self.bind(pos=update_layout)

        Clock.schedule_once(lambda dt: update_layout(), 0)


class TextPreviewEntry(FloatLayout):

    def __init__(self, number, term, definition, confidence, **kwargs):
        super().__init__(**kwargs)

        self.size_hint_y = None

        entryBackground = Image(
            source="./assets/pageAssets/contentreview/entryBackground.png",
            size_hint=(0.15, None),
            pos_hint={"x": 0, "top": 1},
            fit_mode="contain",
        )
        entryBackground.bind(
            width=lambda instance, value: setattr(instance, "height", value * 37 / 40))
        self.add_widget(entryBackground)

        number_label = Label(
            text=str(number),
            font_name="./assets/fonts/PressStart2P.ttf",
            font_size="11sp",
            color=(1, 1, 1, 1),
            size_hint=(None, None),
            size=(dp(40), dp(40)),
            pos_hint={"x": 0.01},
            halign="center",
            valign="middle"
        )
        self.add_widget(number_label)

        term_label = Label(
            text=term,
            font_name="./assets/fonts/PixelifySans.ttf",
            font_size="17sp",
            color=(1, 0.749, 0.2, 1),
            size_hint=(0.8, None),
            pos_hint={"x": 0.16},
            halign="left",
            valign="top"
        )
        term_label.bind(
            width=lambda instance, value: setattr(instance, "text_size", (value, None)))
        term_label.bind(
            texture_size=lambda instance, value: setattr(instance, "height", value[1]))
        self.add_widget(term_label)

        definition_label = Label(
            text=f"{definition} ({confidence}% confident)",
            font_name="./assets/fonts/PixelifySans.ttf",
            font_size="12sp",
            color=(0.604, 0.4, 0.894, 1),
            size_hint=(0.8, None),
            pos_hint={"x": 0.16},
            halign="left",
            valign="top"
        )
        definition_label.bind(
            width=lambda instance, value: setattr(instance, "text_size", (value, None)))
        definition_label.bind(
            texture_size=lambda instance, value: setattr(instance, "height", value[1]))
        self.add_widget(definition_label)

        divider = Image(
            source="./assets/pageAssets/contentreview/divider.png",
            size_hint=(1.5, None),
            pos_hint={"center_x": 0.5}
        )
        divider.bind(
            width=lambda instance, value: setattr(instance, "height", value * (3 / 323)))
        self.add_widget(divider)

        def update_layout(*args):
            number_label.top = self.top + dp(4)
            term_label.top = self.top + dp(8)
            definition_label.top = term_label.y - dp(-3)
            divider.y = self.y + dp(8)
            self.height = (
                term_label.height + dp(5) + definition_label.height + dp(10)
            )

        term_label.bind(height=update_layout, y=update_layout)
        definition_label.bind(height=update_layout)
        self.bind(pos=update_layout)

        Clock.schedule_once(lambda dt: update_layout(), 0)


class ReviewSets(Screen):

    def on_enter(self):
        self.load_review_sets()

    def load_review_sets(self):
        app = App.get_running_app()
        review_sets = app.db.get_review_sets()

        self.ids.reviewSetsContainer.clear_widgets()

        for number, (review_set_id, name) in enumerate(review_sets, start=1):
            entry = ReviewSetEntry(
                number=number, review_set_id=review_set_id, name=name)
            self.ids.reviewSetsContainer.add_widget(entry)

    def open_review_set(self, review_set_id, name):
        manual = self.manager.get_screen("manual")
        manual.load_existing_set(review_set_id, name)
        self.manager.transition.direction = "left"
        self.manager.current = "manual"

    def go_back_home(self, instance):
        self.manager.transition.direction = "right"
        self.manager.current = "home"


class ReviewSetEntry(FloatLayout):

    def __init__(self, number, review_set_id, name, **kwargs):
        super().__init__(**kwargs)

        self.review_set_id = review_set_id
        self.name = name

        self.size_hint_y = None

        entryBackground = Image(
            source="./assets/pageAssets/contentreview/entryBackground.png",
            size_hint=(0.15, None),
            pos_hint={"x": 0, "top": 1},
            fit_mode="contain",
        )
        entryBackground.bind(
            width=lambda instance, value: setattr(instance, "height", value * 37 / 40))
        self.add_widget(entryBackground)

        number_label = Label(
            text=str(number),
            font_name="./assets/fonts/PressStart2P.ttf",
            font_size="11sp",
            color=(1, 1, 1, 1),
            size_hint=(None, None),
            size=(dp(40), dp(40)),
            pos_hint={"x": 0.01},
            halign="center",
            valign="middle",
            
        )
        self.add_widget(number_label)

        name_label = Label(
            text=name,
            font_name="./assets/fonts/PixelifySans.ttf",
            font_size="17sp",
            color=(1, 0.749, 0.2, 1),
            size_hint=(0.68, None),
            pos_hint={"x": 0.16},
            halign="left",
            valign="middle"
        )
        name_label.bind(
            width=lambda instance, value: setattr(instance, "text_size", (value, None)))
        name_label.bind(
            texture_size=lambda instance, value: setattr(instance, "height", value[1]))
        self.add_widget(name_label)

        delete_button = Button(
            text="X",
            font_name="./assets/fonts/PressStart2P.ttf",
            font_size="12sp",
            color=(1, 0.4, 0.4, 1),
            size_hint=(None, None),
            size=(dp(28), dp(28)),
            pos_hint={"right": 0.97, "top": 1},
            background_color=(0, 0, 0, 0),
            background_normal="",
            background_down=""
        )
        delete_button.bind(on_release=self.delete_entry)
        self.add_widget(delete_button)
        self.delete_button = delete_button

        divider = Image(
            source="./assets/pageAssets/contentreview/divider.png",
            size_hint=(1.5, None),
            pos_hint={"center_x": 0.5}
        )
        divider.bind(
            width=lambda instance, value: setattr(instance, "height", value * (3 / 323)))
        self.add_widget(divider)

        def update_layout(*args):
            number_label.top = self.top + dp(4)
            name_label.top = self.top + dp(8)
            divider.y = self.y + dp(8)
            self.height = max(entryBackground.height, name_label.height) + dp(15)

        name_label.bind(height=update_layout, y=update_layout)
        self.bind(pos=update_layout)

        Clock.schedule_once(lambda dt: update_layout(), 0)

    def on_touch_up(self, touch):
        if super().on_touch_up(touch):
            return True

        if self.delete_button.collide_point(*touch.pos):
            return False

        moved = ((touch.x - touch.ox) ** 2 + (touch.y - touch.oy) ** 2) ** 0.5
        if (self.collide_point(*touch.pos)
                and self.collide_point(touch.ox, touch.oy)
                and moved < dp(10)):
            reviewsets = App.get_running_app().root.get_screen("reviewsets")
            reviewsets.open_review_set(self.review_set_id, self.name)
            return True

        return False

    def delete_entry(self, instance):
        app = App.get_running_app()
        app.db.delete_review_set(self.review_set_id)
        reviewsets = app.root.get_screen("reviewsets")
        reviewsets.load_review_sets()


class BingoGame(Screen):
    """Term-matching Bingo game based on the completed review set."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.review_set_id = None
        self.terms = []
        self.question_order = []
        self.question_index = 0
        self.score = 0
        self.streak = 0
        self._answered = False

        with self.canvas.before:
            Color(0.047, 0, 0.129, 1)
            self._game_bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        root = BoxLayout(orientation="vertical", padding=(dp(16), dp(18)), spacing=dp(8))
        top = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        back = Button(text="‹", font_name=FONT_PX, font_size="18sp", color=(1, 0.2, 0.8, 1),
                      size_hint_x=None, width=dp(42), background_normal="", background_color=(0,0,0,0))
        back.bind(on_release=self.go_back)
        top.add_widget(back)
        top.add_widget(Label(text="BINGO!", font_name=FONT_PX, font_size="16sp", color=AMBER))
        top.add_widget(Widget(size_hint_x=None, width=dp(42)))
        root.add_widget(top)

        self.stats_label = Label(text="⭐ Score: 0 / 0       Question 1 / 1", font_name=FONT,
                                 font_size="12sp", size_hint_y=None, height=dp(30))
        root.add_widget(self.stats_label)
        self.definition_label = Label(text="Complete a reviewer to start playing.", font_name=FONT,
                                      font_size="14sp", halign="center", valign="middle",
                                      size_hint_y=None, height=dp(110), color=(1,1,1,1))
        self.definition_label.bind(size=lambda w, size: setattr(w, "text_size", (size[0]-dp(16), size[1])))
        with self.definition_label.canvas.before:
            Color(0.10, 0.06, 0.25, 1)
            self._definition_bg = RoundedRectangle(pos=self.definition_label.pos,
                                                    size=self.definition_label.size, radius=[dp(12)])
        self.definition_label.bind(pos=self._update_definition_bg, size=self._update_definition_bg)
        root.add_widget(self.definition_label)

        self.grid = GridLayout(cols=3, spacing=dp(7), padding=dp(4), size_hint_y=0.68)
        root.add_widget(self.grid)
        self.feedback_label = Label(text="", font_name=FONT, font_size="13sp", size_hint_y=None, height=dp(42))
        root.add_widget(self.feedback_label)
        self.streak_label = Label(text="Streak: 0", font_name=FONT_PX, font_size="10sp",
                                  color=(0.7, 0.4, 1, 1), size_hint_y=None, height=dp(30))
        root.add_widget(self.streak_label)
        self.add_widget(root)

    def _update_bg(self, *args):
        self._game_bg.pos, self._game_bg.size = self.pos, self.size

    def _update_definition_bg(self, *args):
        self._definition_bg.pos = self.definition_label.pos
        self._definition_bg.size = self.definition_label.size

    def go_back(self, *args):
        self.manager.transition.direction = "right"
        self.manager.current = "reviewsets"

    def start_game(self, review_set_id, name=""):
        app = App.get_running_app()
        self.review_set_id = review_set_id
        self.terms = [(term, definition) for _, term, definition in app.db.get_terms(review_set_id)
                      if term.strip() and definition.strip()]
        self.question_order = list(range(len(self.terms)))
        random.shuffle(self.question_order)
        self.question_index = 0
        self.score = 0
        self.streak = 0
        self._answered = False
        self.feedback_label.text = ""
        if not self.terms:
            self.definition_label.text = "This reviewer has no terms yet. Go back and add some first."
            self.grid.clear_widgets()
            self.stats_label.text = "Score: 0 / 0"
            self.streak_label.text = "Streak: 0"
            return
        self._show_question()

    def _show_question(self):
        if self.question_index >= len(self.question_order):
            self.definition_label.text = "REVIEW COMPLETE!\nFinal score: %d / %d" % (self.score, len(self.terms))
            self.grid.clear_widgets()
            again = Button(text="PLAY AGAIN", font_name=FONT_PX, font_size="11sp", color=AMBER,
                           background_normal="", background_color=(0.22, 0.08, 0.55, 1))
            again.bind(on_release=lambda *_: self.start_game(self.review_set_id))
            back = Button(text="BACK TO REVIEW SETS", font_name=FONT, font_size="12sp", color=(1,1,1,1),
                          background_normal="", background_color=(0.22, 0.08, 0.55, 1))
            back.bind(on_release=self.go_back)
            self.grid.add_widget(again)
            self.grid.add_widget(back)
            self.feedback_label.text = ""
            self.stats_label.text = "Score: %d / %d" % (self.score, len(self.terms))
            self.streak_label.text = "Best play is continuous correct answers!"
            return

        self._answered = False
        correct_index = self.question_order[self.question_index]
        correct_term, definition = self.terms[correct_index]
        self.definition_label.text = definition
        self.stats_label.text = "⭐ Score: %d / %d       Question %d / %d" % (
            self.score, len(self.terms), self.question_index + 1, len(self.terms))
        self.streak_label.text = "Streak: %d" % self.streak
        self.feedback_label.text = "Tap the term that matches the definition."

        distractors = [item for i, item in enumerate(self.terms) if i != correct_index]
        random.shuffle(distractors)
        options = [(correct_term, True)] + [(term, False) for term, _ in distractors[:7]]
        while len(options) < 8:
            options.append(("—", False))
        random.shuffle(options)
        self.grid.clear_widgets()
        for index, (term, is_correct) in enumerate(options):
            if index == 4:
                free = Label(text="⭐\nFREE!", font_name=FONT_PX, font_size="10sp", color=AMBER)
                self.grid.add_widget(free)
            if term == "—":
                btn = Button(text=term, disabled=True)
            else:
                btn = Button(text=term, font_name=FONT, font_size="11sp", color=(0.78,0.65,1,1),
                             background_normal="", background_down="",
                             background_color=(0.10,0.04,0.30,1),
                             border=(dp(2), dp(2), dp(2), dp(2)))
                btn.bind(on_release=lambda instance, ok=is_correct, answer=correct_term: self.check_answer(instance, ok, answer))
            self.grid.add_widget(btn)

    def check_answer(self, button, is_correct, correct_term):
        if self._answered:
            return
        self._answered = True
        for child in self.grid.children:
            if isinstance(child, Button):
                child.disabled = True
        if is_correct:
            self.score += 1
            self.streak += 1
            button.background_color = (0.05, 0.45, 0.30, 1)
            self.feedback_label.text = "✓ Correct!  " + correct_term
            self.feedback_label.color = (0.25, 1, 0.65, 1)
        else:
            self.streak = 0
            button.background_color = (0.55, 0.08, 0.18, 1)
            self.feedback_label.text = "Incorrect! Answer: " + correct_term
            self.feedback_label.color = (1, 0.3, 0.4, 1)
            for child in self.grid.children:
                if isinstance(child, Button) and child.text == correct_term:
                    child.background_color = (0.05, 0.45, 0.30, 1)
        self.streak_label.text = "Streak: %d" % self.streak
        self.stats_label.text = "⭐ Score: %d / %d       Question %d / %d" % (
            self.score, len(self.terms), self.question_index + 1, len(self.terms))
        Clock.schedule_once(self._next_question, 1.0)

    def _next_question(self, dt):
        self.question_index += 1
        self._show_question()


class Result(Screen):
    pass

AMBER = (1, 0.749, 0.2, 1)
BG = (0.07, 0.06, 0.12, 1)
FONT = "./assets/fonts/PixelifySans.ttf"
FONT_PX = "./assets/fonts/PressStart2P.ttf"


def _label(markup, size="12sp"):
    lbl = Label(text=markup, markup=True, font_name=FONT, font_size=size,
                color=(1, 1, 1, 1), size_hint_y=None, halign="left", valign="top")
    lbl.bind(width=lambda i, v: setattr(i, "text_size", (v, None)))
    lbl.bind(texture_size=lambda i, v: setattr(i, "height", v[1] + dp(8)))
    return lbl


def _top_button(text, cb):
    b = Button(text=text, font_name=FONT_PX, font_size="10sp", color=AMBER,
               size_hint=(None, 1), width=dp(70), background_normal="",
               background_down="", background_color=(0, 0, 0, 0))
    b.bind(on_release=lambda *_: cb())
    return b

TEAL = (0.25, 0.78, 0.55, 1)


def _src_name(w):
    return {"filled": "reconstruction", "typed": "typed text"}.get(
        getattr(w, "src", "ocr"), "OCR")


def _notice(text):
    lbl = Label(text=text, font_name=FONT, font_size="13sp",
                halign="center", valign="middle")
    lbl.bind(size=lambda i, v: setattr(i, "text_size", v))
    Popup(title="", separator_height=0, content=lbl, size_hint=(0.85, 0.3)).open()

def send_to_manual(manager, terms):
    app = App.get_running_app()
    scan = manager.get_screen("scan")
    manual = manager.get_screen("manual")

    if scan.append_to is not None and manual.review_set_id == scan.append_to:
        review_set_id = scan.append_to          # second picture: add to the same set
    else:
        review_set_id = app.db.create_review_set("Untitled Review Set")
        manual.review_set_id = review_set_id
        manual.is_existing_set = False
        manual.ids.entriesContainer.clear_widgets()
        manual.ids.termInput.text = ""
        manual.ids.definitionInput.text = ""
    scan.append_to = None

    for item in terms:
        term = item.get("term", "").strip()
        definition = item.get("definition", "").strip()
        if not term or not definition:
            continue
        term_id = app.db.add_term(review_set_id, term, definition)
        manual.ids.entriesContainer.add_widget(
            TermEntry(term_id=term_id, term=term, definition=definition))

    manual.ids.entryCountLabel.text = str(app.db.get_term_count(review_set_id))
    manager.transition.direction = "left"
    manager.current = "manual"
class PageScreen(Screen):
    """Top bar (back / title / optional right button), scrolling body, bottom buttons."""

    def __init__(self, title, right_text=None, bottoms=(), **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*BG)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd_bg, size=self._upd_bg)

        root = BoxLayout(orientation="vertical")
        root.add_widget(Widget(size_hint_y=None, height=dp(50)))

        bar = BoxLayout(size_hint_y=None, height=dp(52), padding=dp(6), spacing=dp(6))
        bar.add_widget(_top_button("<", self.on_back_pressed))
        bar.add_widget(Label(text=title, font_name=FONT_PX, font_size="10sp", color=AMBER))
        self.right_btn = None
        if right_text:
            self.right_btn = _top_button(right_text, self.on_right_pressed)
            bar.add_widget(self.right_btn)
        else:
            bar.add_widget(Widget(size_hint_x=None, width=dp(70)))
        root.add_widget(bar)

        scroll = ScrollView(bar_width=dp(4))
        self.box = BoxLayout(orientation="vertical", size_hint_y=None,
                             padding=dp(12), spacing=dp(8))
        self.box.bind(minimum_height=self.box.setter("height"))
        scroll.add_widget(self.box)
        root.add_widget(scroll)

        if bottoms:
            row = BoxLayout(size_hint_y=None, height=dp(52),
                            spacing=dp(6), padding=(dp(6), 0))
            for text, method, color in bottoms:
                btn = Button(text=text, font_name=FONT_PX, font_size="9sp",
                             color=BG, background_normal="", background_down="",
                             background_color=color)
                btn.bind(on_release=lambda *_, m=method: getattr(self, m)())
                row.add_widget(btn)
            root.add_widget(row)

        self.add_widget(root)

    def _upd_bg(self, *args):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def on_back_pressed(self):
        pass

    def on_right_pressed(self):
        pass
    
RED = (1, 0.333, 0.333, 1)
ORANGE = (1, 0.663, 0.251, 1)
RED_HEX, ORANGE_HEX, AMBER_HEX, DIM_HEX = "ff5555", "ffa940", "ffbf33", "9a8fb5"


def _sev(p):
    return RED_HEX if p >= 0.8 else ORANGE_HEX


def _sev_rgba(p):
    return RED if p >= 0.8 else ORANGE


class Meter(Widget):
    def __init__(self, value, color, **kwargs):
        super().__init__(size_hint_y=None, height=dp(6), **kwargs)
        self.value = max(0.0, min(1.0, value))
        with self.canvas:
            Color(1, 1, 1, 0.12)
            self._track = Rectangle()
            Color(*color)
            self._fill = Rectangle()
        self.bind(pos=self._upd, size=self._upd)

    def _upd(self, *args):
        self._track.pos, self._track.size = self.pos, self.size
        self._fill.pos = self.pos
        self._fill.size = (self.width * self.value, self.height)



class Card(BoxLayout):
    """Headline + meter. Tap to show or hide the full calculation."""

    def __init__(self, head, pct, color, body, **kwargs):
        super().__init__(orientation="vertical", size_hint_y=None,
                         padding=(dp(10), dp(8)), spacing=dp(4), **kwargs)
        self.bind(minimum_height=self.setter("height"))
        with self.canvas.before:
            Color(1, 1, 1, 0.06)
            self._bg = RoundedRectangle(radius=[dp(4)])
        self.bind(pos=self._upd, size=self._upd)

        self.add_widget(_label(head, "13sp"))
        self.add_widget(Meter(pct, color))
        self.body = _label(body, "10sp")
        self.hint = _label(f"[color={DIM_HEX}]tap to see the calculation[/color]", "9sp")
        self.add_widget(self.hint)
        self._open = False

    def _upd(self, *args):
        self._bg.pos, self._bg.size = self.pos, self.size

    def on_touch_up(self, touch):
        if self.collide_point(*touch.pos) and self.collide_point(touch.ox, touch.oy):
            moved = ((touch.x - touch.ox) ** 2 + (touch.y - touch.oy) ** 2) ** 0.5
            if moved < dp(10):
                if self._open:
                    self.remove_widget(self.body)
                    self.add_widget(self.hint)
                else:
                    self.remove_widget(self.hint)
                    self.add_widget(self.body)
                self._open = not self._open
                return True
        return super().on_touch_up(touch)
class Detection(PageScreen):
    """OCR text with the parts the model thinks are damaged highlighted."""
    det = None
    back_to = "scan"
    editing = False
    editor = None

    def __init__(self, **kwargs):
        super().__init__(
            title="DAMAGE CHECK", right_text="EDIT",
            bottoms=(("RECONSTRUCT", "on_reconstruct", AMBER),
                     ("SPLIT TERMS", "on_split", TEAL)),
            **kwargs)

    def _has_text(self):
        return self.det is not None and bool(self.det.words)

    # ---------- navigation ----------
    def on_back_pressed(self):
        if self.editing:
            self.show(self.det)          # leave the editor without saving
            return
        self.manager.transition.direction = "right"
        self.manager.current = self.back_to

    # ---------- manual editing ----------
    def on_right_pressed(self):
        if self.editing:
            self._save_edit()
        else:
            self._start_edit()

    def _start_edit(self):
        self.editing = True
        self.right_btn.text = "SAVE"
        self.box.clear_widgets()
        self.box.add_widget(_label(
            "Fix the text yourself, then tap SAVE to run the damage check again. "
            "Words you type are trusted, so they are not flagged.\n"
            f"[size=10sp][color={DIM_HEX}]For SPLIT TERMS, put each item on its own line "
            f"as 'Term - definition'.[/color][/size]", size="11sp"))
        words = self.det.words if self.det else []
        self.editor = TextInput(
            text=words_to_text(words), font_name=FONT, font_size="14sp",
            foreground_color=(1, 1, 1, 1), cursor_color=AMBER,
            background_normal="", background_active="",
            background_color=(1, 1, 1, 0.08),
            padding=(dp(8), dp(8)), size_hint_y=None, height=dp(300))
        self.editor.bind(minimum_height=lambda i, v: setattr(i, "height", max(v, dp(300))))
        self.box.add_widget(self.editor)

    def _save_edit(self):
        text = self.editor.text if self.editor else ""
        old = self.det.words if self.det else []
        has_conf = self.det.has_conf if self.det else True
        try:
            det = detect(text_to_words(old, text), has_conf)
        except Exception:
            import traceback
            traceback.print_exc()
            _notice("Could not check the edited text.")
            return
        self.show(det)

    # ---------- bottom buttons ----------
    def on_reconstruct(self):
        if self.editing:
            self._save_edit()
        if not self._has_text():
            return
        processing = self.manager.get_screen("processing")
        processing.mode = "reconstruct"
        processing.detection = self.det
        self.manager.transition.direction = "left"
        self.manager.current = "processing"

    def on_split(self):
        if self.editing:
            self._save_edit()
        if not self._has_text():
            return
        confs = [w.conf for w in self.det.words if w.conf >= 0]
        mean = sum(confs) / len(confs) if confs else 0.0
        terms = extract_terms(words_to_text(self.det.words), {}, mean)
        if not terms:
            _notice("No terms found. Put each item on its own line as "
                    "'Term - definition'. Use EDIT to fix the text.")
            return
        send_to_manual(self.manager, terms)

    # ---------- display ----------
    @staticmethod
    def _marked_text(det):
        words, toks = det.words, det.tokens
        role = {}
        for g in det.gaps:
            for k in range(g.position - 2, g.position + 2):
                role.setdefault(k, "ctx")
        for i, t in enumerate(toks):
            if t.flagged:
                for k in range(i - 2, i + 3):
                    role.setdefault(k, "ctx")
        for i, t in enumerate(toks):
            if t.flagged:
                role[i] = "bad"

        gap_at = {g.position: g for g in det.gaps}
        lines = {}
        for i, w in enumerate(words):
            lines.setdefault(w.line, []).append(i)

        out = []
        for _, idxs in sorted(lines.items()):
            parts, run, best = [], [], [0.0]

            def flush():
                if run:
                    parts.append(
                        " ".join(run) +
                        f"[size=9sp][color={_sev(best[0])}] @{round(best[0] * 100)}%"
                        f"[/color][/size]")
                    run.clear()
                    best[0] = 0.0

            for i in idxs:
                r = role.get(i)
                if i in gap_at:
                    g = gap_at[i]
                    run.append(f"[color={RED_HEX}][b]&bl;missing {g.est_words}&br;[/b][/color]")
                    best[0] = max(best[0], g.p_gap)
                    r = r or "ctx"
                txt = esc(words[i].text)
                if r == "bad":
                    run.append(f"[color={RED_HEX}][b][u]{txt}[/u][/b][/color]")
                    best[0] = max(best[0], toks[i].p_damage)
                elif r == "ctx":
                    run.append(f"[color={AMBER_HEX}]{txt}[/color]")
                else:
                    flush()
                    parts.append(txt)
            flush()
            out.append(" ".join(parts))
        return "\n".join(out)

    @staticmethod
    def _token_detail(i, t):
        W = WEIGHTS
        conf = t.word.conf
        if t.bits is not None:
            lm = (f"surprisal = {t.bits:.1f} bits, z-score {t.z_lm:+.2f}\n"
                  f"   f_lm = sigmoid({t.z_lm:+.2f}) = {t.f_lm:.2f}")
        else:
            lm = "no surprisal available, so f_lm = 0.50 (neutral)"
        return (f"{_src_name(t.word)} confidence {conf:.0f}%\n"
                f"   f_ocr = 1 - {conf:.0f}/100 = {t.f_ocr:.2f}\n"
                f"{lm}\n"
                f"shape check: {esc(t.why)}\n"
                f"   f_shape = {t.f_shape:.2f}\n"
                f"z = {W['bias']} + {W['ocr']}*{t.f_ocr:.2f} + {W['lm']}*{t.f_lm:.2f} "
                f"+ {W['shape']}*{t.f_shape:.2f} = {t.z:+.2f}\n"
                f"P(damaged) = sigmoid({t.z:+.2f}) = [b]{t.p_damage*100:.0f}%[/b]")

    @staticmethod
    def _gap_detail(g, stats):
        return (f"gap = {g.gap_px:.0f}px, median gap = {stats['med_gap']:.0f}px\n"
                f"   ratio = {g.gap_px:.0f} / {stats['med_gap']:.0f} = {g.ratio:.2f}\n"
                f"missing words = round({g.gap_px:.0f} / ({stats['med_w']:.0f} + "
                f"{stats['med_gap']:.0f})) = {g.est_words}\n"
                f"P(gap) = sigmoid({GAP_K} * ({g.ratio:.2f} - {GAP_MID})) = "
                f"[b]{g.p_gap*100:.0f}%[/b]")

    def show(self, det, back=None):
        if back:
            self.back_to = back
        self.editing = False
        self.editor = None
        if self.right_btn is not None:
            self.right_btn.text = "EDIT"
        self.det = det
        self.box.clear_widgets()

        if det is None or not det.words:
            self.box.add_widget(_label(
                "Nothing to show. Tap EDIT to type the text yourself, or go back."))
            return

        toks = [(i, t) for i, t in enumerate(det.tokens) if t.flagged]
        n_bad, n_gap = len(toks), len(det.gaps)
        stage = ("after reconstruction" if self.back_to == "reconstructed"
                 else "straight from OCR")

        if det.has_conf:
            mean = sum(w.conf for w in det.words) / len(det.words)
            conf_txt = f"mean confidence {mean:.0f}%"
        else:
            conf_txt = "this ML Kit build gives no per-word confidence"
        self.box.add_widget(_label(
            f"[b][color={AMBER_HEX}]{n_bad} damaged word(s)  |  {n_gap} gap(s)[/color][/b]\n"
            f"[size=10sp][color={DIM_HEX}]{stage}: {len(det.words)} words, "
            f"{conf_txt}[/color][/size]"))

        self.box.add_widget(_label(
            f"[color={RED_HEX}][b][u]red[/u][/b][/color] damaged word   "
            f"[color={AMBER_HEX}]amber[/color] words around it   "
            f"[color={RED_HEX}][b]&bl;missing&br;[/b][/color] words lost here\n"
            f"[size=10sp][color={DIM_HEX}]@ = highest damage score in that "
            f"highlighted phrase[/color][/size]", size="10sp"))

        self.box.add_widget(_label(self._marked_text(det), size="14sp"))

        if n_bad + n_gap == 0:
            self.box.add_widget(_label("No damaged words or gaps detected."))
            return

        self.box.add_widget(_label(
            f"[b][color={AMBER_HEX}]HOW SURE, AND WHY[/color][/b]\n"
            f"[size=10sp][color={DIM_HEX}]most damaged first, tap a card[/color][/size]"))

        W = WEIGHTS
        cards = []
        for i, t in toks:
            reasons = [
                (W["ocr"] * t.f_ocr, f"{_src_name(t.word)} only {t.word.conf:.0f}% sure"),
                (W["lm"] * t.f_lm, "unlikely given the words around it"),
                (W["shape"] * t.f_shape, esc(t.why)),
            ]
            main = max(reasons)[1]
            head = (f"[b]{esc(t.word.text)}[/b]  "
                    f"[color={_sev(t.p_damage)}]{t.p_damage*100:.0f}% damaged[/color]\n"
                    f"[size=10sp][color={DIM_HEX}]mainly: {main}[/color][/size]")
            cards.append((t.p_damage, Card(head, t.p_damage, _sev_rgba(t.p_damage),
                                           self._token_detail(i, t))))
        for g in det.gaps:
            nxt = det.words[g.position].text if g.position < len(det.words) else ""
            head = (f"[b]~{g.est_words} word(s) missing[/b] before '{esc(nxt)}'  "
                    f"[color={_sev(g.p_gap)}]{g.p_gap*100:.0f}%[/color]\n"
                    f"[size=10sp][color={DIM_HEX}]gap is {g.ratio:.1f}x the usual "
                    f"spacing[/color][/size]")
            cards.append((g.p_gap, Card(head, g.p_gap, _sev_rgba(g.p_gap),
                                        self._gap_detail(g, det.stats))))

        for _, card in sorted(cards, key=lambda c: -c[0]):
            self.box.add_widget(card)

        self.box.add_widget(_label(
            "These percentages come straight from the formulas. The weights are "
            "hand-set, so treat them as scores, not calibrated probabilities.", size="9sp"))

class Reconstructed(PageScreen):
    result = None
    source_det = None
    source_back = "scan"

    def __init__(self, **kwargs):
        super().__init__(title="RECONSTRUCTED", right_text="HOW",
                         bottoms=(("DAMAGE CHECK", "on_recheck", AMBER),), **kwargs)

    def on_back_pressed(self):
        # go back to the damage check that this reconstruction came from
        self.manager.get_screen("detection").show(self.source_det, self.source_back)
        self.manager.transition.direction = "right"
        self.manager.current = "detection"

    def on_right_pressed(self):
        if self.result is None:
            return
        how = self.manager.get_screen("how")
        how.show(self.result)
        self.manager.transition.direction = "left"
        self.manager.current = "how"

    def on_recheck(self):
        if self.result is None:
            return
        processing = self.manager.get_screen("processing")
        processing.mode = "recheck"
        processing.result = self.result
        self.manager.transition.direction = "left"
        self.manager.current = "processing"

    def show(self, result, det=None, back="scan"):
        self.result = result
        self.source_det = det
        self.source_back = back
        self.box.clear_widgets()

        if result is None:
            self.box.add_widget(_label("Reconstruction failed."))
            return

        slots = {s.id: s for s in result.slots}

        def fill(m):
            s = slots.get(int(m.group(1)))
            conf = f" {s.recon_conf * 100:.0f}%" if s else ""
            return (f"[color=ffbf33][b]{m.group(2)}[/b][/color]"
                    f"[size=9sp][color=ffbf33]{conf}[/color][/size]")

        page = re.sub(r"\{\{(\d+)\|([^}]*)\}\}", fill, esc(result.annotated))

        self.box.add_widget(_label(
            "[color=ffbf33][b]orange[/b][/color] = filled in by the language model "
            "(with its confidence). Tap HOW to see the calculation, or DAMAGE CHECK "
            "to check the new text."))
        self.box.add_widget(_label(page, size="13sp"))
        self.box.add_widget(_label(f"{len(result.slots)} spot(s) filled.", size="10sp"))

class How(PageScreen):
    def __init__(self, **kwargs):
        super().__init__(title="HOW IT WORKED", **kwargs)

    def on_back_pressed(self):
        self.manager.transition.direction = "right"
        self.manager.current = "reconstructed"

    def show(self, result):
        self.box.clear_widgets()
        for block in build_how_blocks(result):
            self.box.add_widget(_label(block, size="11sp"))
class Bingo(App):

    def build(self):
        Window.softinput_mode = "below_target"

        self.db = Database(os.path.join(self.user_data_dir, "bingo.db"))

        sm = ScreenManager()

        home = Home(name="home")
        scan = Scan(name="scan")
        imagepreview = ImagePreview(name="imagepreview")
        processing = Processing(name="processing")
        extractedcontent = ExtractedContent(name="extractedcontent")
        report = Report(name="report")
        manual = Manual(name="manual")
        contentreview = ContentReview(name="contentreview")
        reviewsets = ReviewSets(name="reviewsets")
        bingogame = BingoGame(name="bingogame")
        result = Result(name="result")
        detection = Detection(name="detection")
        reconstructed = Reconstructed(name="reconstructed")
        how = How(name="how")

        contentreview.ids.edit_button.bind(on_release=contentreview.printEdit)
        contentreview.ids.conRevBackButton.bind(on_release=contentreview.go_back_manual)
        contentreview.ids.addTermButton.bind(on_release=contentreview.go_back_manual)
        contentreview.ids.completeReviewerButton.bind(on_release=contentreview.complete_reviewer)

        manual.ids.manualBackButton.bind(on_release=manual.go_back_home)
        manual.ids.addTermButton.bind(on_release=manual.add_term)
        manual.ids.continueButton.bind(on_release=manual.go_to_content_review)

        reviewsets.ids.reviewSetsBackButton.bind(on_release=reviewsets.go_back_home)

        for screen in (home, scan, imagepreview, processing, extractedcontent,
                       report, manual, contentreview, reviewsets, bingogame, result,
                       detection, reconstructed, how):
            sm.add_widget(screen)

        sm.current = "home"
        return sm

    def on_start(self):
        # Load the Java classes on the main thread so the OCR worker thread can use them.
        try:
            ocr_engine.init()
        except Exception:
            import traceback
            traceback.print_exc()
        Window.bind(on_keyboard=self.on_back)

    def on_pause(self):
        return True      # required: the camera / picker intents pause the app

    def on_resume(self):
        pass

    def on_back(self, window, key, *args):
        if key != 27:    # Android back button
            return False

        sm = self.root
        cur = sm.current

        if cur == "home":
            return False                       # let Android close the app
        if cur == "processing":
            return True                        # ignore while OCR is running
        if cur == "manual":
            sm.get_screen("manual").go_back_home(None)
            return True
        if cur == "contentreview":
            sm.get_screen("contentreview").go_back_manual(None)
            return True
        
        if cur in ("detection", "reconstructed"):
            sm.get_screen(cur).on_back_pressed()
            return True

        if cur == "scan":
            sm.get_screen("scan").go_back_home()
            return True

        target = {
            "scan": "home",
            "imagepreview": "scan",
            "extractedcontent": "scan",
            "report": "extractedcontent",
            "how": "reconstructed",
            "reviewsets": "home",
        }.get(cur, "home")
        sm.transition.direction = "right"
        sm.current = target
        return True


if __name__ == "__main__":
    Bingo().run()