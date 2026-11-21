"""My Review Sets page: the list of saved review sets, one card each, and a green
"Create new review set" button at the end of the list.

Tap a card to open the set. Hold a card (about 0.7 s) to delete it.

EASY TO CHANGE
  * ASSETS   every image on this page. Drop a PNG with the listed name into
             assets/pageAssets/reviewsets/ and it is used; with no file a plain
             drawing is shown.
  * TEXT     the words on the page.
  * LAYOUT   widths are fractions of the screen; the card and button keep the proportions
             of their images (CARD_RATIO, CREATE_RATIO).

main.py needs only:   from reviewsets_screen import ReviewSets
and the screen is added as before:   ReviewSets(name="reviewsets")
"""
from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from ui_kit import (CYAN, DIM, FONT, FONT_PX, PANEL, PURPLE, WHITE, Art, ArtButton,
                    fb_back, fb_chevron, fb_file, fb_frame, register_assets)

# ----------------------------------------------------------------- settings
FOLDER = "./assets/pageAssets/reviewsets/"
ASSETS = {
    "rs_frame":  [FOLDER + "reviewSetContainer.png"],
    "rs_card":   [FOLDER + "reviewerContainer.png"],
    "rs_back":   [FOLDER + "backButton.png", "./assets/icons/backButton.png"],
    "rs_create": [FOLDER + "createNewReviewSet.png"],
    "rs_file":   [FOLDER + "purpleDocument.png"],     # document icon on each card
    "rs_open":   [FOLDER + "open.png"],               # the "Open >" picture
}
register_assets(ASSETS)

TEXT = dict(
    title="My Review Sets",
    open="Open",
    one_term="1 term",
    many_terms="%d terms",
    empty="No review sets yet.",
    delete_q="Delete \"%s\"?",
    delete="DELETE",
    cancel="CANCEL",
    untitled="Untitled Review Set",
)

BG = (0.047, 0, 0.129, 1)
COUNT_COLOR = (0.45, 0.3, 0.95, 1)
GREEN = (0.1, 0.75, 0.45, 1)
FRAME_FILL = (0x16 / 255.0, 0x0c / 255.0, 0x48 / 255.0, 1)   # #160c48, inside the frame
FILL_INSET = dp(10)                                         # keeps the colour under the frame border

CARD_RATIO = 73 / 305.0          # card height / width (reviewerContainer.png)
CREATE_RATIO = 71 / 339.0        # button height / width (createNewReviewSet.png)
CREATE_OVERSCAN = 1.065          # the PNG has transparent margins; draw it a bit wider
FRAME_W = 0.97                   # width of the frame, as a fraction of the screen
LIST_H = 0.93                    # height of the list, as a fraction of the frame
LIST_SHORTER = dp(6)             # then made this much shorter
FRAME_RAISE = dp(10)             # frame and list are moved up by this much
LIST_W = 0.79                    # width of the list, as a fraction of the screen
FRAME_BOTTOM_GAP = dp(24)        # space under the frame (phone gesture bar)
HOLD_SECONDS = 0.7
BACK_SCALE = 1.2                 # size of the pink back arrow (1 = the PNG's own pixels)


# ----------------------------------------------------------------- fallbacks
def fb_card(wd):
    Color(*PANEL)
    RoundedRectangle(pos=wd.pos, size=wd.size, radius=[dp(10)])
    Color(*PURPLE)
    Line(rounded_rectangle=(wd.x, wd.y, wd.width, wd.height, dp(10)), width=1.6)


def fb_create(wd):
    Color(0.1, 0.65, 0.4, 1)
    Rectangle(pos=wd.pos, size=wd.size)
    Color(0.6, 1, 0.8, 1)
    Line(rectangle=(wd.x, wd.y, wd.width, wd.height), width=2)
    lab = CoreLabel(text="+ Create new review set", font_size=dp(11), font_name=FONT)
    lab.refresh()
    t = lab.texture
    Color(1, 1, 1, 1)
    Rectangle(texture=t, size=t.size,
              pos=(wd.x + (wd.width - t.width) / 2, wd.y + (wd.height - t.height) / 2))


def fb_open(wd):
    lab = CoreLabel(text="Open", font_size=dp(12), font_name=FONT)
    lab.refresh()
    t = lab.texture
    Color(1, 1, 1, 1)
    Rectangle(texture=t, size=t.size, pos=(wd.x, wd.y + (wd.height - t.height) / 2))
    fb_chevron("right")(type("W", (), dict(x=wd.right - dp(10), y=wd.y, width=dp(10),
                                           height=wd.height))())


# ----------------------------------------------------------------- helpers
def _label(txt, size, color, halign="left", font=FONT, **kwargs):
    """Single-line, vertically centred, no markup (set names may contain [ ])."""
    lab = Label(text=txt, font_name=font, font_size=size, color=color,
                halign=halign, valign="middle", **kwargs)
    lab.bind(size=lambda i, v: setattr(i, "text_size", v))
    return lab


class TapBox(ButtonBehavior, FloatLayout):
    """An invisible, tappable area."""


# ----------------------------------------------------------------- card
class ReviewSetCard(ButtonBehavior, FloatLayout):
    """One saved set: icon, name, term count, "Open >". Tap = open, hold = delete."""

    def __init__(self, set_id, name, count, on_open, on_hold, **kwargs):
        super().__init__(size_hint_y=None, **kwargs)
        self.set_id, self.name = set_id, name
        self._on_open, self._on_hold = on_open, on_hold
        self._ev = None
        self._held = False
        self.bind(width=lambda i, w: setattr(i, "height", w * CARD_RATIO))

        self.add_widget(Art("rs_card", fb_card, size_hint=(1, 1),
                            pos_hint={"x": 0, "y": 0}))
        self.add_widget(Art("rs_file", fb_file, size_hint=(None, None),
                            size=(dp(29), dp(32)),
                            pos_hint={"x": 0.06, "center_y": 0.5}))
        self.add_widget(_label(name, "11sp", WHITE, shorten=True, shorten_from="right",
                               size_hint=(0.5, 0.4),
                               pos_hint={"x": 0.19, "center_y": 0.64}))
        terms = TEXT["one_term"] if count == 1 else TEXT["many_terms"] % count
        self.add_widget(_label(terms, "10sp", COUNT_COLOR, size_hint=(0.5, 0.3),
                               pos_hint={"x": 0.19, "center_y": 0.36}))
        self.add_widget(Art("rs_open", fb_open, size_hint=(None, None),
                            size=(dp(47), dp(13)),
                            pos_hint={"right": 0.965, "center_y": 0.5}))

    # ---- hold to delete
    def on_press(self):
        self._held = False
        self._cancel()
        self._ev = Clock.schedule_once(self._hold, HOLD_SECONDS)

    def on_touch_move(self, touch):
        if self._ev is not None:
            if ((touch.x - touch.ox) ** 2 + (touch.y - touch.oy) ** 2) ** 0.5 > dp(10):
                self._cancel()
        return super().on_touch_move(touch)

    def on_release(self):
        self._cancel()
        if self._held:
            return
        t = self.last_touch
        if t is not None:
            if ((t.x - t.ox) ** 2 + (t.y - t.oy) ** 2) ** 0.5 > dp(10):
                return                      # it was a scroll, not a tap
        self._on_open(self.set_id, self.name)

    def _hold(self, dt):
        self._ev = None
        self._held = True
        self._on_hold(self.set_id, self.name)

    def _cancel(self):
        if self._ev is not None:
            self._ev.cancel()
            self._ev = None


# ----------------------------------------------------------------- screen
class ReviewSets(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*BG)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd_bg, size=self._upd_bg)

        outer = BoxLayout(orientation="vertical")
        outer.add_widget(Widget(size_hint_y=None, height=dp(40)))        # status bar space

        # ---- title row: back arrow + centred title
        head = FloatLayout(size_hint_y=None, height=dp(52))
        back = TapBox(size_hint=(None, None), size=(dp(56), dp(48)),
                      pos_hint={"x": 0.02, "center_y": 0.5})
        back.add_widget(Art("rs_back", fb_back, size_hint=(None, None),
                            size=(dp(66 * BACK_SCALE), dp(17 * BACK_SCALE)),
                            pos_hint={"x": 0.14, "center_y": 0.5}))
        back.bind(on_release=lambda *a: self.go_back_home())
        head.add_widget(back)
        head.add_widget(_label(TEXT["title"], "17sp", WHITE, halign="center",
                               font=FONT_PX, size_hint=(0.7, 1),
                               pos_hint={"center_x": 0.5, "center_y": 0.5}))
        outer.add_widget(head)

        # ---- frame with the scrolling list inside
        body = FloatLayout()
        with body.canvas.before:                      # colour behind the frame art
            Color(*FRAME_FILL)
            self._fill = Rectangle()
        self.frame = Art("rs_frame", fb_frame, size_hint=(None, None))
        body.add_widget(self.frame)
        self.scroll = ScrollView(size_hint=(None, None), bar_width=0, do_scroll_x=False)
        self.list = GridLayout(cols=1, size_hint_y=None, spacing=dp(18),
                               padding=(0, dp(6)))
        self.list.bind(minimum_height=self.list.setter("height"))
        self.scroll.add_widget(self.list)
        body.add_widget(self.scroll)
        body.bind(pos=self._place_body, size=self._place_body)
        self._body = body
        outer.add_widget(body)
        outer.add_widget(Widget(size_hint_y=None, height=FRAME_BOTTOM_GAP))
        self.add_widget(outer)

    def _place_body(self, *args):
        """Frame and list are placed by hand so both can be nudged together (FRAME_RAISE)."""
        b = self._body
        fw = b.width * FRAME_W
        self.frame.size = (fw, b.height)
        self.frame.pos = (b.x + (b.width - fw) / 2.0, b.y + FRAME_RAISE)
        self._fill.pos = (self.frame.x + FILL_INSET, self.frame.y + FILL_INSET)
        self._fill.size = (fw - 2 * FILL_INSET, b.height - 2 * FILL_INSET)
        self.scroll.size = (b.width * LIST_W, b.height * LIST_H - LIST_SHORTER)
        self.scroll.center = (b.center_x, self.frame.center_y)

    def _upd_bg(self, *args):
        self._bg.pos, self._bg.size = self.pos, self.size

    # ---------------------------------------------------------------- public
    def on_enter(self, *args):
        self.load_review_sets()

    def load_review_sets(self):
        app = App.get_running_app()
        self.list.clear_widgets()
        rows = app.db.get_review_sets()
        if not rows:
            lab = _label(TEXT["empty"], "12sp", DIM, halign="center",
                         size_hint_y=None, height=dp(60))
            self.list.add_widget(lab)
        for set_id, name in rows:
            self.list.add_widget(ReviewSetCard(
                set_id, name, app.db.get_term_count(set_id),
                self.open_review_set, self.ask_delete))
        self.list.add_widget(self._create_row())

    def _create_row(self):
        row = FloatLayout(size_hint_y=None)
        row.bind(width=lambda i, w: setattr(i, "height",
                                            w * CREATE_OVERSCAN * CREATE_RATIO))
        btn = ArtButton("rs_create", fb_create, size_hint=(CREATE_OVERSCAN, 1),
                        pos_hint={"center_x": 0.5, "y": 0})
        btn.bind(on_release=lambda *a: self.create_new())
        row.add_widget(btn)
        return row

    def open_review_set(self, review_set_id, name):
        manual = self.manager.get_screen("manual")
        manual.load_existing_set(review_set_id, name)
        self.manager.transition.direction = "left"
        self.manager.current = "manual"

    def create_new(self):
        self.manager.get_screen("home").go_to_manual()      # makes an empty set, opens Manual

    def go_back_home(self, *args):
        self.manager.transition.direction = "right"
        self.manager.current = "home"

    # ---------------------------------------------------------------- delete
    def ask_delete(self, review_set_id, name):
        box = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(12))
        box.add_widget(_label(TEXT["delete_q"] % name, "13sp", WHITE, halign="center"))
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
        popup = Popup(title="", separator_height=0, content=box, auto_dismiss=False,
                      size_hint=(0.85, None), height=dp(170),
                      background="", background_color=(0.08, 0.04, 0.22, 1))
        for text, color, action in (
                (TEXT["cancel"], (0.3, 0.2, 0.7, 1), popup.dismiss),
                (TEXT["delete"], (0.85, 0.2, 0.25, 1),
                 lambda *a: self._delete(popup, review_set_id))):
            b = Button(text=text, font_name=FONT_PX, font_size="9sp", color=WHITE,
                       background_normal="", background_down="", background_color=color)
            b.bind(on_release=action)
            row.add_widget(b)
        box.add_widget(row)
        popup.open()

    def _delete(self, popup, review_set_id):
        popup.dismiss()
        App.get_running_app().db.delete_review_set(review_set_id)
        self.load_review_sets()
