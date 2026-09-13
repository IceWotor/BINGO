import kivy
from kivy.config import Config

Config.set('graphics', 'resizable', '0')

# Kivy - Core
from kivy.app import App
from kivy.core.window import Window
from kivy.metrics import dp, sp


# Kivy - Layouts
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout

# Kivy - Widgets
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

# Kivy - Screen Management
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
Window.left = -1900
Window.top = 150

class Home(Screen):
    def go_to_scan(self, instance):
        self.manager.transition.direction = "left"
        self.manager.current="scan"

    def go_to_manual(self, instance):
        self.manager.transition.direction = "left"
        self.manager.current="manual"
        
    def go_to_reviewset(self, instance):
        self.manager.transition.direction = "left"
        self.manager.current="reviewset"
        
# To Take a Photo with Camera
class Scan(Screen):
    
    def go_back_home(self, instance):
        self.manager.transition.direction = "right"
        self.manager.current="home"
        
    def on_enter(self):
        self.ids.camera.start_camera()
    
    def take_photo(self, instance):
        frame = self.ids.camera.current_frame

        if frame is None:
            return

        # Rotate the saved image too
        frame = cv2.rotate(
            frame,
            cv2.ROTATE_90_CLOCKWISE
        )

        # Save it
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

        # Set camera resolution to 16:9
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

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
        
        #Rotate Frame
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

# Preview of Uploaded Photo | Confirm Photo
class ImagePreview(Screen):
    
    image_path = ""
    
    def take_photo_again(self, instance):
        self.manager.transition.direction = "right"
        self.manager.current = "scan"
        

    def on_enter(self):
        self.ids.preview_image.source = self.image_path
        self.ids.preview_image.reload()
        
    def use_photo(self, instance):
        text = pytesseract.image_to_string(
            PILImage.open(self.image_path)
        )
        textpreview = self.manager.get_screen("textpreview")
        textpreview.ocr_text = text

        self.manager.transition.direction = "left"
        self.manager.current = "textpreview"
    

# Preview of OCR Scanned Text | Confirm Text
class TextPreview(Screen):
    ocr_text = ""
    
    def back_to_preview(self, instance):
        self.manager.current = "imagepreview"



class Manual(Screen):
    def go_back_home(self, instance):
        self.manager.transition.direction = "right"
        self.manager.current="home"

class Reconstruct(Screen):
    pass

class ReviewSet(Screen):
    pass

class BingoGame(Screen):
    pass

class Result(Screen):
    pass

class Bingo(App):
    def build(self):
        sm = ScreenManager()
        
        home = Home(name="home")
        
        scan = Scan(name="scan")
        imagepreview = ImagePreview(name="imagepreview")
        textpreview = TextPreview(name="textpreview")
        
        manual = Manual(name="manual")
        reconstruct = Reconstruct(name="reconstruct")
        reviewset = ReviewSet(name="reviewset")
        bingogame = BingoGame(name="bingogame")
        result = Result(name="result")

        # home buttons
        home.ids.scanAcademicMaterial_button.bind(
            on_release=home.go_to_scan
        )

        home.ids.manualEncoding_button.bind(
            on_release=home.go_to_manual
        )

        home.ids.reviewSets_button.bind(
            on_release=home.go_to_reviewset
        )
        
        # scan buttons
        scan.ids.scanBackButton.bind(
            on_release=scan.go_back_home
        )
        
        scan.ids.takephoto.bind(
            on_release=scan.take_photo
        )
        
        # image preview buttons
        
        imagepreview.ids.photoBackButton.bind(
            on_release=imagepreview.take_photo_again
        )
        
        # text preview buttons
        
        textpreview.ids.textBackButton.bind(
                on_release=textpreview.back_to_preview
        )
        # manual buttons
        
        manual.ids.manualBackButton.bind(
            on_release=manual.go_back_home
        )
        

        # add all pages
        sm.add_widget(home)
        
        sm.add_widget(scan)
        
        sm.add_widget(imagepreview)
        sm.add_widget(textpreview)
        
        sm.add_widget(manual)
        sm.add_widget(reconstruct)
        
        sm.add_widget(reviewset)
        sm.add_widget(bingogame)
        sm.add_widget(result)
        
        sm.current = "home"

        return sm


if __name__ == '__main__':
    Bingo().run()