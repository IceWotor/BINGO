"""Processing page: the loading screen between USE IMAGE and Extracted Text.

Shows the document icon, a title, a loading bar with the cat running to the flag, three
check rows and the step bar. The screen only draws and animates; main.py's Processing class
tells it what happened:

    self.start()            when the page opens (resets everything, starts the bar)
    self.step_done(1..3)    a row gets its check and the bar jumps ahead
    self.finish(callback)   all done: "PROCESSING DONE!" shows for HOLD seconds, then callback()

EASY TO CHANGE
  * ASSETS      every image on this page. Drop a PNG with the listed name into
                assets/pageAssets/processing/ and it is used.
                doneText.png is optional: a picture of the "Remember to check..." line.
                Without it the line is drawn as text.
  * TEXT        the words on the page.
  * COLORS      text and bar colours.
  * LAYOUT      positions are in "asset pixels" (the pixels of Processing.png, measured from
                the top-left of the stage), so everything keeps its proportions on any phone.
  * FLOORS      how full the bar is after each step. CREEP is how fast it crawls while it waits.
"""
from kivy.clock import Clock, mainthread
from kivy.graphics import Color, Quad, Rectangle
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from ui_kit import (AMBER, FONT, STEP_FOLDER, Art, fb_frame, find_asset, register_assets,
                    texture)

# ----------------------------------------------------------------- settings
FOLDER = "./assets/pageAssets/processing/"
ASSETS = {
    "pr_frame":        [FOLDER + "container.png"],
    "pr_icon":         [FOLDER + "Processing.png"],          # document, sparkles, subtitle
    "pr_track":        [FOLDER + "loadingBar.png"],
    "pr_cat":          [FOLDER + "cat.png"],
    "pr_flag":         [FOLDER + "finishFlag.png"],
    "pr_circle":       [FOLDER + "circleBorder.png"],        # row not done
    "pr_check":        [FOLDER + "circlCheck.png"],          # row done
    "pr_badge":        [FOLDER + "documentCheck.png"],       # tick on the document at the end
    "pr_done_text":    [FOLDER + "doneText.png"],            # optional
    "pr_step_preview": [FOLDER + "progressBottomPreview.png",
                        STEP_FOLDER + "stepbar_preview.png"],
    "pr_step_recover": [FOLDER + "progressBottomRecover.png",
                        STEP_FOLDER + "stepbar_recover.png"],
}
register_assets(ASSETS)

TEXT = dict(
    heading="PROCESSING...",
    heading_done="PROCESSING DONE!",
    done_sub="Remember to check your texts! \u00b7\u1d17\u00b7",
    steps=("Image processed", "Text extracted", "Terms found"),
)

LAVENDER = (0.686, 0.663, 1, 1)
FILL = (0.467, 0.243, 0.976, 1)         # bar fill while working
FILL_DONE = AMBER                        # bar fill when done
BG = (0.047, 0, 0.129, 1)

# ---- progress
FLOORS = (0.0, 0.30, 0.60, 1.0)         # bar level once 0, 1, 2, 3 steps are done
CAP_GAP = 0.06                          # while waiting, the bar never gets closer than this to the next floor
CREEP = 0.06                            # crawl speed while waiting (bar fractions per second)
EASE = 6.0                              # how quickly the shown bar follows its target
HOLD = 1.0                              # seconds "PROCESSING DONE!" stays up
FPS = 30.0

# ---- page layout (fractions of the screen)
UNIT = 0.914 / 364.0                    # screen pixels per asset pixel = screen width * UNIT
FRAME_W, FRAME_H, FRAME_CY = 0.955, 0.867, 0.48
STAGE_TOP = 0.748                       # top edge of the stage (fraction of screen height)
STEPS_W, STEPS_CY = 0.605, 0.185        # step bar width and centre height (the image has its labels below the centre)
STEPS_RATIO = 61 / 241.0                # used only when the step bar image is missing

# ---- stage layout (asset pixels, y counted down from the stage top)
STAGE_W, STAGE_H = 305, 400
ICON_CROP_H = 112                       # in the done state only the picture part of Processing.png is shown
TITLE_Y = 119
SUB_Y = 207                             # centre of the subtitle line
BAR_CX, BAR_CY = 152.5, 165
INNER = (18, 26, 294, 52)               # fillable area inside loadingBar.png (x0, y0, x1, y1)
CHAMFER = 8                             # cut corners of that area
CAT_END_GAP = 4                         # space between the cat and the end of the bar at 100%
FLAG_GAP = 3.5                          # flag sits this far above the bar
CIRCLE_X, LABEL_X = 95.5, 117.5
ROW_Y0, ROW_DY = 276, 48
BADGE_CX, BADGE_CY, BADGE_K = 178.6, 22.3, 0.88

# ---- font sizes (asset pixels)
TITLE_SIZE, ROW_SIZE, SUB_SIZE = 18.6, 13.7, 12.6

TRACK_X, TRACK_Y = BAR_CX - 156, BAR_CY - 39   # top-left of loadingBar.png

# ----------------------------------------------------------------- helpers
_vis = {}
_crop = {}


def visible_box(path):
    """(left, top, right, bottom) of the non-transparent part of an image, in its pixels."""
    if path not in _vis:
        try:
            from PIL import Image as PilImage
            im = PilImage.open(path).convert("RGBA")
            alpha = im.getchannel("A").point(lambda v: 255 if v > 40 else 0)
            _vis[path] = alpha.getbbox() or ((0, 0) + im.size)
        except Exception:
            tex = texture(path)
            _vis[path] = (0, 0, tex.width, tex.height)
    return _vis[path]


# ----------------------------------------------------------------- stage
class ProcessingStage(Widget):
    """Everything between the frame and the step bar, drawn at one scale."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.progress = 0.0
        self.done = False
        self.rows_done = 0
        self.s = 1.0
        self.title = self._label("center")
        self.sub = self._label("center")
        self.rows = [self._label("left") for _ in TEXT["steps"]]
        for lab, txt in zip(self.rows, TEXT["steps"]):
            lab.text = txt
        self.bind(pos=self._moved, size=self._moved)
        self.reset()

    def _label(self, halign):
        lab = Label(font_name=FONT, color=LAVENDER, halign=halign, valign="middle",
                    size_hint=(None, None))
        self.add_widget(lab)
        return lab

    # ---- state
    def reset(self):
        self.progress, self.done, self.rows_done = 0.0, False, 0
        self.relayout()
        self.redraw()

    def set_done(self):
        self.done = True
        self.relayout()
        self.redraw()

    def _moved(self, *args):
        self.relayout()
        self.redraw()

    # ---- coordinates
    def _x(self, ax):
        return self.x + ax * self.s

    def _y(self, ay):
        return self.top - ay * self.s

    # ---- labels (text, colour and position; the shapes are drawn in redraw)
    def relayout(self):
        self.s = s = (self.width / float(STAGE_W)) if self.width > 1 else 1.0
        self.title.text = TEXT["heading_done"] if self.done else TEXT["heading"]
        self.title.color = FILL_DONE if self.done else LAVENDER
        self._place(self.title, 0, TITLE_Y, STAGE_W, 30, TITLE_SIZE)

        self.sub.text = TEXT["done_sub"]
        has_art = bool(find_asset("pr_done_text"))
        self.sub.opacity = 1 if (self.done and not has_art) else 0
        self._place(self.sub, 0, SUB_Y, STAGE_W, 24, SUB_SIZE)

        for i, lab in enumerate(self.rows):
            self._place(lab, LABEL_X, ROW_Y0 + i * ROW_DY, STAGE_W - LABEL_X, 30, ROW_SIZE)

    def _place(self, lab, left, cy, w, h, size):
        s = self.s
        lab.font_size = size * s
        lab.size = (w * s, h * s)
        lab.text_size = lab.size
        lab.pos = (self._x(left), self._y(cy) - h * s / 2.0)

    # ---- drawing (canvas.before, so the labels above stay on top)
    def redraw(self, *args):
        c = self.canvas.before
        c.clear()
        with c:
            self._put("pr_icon", 0, 0, crop_h=ICON_CROP_H if self.done else None)
            if self.done:
                self._put_vis("pr_badge", BADGE_CX, BADGE_CY, k=BADGE_K)
                self._put_vis("pr_done_text", STAGE_W / 2.0, SUB_Y)
            self._put("pr_track", TRACK_X, TRACK_Y)
            self._fill()
            self._cat()
            self._flag()
            for i in range(3):
                key = "pr_check" if i < self.rows_done else "pr_circle"
                self._put_vis(key, CIRCLE_X, ROW_Y0 + i * ROW_DY)

    def _put(self, key, x, y, k=1.0, crop_h=None):
        """Draw an image with its top-left corner at stage point (x, y)."""
        path = find_asset(key)
        if not path:
            return
        tex = texture(path)
        w, h = tex.size
        if crop_h and crop_h < h:
            if (path, crop_h) not in _crop:
                _crop[(path, crop_h)] = tex.get_region(0, h - crop_h, w, crop_h)
            tex = _crop[(path, crop_h)]
            h = crop_h
        s = self.s
        Color(1, 1, 1, 1)
        Rectangle(texture=tex, pos=(self._x(x), self._y(y + h * k)),
                  size=(w * k * s, h * k * s))

    def _put_vis(self, key, cx, cy, k=1.0):
        """Draw an image so the middle of its visible part lands on stage point (cx, cy)."""
        path = find_asset(key)
        if not path:
            return
        l, t, r, b = visible_box(path)
        self._put(key, cx - (l + r) / 2.0 * k, cy - (t + b) / 2.0 * k, k=k)

    def _fill(self):
        x0, y0, x1, y1 = INNER
        x0, x1 = TRACK_X + x0, TRACK_X + x1
        y0, y1 = TRACK_Y + y0, TRACK_Y + y1
        end = x0 + (x1 - x0) * self.progress
        c = CHAMFER
        if end - x0 <= c:
            return                                   # the cat covers this part anyway
        Color(*(FILL_DONE if self.done else FILL))
        s = self.s
        full = self.progress >= 0.999
        body_end = (x1 - c) if full else end
        Quad(points=[self._x(x0), self._y(y0 + c), self._x(x0 + c), self._y(y0),
                     self._x(x0 + c), self._y(y1), self._x(x0), self._y(y1 - c)])
        Rectangle(pos=(self._x(x0 + c), self._y(y1)),
                  size=((body_end - x0 - c) * s, (y1 - y0) * s))
        if full:
            Quad(points=[self._x(x1 - c), self._y(y0), self._x(x1), self._y(y0 + c),
                         self._x(x1), self._y(y1 - c), self._x(x1 - c), self._y(y1)])

    def _track_visible(self):
        path = find_asset("pr_track")
        if not path:
            return 8, 20, 304, 58
        return visible_box(path)

    def _cat(self):
        path = find_asset("pr_cat")
        if not path:
            return
        cl, ct, cr, cb = visible_box(path)
        tl, _, tr, _ = self._track_visible()
        left = TRACK_X + tl + self.progress * (tr - tl - (cr - cl) - CAT_END_GAP)
        self._put("pr_cat", left - cl, BAR_CY - (ct + cb) / 2.0)

    def _flag(self):
        path = find_asset("pr_flag")
        if not path:
            return
        fl, ft, fr, fb = visible_box(path)
        tl, tt, tr, _ = self._track_visible()
        right = TRACK_X + tr - 1
        bottom = TRACK_Y + tt - FLAG_GAP
        self._put("pr_flag", right - fr, bottom - fb)


# ----------------------------------------------------------------- screen
class ProcessingScreen(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._ev = None
        self._after = None
        self._callback = None
        self._finishing = False
        self._p = self._target = self._floor = 0.0
        self._cap = FLOORS[1] - CAP_GAP
        self.count = 0

        with self.canvas.before:
            Color(*BG)
            self._bg = Rectangle(pos=self.pos, size=self.size)

        root = FloatLayout()
        self.add_widget(root)
        root.add_widget(Art("pr_frame", fb_frame, size_hint=(FRAME_W, FRAME_H),
                            pos_hint={"center_x": .5, "center_y": FRAME_CY}))
        self.stage = ProcessingStage(size_hint=(None, None),
                                     pos_hint={"center_x": .5, "top": STAGE_TOP})
        root.add_widget(self.stage)
        self.steps = Art("pr_step_preview", None, size_hint=(STEPS_W, None),
                         pos_hint={"center_x": .5, "center_y": STEPS_CY})
        self.steps.bind(width=self._fit_steps)
        root.add_widget(self.steps)

        self.bind(pos=self._layout, size=self._layout)
        self._layout()

    def _layout(self, *args):
        self._bg.pos, self._bg.size = self.pos, self.size
        s = self.width * UNIT
        self.stage.size = (STAGE_W * s, STAGE_H * s)

    def _fit_steps(self, *args):
        src = find_asset(self.steps.key)
        if src:
            tw, th = texture(src).size
            self.steps.height = self.steps.width * th / float(tw)
        else:
            self.steps.height = self.steps.width * STEPS_RATIO

    # ---------------------------------------------------------------- public
    def start(self):
        """Call when the page opens."""
        self._stop()
        self.count = 0
        self._p = self._target = self._floor = 0.0
        self._cap = FLOORS[1] - CAP_GAP
        self._callback = None
        self._finishing = False
        self.steps.set_art("pr_step_preview")
        self._fit_steps()
        self.stage.reset()
        self._ev = Clock.schedule_interval(self._tick, 1.0 / FPS)

    @mainthread
    def step_done(self, n):
        """Row n (1 to 3) is finished. Safe to call from any thread."""
        if n <= self.count or n > 3:
            return
        self.count = n
        self._floor = FLOORS[n]
        self._cap = (FLOORS[n + 1] - CAP_GAP) if n < 3 else 1.0
        self._target = max(self._target, self._floor)
        self.stage.rows_done = n
        self.stage.redraw()

    @mainthread
    def finish(self, callback):
        """All work is finished. Fills the bar, shows DONE for HOLD seconds, then callback()."""
        self._callback = callback
        self._finishing = True
        self.step_done(3)

    def on_leave(self, *args):
        self._stop()
        self._callback = None

    # ---------------------------------------------------------------- animation
    def _stop(self):
        for ev in (self._ev, self._after):
            if ev is not None:
                ev.cancel()
        self._ev = self._after = None

    def _tick(self, dt):
        self._target = min(max(self._target + dt * CREEP, self._floor), self._cap)
        self._p += (self._target - self._p) * min(1.0, dt * EASE)
        if self._target >= 1.0 and self._p > 0.995:
            self._p = 1.0
        self.stage.progress = self._p
        self.stage.redraw()
        if self._finishing and self._p >= 1.0:
            self._finishing = False
            if self._ev is not None:
                self._ev.cancel()
                self._ev = None
            self.stage.set_done()
            self.steps.set_art("pr_step_recover")
            self._fit_steps()
            self._after = Clock.schedule_once(self._leave, HOLD)

    def _leave(self, dt):
        cb, self._callback = self._callback, None
        if cb:
            cb()
