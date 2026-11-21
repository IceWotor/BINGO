"""Bingo setup screen: choose a term set, a difficulty and the game options.

Sits between Content Review ("Complete reviewer") and the game.

EASY TO CHANGE
  * ASSETS       every image the screen uses. Drop a PNG with the listed name into
                 assets/pageAssets/bingosetup/ (or edit the path) and it is used. If no
                 file exists the widget draws a plain fallback, so the screen always works.
  * DIFFICULTIES the cards in section 2 (grid size, labels, which one gets the star).
  * OPTIONS      the checkboxes in section 3 (text and default value).
  * HOW_TO       the text in the "How to play" box.
  * TEXT         every other word on the page (headings, hint, messages).
  * LAYOUT       sizes and positions of everything (heights, gaps, frame and button placement).
  Shared helpers (Art, ArtButton, text, add_border...) are in ui_kit.py.
  Where things are drawn: SetPicker = term set box, DifficultyCard = the three cards,
  OptionRow = one checkbox row, BingoSetup.__init__ = the page structure and the how-to box.
"""
from kivy.app import App
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle, Triangle
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.dropdown import DropDown
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from ui_kit import (AMBER, CYAN, DIM, FONT, FONT_PX, PANEL, PURPLE, WHITE, Art, ArtButton,
                    add_border, fb_back, fb_continue, fb_frame, notice, register_assets,
                    star, text)

# ----------------------------------------------------------------- settings
FOLDER = "./assets/pageAssets/bingosetup/"

# name -> list of paths, first one that exists wins. No file at all -> drawn fallback.
ASSETS = {
    "bs_frame":       [FOLDER + "frame.png",
                    "./assets/pageAssets/extractedcontent/setContainer.png"],  # big panel
    "bs_continue":    [FOLDER + "continue.png",
                    "./assets/pageAssets/manual/continueButton.png"],          # pink button
    "bs_back":        [FOLDER + "back.png", "./assets/icons/backButton.png"],
    "bs_arrow":       [FOLDER + "dropdown_arrow.png"],   # little box with a triangle
    "bs_info":        [FOLDER + "info.png"],             # the (i) next to the hint
    "bs_divider":     [FOLDER + "divider.png"],          # dotted line between sections
    "bs_diff_easy":   [FOLDER + "diff_easy.png"],        # 3 x 3 dots icon
    "bs_diff_medium": [FOLDER + "diff_medium.png"],      # 4 x 4 dots icon
    "bs_diff_hard":   [FOLDER + "diff_hard.png"],        # 5 x 5 dots icon
    "bs_card":        [FOLDER + "diff_card.png"],        # difficulty card, not selected
    "bs_card_on":     [FOLDER + "diff_card_on.png"],     # difficulty card, selected
    "bs_badge":       [FOLDER + "badge_star.png"],       # round star on the recommended card
    "bs_check_on":    [FOLDER + "check_on.png"],
    "bs_check_off":   [FOLDER + "check_off.png"],
    "bs_howto_star":  [FOLDER + "howto_star.png"],
}

register_assets(ASSETS)

# key, grid size, big label, small label
DIFFICULTIES = [
    ("easy", 3, "3 x 3", "Easy"),
    ("medium", 4, "4 x 4", "Medium"),
    ("hard", 5, "5 x 5", "Hard"),
]
DEFAULT_DIFFICULTY = "easy"
RECOMMENDED = "medium"          # gets the star badge; "" = no badge

# key, title, description, default value
OPTIONS = [
    ("shuffle", "Shuffle terms on card",
     "Shuffle terms every time a new game is started", True),
    ("free_center", "Free center",
     "Enables the free space in the middle of each card", True),
    ("show_answer", "Show correct answer after selection",
     "Reveal the correct term after answering incorrectly", False),
]
NO_FREE_CENTER_NOTE = "Only on 3 x 3 and 5 x 5 cards (they have a middle square)"

HOW_TO = ("Read the definition, then choose the correct term.\n"
          "Get all answers correct (blackout) to BINGO!")

# The words on the page (the option texts and HOW_TO are above).
TEXT = dict(
    heading_set="1. SELECT A TERM SET",
    heading_difficulty="2. SELECT DIFFICULTY",
    heading_options="3. GAME OPTIONS",
    hint="You can review or edit this set in [ref=cr][color=33c4ff]Content Review[/color][/ref].",
    no_sets="No term sets yet",
    term_one="%d term",
    term_many="%d terms",
    how_title="HOW TO PLAY:",
    empty_set="This term set has no terms yet. Add some in Content Review first.",
)

# Sizes and positions. Lengths are in dp, "pos" and "size" pairs are fractions of the page.
LAYOUT = dict(
    top_space=50,                 # room for the phone's status bar
    frame_size=(0.9, 0.78),       # the big frame: width, height
    frame_top=0.93,               # frame top edge (1 = top of the page)
    list_size=(0.82, 0.71),       # scrolling area inside the frame
    list_center_y=0.55,
    list_padding=(4, 14),         # left/right, top/bottom inside the scrolling area
    section_gap=12,               # space between the pieces of a section
    heading_height=26,
    picker_height=64,             # the term set box
    arrow_size=34,                # dropdown arrow
    hint_height=30,
    divider_height=3,
    cards_height=118,             # the three difficulty cards
    cards_gap=10,
    card_icon=44,                 # dots icon on a card
    badge_size=28,                # star badge
    options_padding=14,
    options_gap=10,
    option_row=54,                # one checkbox row
    check_size=26,
    how_padding=12,
    back_size=(44, 12),     # width, height in dp    
    back_pos=(0.03, 0.99),        # x and top, as fractions
    continue_width=0.69,          # fraction of the page width
    continue_center_y=0.07,
)
L = LAYOUT


# ----------------------------------------------------------------- fallback drawings
# Plain stand-ins used when an image file is missing (only for this page's own images;
# the shared ones, like the frame and the buttons, are in ui_kit.py).


def fb_arrow(wd):
    x, y, w, h = wd.x, wd.y, wd.width, wd.height
    Color(0.12, 0.06, 0.4, 1)
    Rectangle(pos=wd.pos, size=wd.size)
    Color(0.55, 0.4, 1, 1)
    Line(rectangle=(x, y, w, h), width=1.6)
    Color(0.85, 0.7, 1, 1)
    Triangle(points=[x + .28 * w, y + .62 * h, x + .72 * w, y + .62 * h,
                     x + .5 * w, y + .3 * h])


def fb_info(wd):
    cx, cy = wd.center
    r = min(wd.width, wd.height) / 2
    Color(*DIM)
    Line(circle=(cx, cy, r), width=1.2)
    Rectangle(pos=(cx - r * .09, cy - r * .5), size=(r * .18, r * .6))
    Rectangle(pos=(cx - r * .09, cy + r * .3), size=(r * .18, r * .18))


def fb_divider(wd):
    Color(0.38, 0.2, 0.9, 1)
    Line(points=[wd.x, wd.center_y, wd.right, wd.center_y], width=1.6,
         dash_length=2, dash_offset=3)


def fb_dots(n):
    def draw(wd):
        side = min(wd.width, wd.height)
        d = side / (n + (n - 1) * 0.6)
        g = d * 0.6
        x0 = wd.center_x - side / 2
        y0 = wd.center_y - side / 2
        Color(*WHITE)
        for r in range(n):
            for c in range(n):
                Rectangle(pos=(x0 + c * (d + g), y0 + r * (d + g)), size=(d, d))
    return draw


def fb_card(on):
    def draw(wd):
        Color(*PANEL)
        RoundedRectangle(pos=wd.pos, size=wd.size, radius=[dp(8)])
        Color(*(CYAN if on else PURPLE))
        Line(rounded_rectangle=(wd.x, wd.y, wd.width, wd.height, dp(8)), width=1.8)
    return draw


def fb_badge(wd):
    cx, cy = wd.center
    r = min(wd.width, wd.height) / 2
    Color(0.15, 0.4, 0.95, 1)
    Ellipse(pos=(cx - r, cy - r), size=(2 * r, 2 * r))
    star(cx, cy, r * .6, WHITE)


def fb_howto_star(wd):
    star(wd.center_x, wd.center_y, min(wd.width, wd.height) / 2, (0.2, 0.55, 1, 1))


def fb_check(on):
    def draw(wd):
        x, y, w, h = wd.x, wd.y, wd.width, wd.height
        if on:
            Color(0.1, 0.55, 0.28, 1)
            Rectangle(pos=wd.pos, size=wd.size)
            Color(1, 1, 1, 1)
            Line(points=[x + .22 * w, y + .5 * h, x + .42 * w, y + .3 * h,
                         x + .78 * w, y + .7 * h], width=2)
        else:
            Color(0.45, 0.35, 0.85, 1)
            Line(rectangle=(x, y, w, h), width=1.4)
    return draw


# ----------------------------------------------------------------- small widgets


class SetPicker(ButtonBehavior, FloatLayout):
    """Box showing the chosen term set; tap to open the list."""

    def __init__(self, **kwargs):
        super().__init__(size_hint_y=None, height=dp(L["picker_height"]), **kwargs)
        add_border(self)
        col = BoxLayout(orientation="vertical", padding=(dp(14), dp(8), dp(60), dp(8)),
                        pos_hint={"x": 0, "y": 0})
        self.name = text("", "14sp", height=dp(24))
        self.count = text("", "10sp", color=DIM, height=dp(18))
        col.add_widget(self.name)
        col.add_widget(self.count)
        self.add_widget(col)
        self.add_widget(Art("bs_arrow", fb_arrow, size_hint=(None, None),
                            size=(dp(L["arrow_size"]), dp(L["arrow_size"])),
                            pos_hint={"right": 0.96, "center_y": .5}))


class DifficultyCard(ButtonBehavior, FloatLayout):
    def __init__(self, key, n, big, small, recommended, on_pick, **kwargs):
        super().__init__(**kwargs)
        self.key, self.on_pick = key, on_pick
        self.bg = Art("bs_card", fb_card(False), size_hint=(1, 1),
                      pos_hint={"x": 0, "y": 0})   # FloatLayout only moves children that have a pos_hint
        self.add_widget(self.bg)
        self.add_widget(Art("bs_diff_" + key, fb_dots(n), size_hint=(None, None),
                            size=(dp(L["card_icon"]), dp(L["card_icon"])),
                            pos_hint={"center_x": .5, "top": .88}))
        big_lbl = text(big, "11sp", font=FONT_PX, halign="center", height=dp(20))
        big_lbl.size_hint = (1, None)
        big_lbl.pos_hint = {"center_x": .5, "center_y": .30}
        small_lbl = text(small, "11sp", color=DIM, halign="center", height=dp(18))
        small_lbl.size_hint = (1, None)
        small_lbl.pos_hint = {"center_x": .5, "center_y": .14}
        self.add_widget(big_lbl)
        self.add_widget(small_lbl)
        if recommended:
            self.add_widget(Art("bs_badge", fb_badge, size_hint=(None, None),
                                size=(dp(L["badge_size"]), dp(L["badge_size"])),
                                pos_hint={"right": 1.0, "top": 1.12}))

    def set_selected(self, on):
        self.bg.key = "bs_card_on" if on else "bs_card"
        self.bg.fallback = fb_card(on)
        self.bg.redraw()

    def on_release(self):
        self.on_pick(self.key)


class OptionRow(ButtonBehavior, BoxLayout):
    def __init__(self, key, title, desc, value, on_toggle, **kwargs):
        super().__init__(size_hint_y=None, height=dp(L["option_row"]), spacing=dp(12), **kwargs)
        self.key, self.value, self.enabled = key, value, True
        self.desc_text, self.on_toggle = desc, on_toggle
        self.box = Art("bs_check_off", fb_check(False), size_hint=(None, None),
                       size=(dp(L["check_size"]), dp(L["check_size"])), pos_hint={"center_y": .5})
        self.add_widget(self.box)
        col = BoxLayout(orientation="vertical", spacing=dp(2))
        self.title = text(title, "11sp", height=dp(18))
        self.desc = text(desc, "8sp", color=DIM, height=dp(30))
        col.add_widget(self.title)
        col.add_widget(self.desc)
        self.add_widget(col)
        self.refresh()

    def refresh(self):
        on = self.value and self.enabled
        self.box.key = "bs_check_on" if on else "bs_check_off"
        self.box.fallback = fb_check(on)
        self.box.redraw()
        self.opacity = 1 if self.enabled else 0.45

    def set_enabled(self, enabled, note=None):
        self.enabled = enabled
        self.desc.text = note if (not enabled and note) else self.desc_text
        self.refresh()

    def on_release(self):
        if not self.enabled:
            return
        self.value = not self.value
        self.refresh()
        self.on_toggle(self.key, self.value)


# ----------------------------------------------------------------- the screen
class BingoSetup(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_id = None
        self.sets = []                       # [(id, name, term count)]
        self.difficulty = DEFAULT_DIFFICULTY
        self.opts = {k: default for k, _, _, default in OPTIONS}
        self.cards, self.rows = {}, {}

        with self.canvas.before:
            Color(0.047, 0, 0.129, 1)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd_bg, size=self._upd_bg)

        outer = BoxLayout(orientation="vertical")
        outer.add_widget(Widget(size_hint_y=None, height=dp(L["top_space"])))
        body = FloatLayout()
        outer.add_widget(body)
        self.add_widget(outer)

        body.add_widget(Art("bs_frame", fb_frame, size_hint=L["frame_size"],
                            pos_hint={"center_x": .5, "top": L["frame_top"]}))

        scroll = ScrollView(size_hint=L["list_size"],
                            pos_hint={"center_x": .5, "center_y": L["list_center_y"]},
                            bar_width=0)
        col = BoxLayout(orientation="vertical", size_hint_y=None,
                        padding=(dp(L["list_padding"][0]), dp(L["list_padding"][1])),
                        spacing=dp(L["section_gap"]))
        col.bind(minimum_height=col.setter("height"))
        scroll.add_widget(col)
        body.add_widget(scroll)

        # 1. term set
        col.add_widget(text(TEXT["heading_set"], "11sp", AMBER, FONT_PX, height=dp(L["heading_height"])))
        self.picker = SetPicker()
        self.picker.bind(on_release=self._open_list)
        col.add_widget(self.picker)
        hint = BoxLayout(size_hint_y=None, height=dp(L["hint_height"]), spacing=dp(6))
        hint.add_widget(Art("bs_info", fb_info, size_hint=(None, None), size=(dp(14), dp(14)),
                            pos_hint={"center_y": .5}))
        link = text(TEXT["hint"], "9sp", DIM, height=dp(L["hint_height"]))
        link.bind(on_ref_press=lambda *a: self.go_content_review())
        hint.add_widget(link)
        col.add_widget(hint)
        col.add_widget(Art("bs_divider", fb_divider, size_hint_y=None, height=dp(L["divider_height"])))

        # 2. difficulty
        col.add_widget(text(TEXT["heading_difficulty"], "11sp", AMBER, FONT_PX, height=dp(L["heading_height"])))
        row = BoxLayout(size_hint_y=None, height=dp(L["cards_height"]), spacing=dp(L["cards_gap"]))
        for key, n, big, small in DIFFICULTIES:
            card = DifficultyCard(key, n, big, small, key == RECOMMENDED, self._pick)
            self.cards[key] = card
            row.add_widget(card)
        col.add_widget(row)
        col.add_widget(Art("bs_divider", fb_divider, size_hint_y=None, height=dp(L["divider_height"])))

        # 3. options
        col.add_widget(text(TEXT["heading_options"], "11sp", AMBER, FONT_PX, height=dp(L["heading_height"])))
        box = BoxLayout(orientation="vertical", size_hint_y=None,
                        padding=dp(L["options_padding"]), spacing=dp(L["options_gap"]))
        box.bind(minimum_height=box.setter("height"))
        add_border(box)
        for key, title, desc, default in OPTIONS:
            r = OptionRow(key, title, desc, default, self._toggle)
            self.rows[key] = r
            box.add_widget(r)
        col.add_widget(box)
        col.add_widget(Art("bs_divider", fb_divider, size_hint_y=None, height=dp(L["divider_height"])))

        # how to play
        how = BoxLayout(orientation="vertical", size_hint_y=None, padding=dp(L["how_padding"]),
                        spacing=dp(6))
        how.bind(minimum_height=how.setter("height"))
        add_border(how)
        head = BoxLayout(size_hint_y=None, height=dp(20), spacing=dp(6))
        head.add_widget(Widget())
        head.add_widget(Art("bs_howto_star", fb_howto_star, size_hint=(None, None),
                            size=(dp(16), dp(16)), pos_hint={"center_y": .5}))
        head.add_widget(text(TEXT["how_title"], "9sp", CYAN, FONT_PX, height=dp(20),
                             size_hint_x=None, width=dp(130)))
        head.add_widget(Widget())
        how.add_widget(head)
        how.add_widget(text(HOW_TO, "10sp", halign="center"))
        col.add_widget(how)

        # back and continue
        back = ArtButton("bs_back", fb_back, size_hint=(None, None),
                 size=(dp(L["back_size"][0]), dp(L["back_size"][1])),
                 pos_hint={"x": L["back_pos"][0], "top": L["back_pos"][1]})
        back.bind(on_release=lambda *a: self.go_back())
        body.add_widget(back)

        go = ArtButton("bs_continue", fb_continue, size_hint=(L["continue_width"], None),
                       pos_hint={"center_x": .5, "center_y": L["continue_center_y"]})
        go.bind(width=lambda i, v: setattr(i, "height", v * 70 / 304))
        go.bind(on_release=lambda *a: self.go_play())
        body.add_widget(go)

        self._refresh_difficulty()

    # ---------------------------------------------------------------- helpers
    def _upd_bg(self, *args):
        self._bg.pos, self._bg.size = self.pos, self.size

    def _grid_size(self):
        return next(n for k, n, _, _ in DIFFICULTIES if k == self.difficulty)

    def _refresh_difficulty(self):
        for key, card in self.cards.items():
            card.set_selected(key == self.difficulty)
        free = self.rows.get("free_center")
        if free is not None:
            free.set_enabled(self._grid_size() % 2 == 1, NO_FREE_CENTER_NOTE)

    def _pick(self, key):
        self.difficulty = key
        self._refresh_difficulty()

    def _toggle(self, key, value):
        self.opts[key] = value

    def _show_set(self):
        cur = next((s for s in self.sets if s[0] == self.set_id), None)
        if cur is None:
            self.picker.name.text = TEXT["no_sets"]
            self.picker.count.text = ""
            return
        self.picker.name.text = cur[1]
        self.picker.count.text = (TEXT["term_one"] if cur[2] == 1 else TEXT["term_many"]) % cur[2]

    def _open_list(self, *args):
        if not self.sets:
            return
        dd = DropDown(auto_width=False, width=self.picker.width)
        for sid, name, count in self.sets:
            btn = Button(text="%s  (%d)" % (name, count), font_name=FONT, font_size="12sp",
                         size_hint_y=None, height=dp(42), color=WHITE,
                         background_normal="", background_down="",
                         background_color=(0.12, 0.07, 0.35, 1))
            btn.bind(on_release=lambda b, s=sid: self._choose(dd, s))
            dd.add_widget(btn)
        dd.open(self.picker)

    def _choose(self, dd, set_id):
        dd.dismiss()
        self.set_id = set_id
        self._show_set()

    # ---------------------------------------------------------------- navigation
    def open_for(self, review_set_id):
        """Call before switching to this screen."""
        db = App.get_running_app().db
        self.sets = [(sid, name, db.get_term_count(sid))
                     for sid, name in db.get_review_sets()]
        ids = [s[0] for s in self.sets]
        self.set_id = review_set_id if review_set_id in ids else (ids[0] if ids else None)
        self._show_set()
        self._refresh_difficulty()

    def go_content_review(self):
        if self.set_id is None:
            return
        cr = self.manager.get_screen("contentreview")
        cr.review_set_id = self.set_id
        cr.ids.reviewSetName.text = next((s[1] for s in self.sets if s[0] == self.set_id), "")
        cr.load_entries()
        self.manager.transition.direction = "right"
        self.manager.current = "contentreview"

    def go_back(self):
        self.go_content_review()

    def go_play(self):
        cur = next((s for s in self.sets if s[0] == self.set_id), None)
        if cur is None or cur[2] == 0:
            notice(TEXT["empty_set"])
            return
        game = self.manager.get_screen("bingogame")
        game.start_game(cur[0], cur[1], size=self._grid_size(),
                        shuffle=self.opts["shuffle"],
                        free_center=self.opts["free_center"],
                        show_answer=self.opts["show_answer"])
        self.manager.transition.direction = "left"
        self.manager.current = "bingogame"
