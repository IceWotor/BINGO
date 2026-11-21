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
from kivy.properties import StringProperty, BooleanProperty

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

from reconstruction.pair_state import Pair
from reconstruction.pair_ui import PairCard

from reconstruction.damage import WEIGHTS, GAP_K, GAP_MID
from reconstruction.reconstruct import detect, reconstruct_words
from reconstruction.report import build_report_blocks, build_how_blocks, esc
from reconstruction.pairs import split_entries
from extracted_text import ExtractedText

from setup_screen import BingoSetup
from game_result import GameResult
from bingo_game import BingoGame

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
        preview.image_name = phone_io.last_name or os.path.basename(path)
        self.manager.transition.direction = "left"
        self.manager.current = "imagepreview"
        
class ImagePreview(Screen):

    image_path = ""
    image_name = ""
    
    def take_photo_again(self):
        self.manager.transition.direction = "right"
        self.manager.current = "scan"

    def on_enter(self):
        self.ids.preview_image.source = self.image_path
        self.ids.preview_image.reload()

    def use_photo(self):
        self.manager.transition.direction = "left"
        self.manager.current = "processing"

class Processing(Screen):
    """Loading screen: OCR, damage detection and pairing, then the Extracted Text page."""

    def on_enter(self):
        path = self.manager.get_screen("imagepreview").image_path
        try:
            ocr_engine.run_ocr_async(path, self._on_ocr)
        except Exception:
            import traceback
            traceback.print_exc()
            self._failed("Could not read the photo.")

    def _on_ocr(self, words, has_conf, error):
        if error or words is None:
            print("OCR failed:", error)
            self._failed("Could not read any text from this photo.")
            return
        threading.Thread(target=self._detect, args=(words, has_conf), daemon=True).start()

    def _detect(self, words, has_conf):
        try:
            det = detect(words, has_conf)
            entries = split_entries(det) if det.words else []
        except Exception:
            import traceback
            traceback.print_exc()
            self._failed("Something went wrong while reading the text.")
            return
        if not det.words:
            self._failed("No text was found in this photo.")
            return
        self._show(entries, det)

    @mainthread
    def _failed(self, message):
        self.manager.transition.direction = "right"
        self.manager.current = "scan"
        _notice(message)

    @mainthread
    def _show(self, entries, det):
        preview = self.manager.get_screen("imagepreview")
        name = preview.image_name or os.path.basename(preview.image_path)
        self.manager.get_screen("extractedtext").load(entries, det, name)
        self.manager.transition.direction = "left"
        self.manager.current = "extractedtext"
        
LEGEND = ("[color=ffd23f]yellow[/color] / [color=ff5555]red[/color] = looks damaged (% sure)   "
          "[color=3fc78c]green[/color] = filled in (% confidence)\n"
          "Tap a definition to edit it. Wrap words in <<double angle brackets>> to mark them "
          "for reconstruction.")


class ExtractedContent(Screen):
    ocr_text = StringProperty("")
    source_name = StringProperty("")
    has_incomplete = BooleanProperty(False)
    cards = None

    def back_to_scan(self):
        self.manager.transition.direction = "right"
        self.manager.current = "extractedtext"

    def load_pairs(self, entries, filename=""):
        os.chdir(BASE_DIR)
        self.source_name = filename
        box = self.ids.textEntriesContainer
        box.clear_widgets()
        self.cards = []
        entries = [e for e in entries if e.term or e.def_words]
        if not entries:
            self.ocr_text = "No terms could be extracted."
            self.has_incomplete = False
            return
        self.ocr_text = ""
        for e in entries:
            card = PairCard(Pair(e.term, list(e.def_words), e.det), self.remove_card)
            card.on_change = self.update_state
            self.cards.append(card)
            box.add_widget(card)
        self.update_state()

    def update_state(self, *_):
        self.has_incomplete = any(c.incomplete for c in self.cards or [])

    def remove_card(self, card):
        if card in self.cards:
            self.cards.remove(card)
        self.ids.textEntriesContainer.remove_widget(card)
        if not self.cards:
            self.ocr_text = "No pairs left."
        self.update_state()

    def continue_to_manual(self):
        if self.has_incomplete:
            return
        terms = []
        for card in self.cards or []:
            card.commit_all()
            term = card.pair.term.strip()
            definition = card.pair.definition_text().strip()
            if term and definition:
                terms.append({"term": term, "definition": definition})
        if not terms:
            _notice("Nothing to add yet. Each pair needs a term and a definition.")
            return
        send_to_manual(self.manager, terms)
        
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
        setup = self.manager.get_screen("bingosetup")
        setup.open_for(self.review_set_id)
        self.manager.transition.direction = "left"
        self.manager.current = "bingosetup"


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
        extractedtext = ExtractedText(name="extractedtext")
        manual = Manual(name="manual")
        contentreview = ContentReview(name="contentreview")
        reviewsets = ReviewSets(name="reviewsets")
        bingogame = BingoGame(name="bingogame")
        result = Result(name="result")
        bingosetup = BingoSetup(name="bingosetup")
        gameresult = GameResult(name="gameresult")

        contentreview.ids.edit_button.bind(on_release=contentreview.printEdit)
        contentreview.ids.conRevBackButton.bind(on_release=contentreview.go_back_manual)
        contentreview.ids.addTermButton.bind(on_release=contentreview.go_back_manual)
        contentreview.ids.completeReviewerButton.bind(on_release=contentreview.complete_reviewer)

        manual.ids.manualBackButton.bind(on_release=manual.go_back_home)
        manual.ids.addTermButton.bind(on_release=manual.add_term)
        manual.ids.continueButton.bind(on_release=manual.go_to_content_review)

        reviewsets.ids.reviewSetsBackButton.bind(on_release=reviewsets.go_back_home)

        for screen in (home, scan, imagepreview, processing, extractedcontent, extractedtext, manual, contentreview, reviewsets, bingogame, result, bingosetup, gameresult):
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
        try:
            from reconstruction import mlm
            mlm.init()
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
        

        if cur == "scan":
            sm.get_screen("scan").go_back_home()
            return True
        
        if cur == "bingosetup":
            sm.get_screen("bingosetup").go_back()
            return True
        
        if cur == "bingogame":
            sm.get_screen("bingogame").go_back()
            return True

        target = {
            "scan": "home",
            "imagepreview": "scan",
            "extractedtext": "scan",
            "extractedcontent": "extractedtext",            
            "reviewsets": "home",
        }.get(cur, "home")
        sm.transition.direction = "right"
        sm.current = target
        return True


if __name__ == "__main__":
    Bingo().run()