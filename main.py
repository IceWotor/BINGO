import kivy, sqlite3
from kivy.config import Config

Config.set('graphics', 'resizable', '0')

# Kivy - Core
from kivy.app import App
from kivy.core.window import Window
from kivy.metrics import dp, sp


# Kivy - Layouts
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.floatlayout import FloatLayout

# Kivy - Widgets
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

# Kivy - Screen Management
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.screenmanager import SlideTransition

# Camera
import os
os.environ["OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS"] = "0"
import cv2
from kivy.clock import Clock 
from kivy.graphics.texture import Texture

# OCR / Image Processing
import pytesseract
from PIL import Image as PILImage


pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

Window.size = (360, 765)
#Window.left = -1900
Window.left = 1400
Window.top = 150

class Database:

    def __init__(self):
        self.connection = sqlite3.connect("bingo.db")
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

        self.cursor.execute("""
            INSERT INTO review_sets (name)
            VALUES (?)
        """, (name,))

        self.connection.commit()

        return self.cursor.lastrowid

    def add_term(self, review_set_id, term, definition):

        self.cursor.execute("""
            INSERT INTO terms (review_set_id, term, definition)
            VALUES (?, ?, ?)
        """, (review_set_id, term, definition))

        self.connection.commit()

        return self.cursor.lastrowid

    def get_terms(self, review_set_id):

        self.cursor.execute("""
            SELECT id, term, definition
            FROM terms
            WHERE review_set_id = ?
        """, (review_set_id,))

        return self.cursor.fetchall()

    def get_term_count(self, review_set_id):
        cursor = self.connection.cursor()

        cursor.execute(
            "SELECT COUNT(*) FROM terms WHERE review_set_id = ?",
            (review_set_id,)
        )

        return cursor.fetchone()[0]

    def delete_term(self, term_id):
        self.cursor.execute("""
            DELETE FROM terms
            WHERE id = ?
        """, (term_id,))

        self.connection.commit()

    def update_review_set_name(self, review_set_id, name):
        self.cursor.execute("""
            UPDATE review_sets
            SET name = ?
            WHERE id = ?
        """, (name, review_set_id))

        self.connection.commit()

    def get_review_sets(self):
        self.cursor.execute("""
            SELECT id, name
            FROM review_sets
            ORDER BY created_at DESC
        """)

        return self.cursor.fetchall()
    
    def delete_review_set(self, review_set_id):

        self.cursor.execute("""
            DELETE FROM terms
            WHERE review_set_id = ?
        """, (review_set_id,))

        self.cursor.execute("""
            DELETE FROM review_sets
            WHERE id = ?
        """, (review_set_id,))

        self.connection.commit()
    def close(self):
        self.connection.close()
        
class Home(Screen):
    def go_to_scan(self, instance):
        self.manager.transition.direction = "left"
        self.manager.current="scan"

    def go_to_manual(self, instance):

        app = App.get_running_app()

        review_set_id = app.db.create_review_set("Untitled Review Set")

        manual = self.manager.get_screen("manual")
        manual.review_set_id = review_set_id

        print("Created Review Set:", review_set_id)

        self.manager.transition.direction = "left"
        self.manager.current = "manual"
        
    def go_to_reviewset(self, instance):
        self.manager.transition.direction = "left"
        self.manager.current="reviewsets"

class Scan(Screen):
    
    def go_back_home(self,  instance):
            self.manager.current = "home"
    def go_camera(self, instance):
            self.manager.transition.direction = "left"
            self.manager.current = "camerascan"
            
    def go_upload(self, instance):
            self.manager.transition.direction = "left"
            self.manager.current = "camerascan"
    


class CameraScan(Screen):
    
    def go_back_home(self, instance):
        self.manager.transition.direction = "right"
        self.manager.current="home"
        
    def on_enter(self):
        self.ids.camera.start_camera()
    
    def take_photo(self, instance):
        frame = self.ids.camera.current_frame

        if frame is None:
            return

        frame = cv2.rotate(
            frame,
            cv2.ROTATE_90_CLOCKWISE
        )

        cv2.imwrite("captured.jpg", frame)

        preview = self.manager.get_screen("imagepreview")
        preview.image_path = "captured.jpg"

        self.manager.transition.direction = "left"
        self.manager.current = "imagepreview"
        
        

    def on_leave(self):
        self.ids.camera.stop_camera()

class CameraWidget(Image):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.camera = None
        self.clock = None
        self.current_frame = None

    def start_camera(self):
        if self.camera is not None:
            return

        self.camera = cv2.VideoCapture(1)

        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 1440)

        self.clock = Clock.schedule_interval(
            self.update_camera, 1.0 / 30.0
        )

    def update_camera(self, dt):
        if self.camera is None:
            return

        ret, frame = self.camera.read()

        if not ret:
            return

        self.current_frame = frame.copy()

        frame = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2RGB
        )
        
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)

        texture = Texture.create(
            size=(frame.shape[1], frame.shape[0]),
            colorfmt="rgb"
        )

        texture.blit_buffer(
            frame.tobytes(),
            colorfmt="rgb",
            bufferfmt="ubyte"
        )

        texture.flip_vertical()

        self.texture = texture

    def stop_camera(self):
        if self.clock is not None:
            self.clock.cancel()
            self.clock = None

        if self.camera is not None:
            self.camera.release()
            self.camera = None

        self.texture = None
class ImagePreview(Screen):
    
    image_path = ""
    
    def take_photo_again(self, instance):
        self.manager.transition.direction = "right"
        self.manager.current = "camerascan"
        

    def on_enter(self):
        self.ids.preview_image.source = self.image_path
        self.ids.preview_image.reload()
        
    def use_photo(self, instance):
        text = pytesseract.image_to_string(
            PILImage.open(self.image_path)
        )
        
        print("OCR Output:")
        print(text)

        textpreview = self.manager.get_screen("textpreview")
        textpreview.ocr_text = text

        self.manager.transition.direction = "left"
        self.manager.current = "textpreview"
    
class TextPreview(Screen):
    ocr_text = ""
    
    def back_to_preview(self, instance):
        self.manager.current = "imagepreview"


class Manual(Screen):

    review_set_id = None
    def go_back_home(self, instance):

        app = App.get_running_app()

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
            on_release=lambda instance:
            self.confirm_go_back(popup)
        )

        popup_content.ids.stayButton.bind(
            on_release=popup.dismiss
        )

        popup.open()

    def confirm_go_back(self, popup):

        if self.review_set_id is not None:

            app = App.get_running_app()

            app.db.delete_review_set(
                self.review_set_id
            )

            print(
                "Deleted Review Set:",
                self.review_set_id
            )

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

        term_id = app.db.add_term(
            self.review_set_id,
            term,
            definition
        )

        entry = TermEntry(
            term_id=term_id,
            term=term,
            definition=definition
        )

        self.ids.entriesContainer.add_widget(entry)

        count = app.db.get_term_count(self.review_set_id)

        self.ids.entryCountLabel.text = f"{count}"

        print("Term added successfully!")
        print("Term ID:", term_id)
        print("Review Set ID:", self.review_set_id)
        print("Term:", term)
        print("Definition:", definition)

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

        print("Entry selected for editing.")
        print("Deleted Term ID:", term_id)

    def go_to_content_review(self, instance):

        if self.review_set_id is None:
            print("No review set selected.")
            return

        content_review = self.manager.get_screen("contentreview")

        content_review.review_set_id = self.review_set_id
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

        # Term
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
            width=lambda instance, value: setattr(
                instance,
                "text_size",
                (value, None)
            )
        )

        term_label.bind(
            texture_size=lambda instance, value: setattr(
                instance,
                "height",
                value[1]
            )
        )

        # Definition
        definition_label = Label(
            text=definition,
            font_name="./assets/fonts/PixelifySans.ttf",
            font_size="10sp",
            color=(0.604, 0.4, 0.894, 0.8),
            size_hint=(1, None),
            halign="left",
            valign="top",
            pos_hint={"x": 0, "top": 0.75},
        )

        definition_label.bind(
            width=lambda instance, value: setattr(
                instance,
                "text_size",
                (value, None)
            )
        )

        definition_label.bind(
            texture_size=lambda instance, value: setattr(
                instance,
                "height",
                value[1]
            )
        )

        # Dividier
        divider = Image(
            source="./assets/pageAssets/manual/divider.png",
            size_hint=(1.5, None),
            pos_hint={"center_x": 0.65, "y": 0}
        )

        divider.bind(
            width=lambda instance, value: setattr(
                instance,
                "height",
                value * (3 / 323)
            )
        )

        self.add_widget(term_label)
        self.add_widget(definition_label)
        self.add_widget(divider)

        def update_height(*args):
            self.height = (
                term_label.height
                + dp(1)
                + definition_label.height
                + dp(3)
                + divider.height
            )

        term_label.bind(texture_size=lambda *args: update_height())
        definition_label.bind(texture_size=lambda *args: update_height())
        divider.bind(height=lambda *args: update_height())

        Clock.schedule_once(lambda dt: update_height(), 0)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            print("ENTRY CLICKED:", self.term)

            manual = App.get_running_app().root.get_screen("manual")

            manual.edit_entry(
                self.term_id,
                self.term,
                self.definition,
                self
            )

            return True

        return super().on_touch_down(touch)

class ContentReview(Screen):
    
    review_set_id = None
    
    def printEdit(self, instance):
        print ("Edit works")
    
    def go_back_manual(self, instance):
        self.manager.transition.direction = "right"
        self.manager.current="manual"

    def load_entries(self):

        if self.review_set_id is None:
            return

        app = App.get_running_app()

        terms = app.db.get_terms(self.review_set_id)

        self.ids.contentEntriesContainer.clear_widgets()

        for number, (term_id, term, definition) in enumerate(terms, start=1):

            entry = ContentReviewEntry(
                number=number,
                term=term,
                definition=definition
            )

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

        self.manager.transition.direction = "left"
        self.manager.current = "reviewsets"

class ContentReviewEntry(FloatLayout):

    def __init__(self, number, term, definition, **kwargs):
        super().__init__(**kwargs)

        self.size_hint_y = None

        entryBackground = Image(
            source="./assets/pageAssets/contentreview/entryBackground.png",
            size_hint=(0.15, None),
            pos_hint={"x": 0, "top": 1},
            allow_stretch=True,
            keep_ratio=True
        )

        entryBackground.bind(
            width=lambda instance, value:
            setattr(instance, "height", value * 37 / 40)
        )

        self.add_widget(entryBackground)


        number_label = Label(
            text=str(number),
            font_name="./assets/fonts/PressStart2P.ttf",
            font_size="11sp",
            color=(1, 1, 1, 1),
            size_hint=(None, None),
            size=(40, 40),
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
            width=lambda instance, value:
            setattr(
                instance,
                "text_size",
                (value, None)
            )
        )

        term_label.bind(
            texture_size=lambda instance, value:
            setattr(
                instance,
                "height",
                value[1]
            )
        )

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
            width=lambda instance, value:
            setattr(
                instance,
                "text_size",
                (value, None)
            )
        )

        definition_label.bind(
            texture_size=lambda instance, value:
            setattr(
                instance,
                "height",
                value[1]
            )
        )

        self.add_widget(definition_label)
        
        divider = Image(
        source="./assets/pageAssets/contentreview/divider.png",
            size_hint=(1.5, None),
            pos_hint={"center_x": 0.5}
        )

        divider.bind(
            width=lambda instance, value: setattr(
                instance,
                "height",
                value * (3 / 323)
            )
        )
        
        self.add_widget(divider)


        def update_layout(*args):

            number_label.top = self.top + dp(4)

            term_label.top = self.top + dp(8)

            definition_label.top = term_label.y - dp(-3)
            
            divider.y = self.y + dp(8)

            self.height = (
                term_label.height
                + dp(5)
                + definition_label.height
                + dp(10)
            )

        term_label.bind(
            height=update_layout,
            y=update_layout
        )

        definition_label.bind(
            height=update_layout
        )

        self.bind(pos=update_layout)  

        Clock.schedule_once(
            lambda dt: update_layout(),
            0
        )
class Reconstruct(Screen):
    pass

class ReviewSets(Screen):

    def on_enter(self):
        self.load_review_sets()

    def load_review_sets(self):
        app = App.get_running_app()

        review_sets = app.db.get_review_sets()

        self.ids.reviewSetsContainer.clear_widgets()

        for number, (review_set_id, name) in enumerate(review_sets, start=1):
            entry = ReviewSetEntry(
                number=number,
                review_set_id=review_set_id,
                name=name
            )
            self.ids.reviewSetsContainer.add_widget(entry)

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
            allow_stretch=True,
            keep_ratio=True
        )

        entryBackground.bind(
            width=lambda instance, value:
            setattr(instance, "height", value * 37 / 40)
        )

        self.add_widget(entryBackground)

        number_label = Label(
            text=str(number),
            font_name="./assets/fonts/PressStart2P.ttf",
            font_size="11sp",
            color=(1, 1, 1, 1),
            size_hint=(None, None),
            size=(40, 40),
            pos_hint={"x": 0.01},
            halign="center",
            valign="middle"
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
            width=lambda instance, value:
            setattr(instance, "text_size", (value, None))
        )

        name_label.bind(
            texture_size=lambda instance, value:
            setattr(instance, "height", value[1])
        )

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

        divider = Image(
            source="./assets/pageAssets/contentreview/divider.png",
            size_hint=(1.5, None),
            pos_hint={"center_x": 0.5}
        )

        divider.bind(
            width=lambda instance, value: setattr(
                instance,
                "height",
                value * (3 / 323)
            )
        )

        self.add_widget(divider)

        def update_layout(*args):
            number_label.top = self.top + dp(4)
            name_label.top = self.top + dp(8)
            divider.y = self.y + dp(8)

            self.height = (
                max(entryBackground.height, name_label.height)
                + dp(15)
            )

        name_label.bind(
            height=update_layout,
            y=update_layout
        )

        self.bind(pos=update_layout)

        Clock.schedule_once(lambda dt: update_layout(), 0)

    def delete_entry(self, instance):
        app = App.get_running_app()

        app.db.delete_review_set(self.review_set_id)

        print("Deleted Review Set:", self.review_set_id)

        reviewsets = App.get_running_app().root.get_screen("reviewsets")
        reviewsets.load_review_sets()
class BingoGame(Screen):
    pass

class Result(Screen):
    pass

class Bingo(App):
    def build(self):
        self.db = Database()
        
        sm = ScreenManager()
        
        home = Home(name="home")
        
        scan = Scan(name="scan")

        camerascan = CameraScan(name="camerascan")
        
        imagepreview = ImagePreview(name="imagepreview")
        textpreview = TextPreview(name="textpreview")
        
        manual = Manual(name="manual")
        
        contentreview = ContentReview(name="contentreview")
        reconstruct = Reconstruct(name="reconstruct")
        reviewsets = ReviewSets(name="reviewsets")
        bingogame = BingoGame(name="bingogame")
        result = Result(name="result")

        # home buttons
        home.ids.scanAcademicMaterial_button.bind(
            on_release=home.go_to_scan
        )

        home.ids.manualEncoding_button.bind(
            on_release=home.go_to_manual
        )

        home.ids.ReviewSets_button.bind(
            on_release=home.go_to_reviewset
        )
        
        # scan buttons
        scan.ids.scanBackButton.bind(
            on_release=camerascan.go_back_home
        )
        
        scan.ids.cameraButton.bind(
            on_release = scan.go_camera
        )
        
        # camera scan buttons
        camerascan.ids.camerascanBackButton.bind(
            on_release=camerascan.go_back_home
        )
        
        camerascan.ids.takephoto.bind(
            on_release=camerascan.take_photo
        )
        
        # image preview buttons
        
        imagepreview.ids.photoBackButton.bind(
            on_release=imagepreview.take_photo_again
        )
        
        imagepreview.ids.retakeButton.bind(
        on_release=imagepreview.take_photo_again
        )

        imagepreview.ids.usePhotoButton.bind(
            on_release=imagepreview.use_photo
        )
        
        # text preview buttons
        
        textpreview.ids.textBackButton.bind(
                on_release=textpreview.back_to_preview
        )
        # manual buttons
        
        manual.ids.manualBackButton.bind(
            on_release=manual.go_back_home
        )
        
        manual.ids.addTermButton.bind(
            on_release=manual.add_term
        )

        manual.ids.continueButton.bind(
            on_release=manual.go_to_content_review
        )
        
        # content review buttons
        contentreview.ids.edit_button.bind(
            on_release=contentreview.printEdit
        )
        
        contentreview.ids.conRevBackButton.bind(
            on_release=contentreview.go_back_manual
        )
        
        contentreview.ids.addTermButton.bind(
            on_release=contentreview.go_back_manual
        )
        
        contentreview.ids.completeReviewerButton.bind(
            on_release=contentreview.complete_reviewer
        )

        reviewsets.ids.reviewSetsBackButton.bind(
            on_release=reviewsets.go_back_home
        )

        # add all pages
        sm.add_widget(home)
        
        sm.add_widget(scan)
        sm.add_widget(camerascan)
        
        sm.add_widget(imagepreview)
        sm.add_widget(textpreview)
        
        sm.add_widget(manual)
        sm.add_widget(contentreview)
        
        sm.add_widget(reconstruct)
        
        sm.add_widget(reviewsets)
        sm.add_widget(bingogame)
        sm.add_widget(result)
        
        sm.current = "home"

        return sm


if __name__ == '__main__':
    Bingo().run()