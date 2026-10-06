"""
On-device OCR using Google ML Kit's bundled Latin text recognizer (no network,
no Play Services download). Called through pyjnius.

init() MUST run on the main thread (see Bingo.on_start) so the Java classes
are loaded there; run_ocr() is then safe to call from the worker thread.
"""
from dataclasses import dataclass

_J = {}

NEUTRAL_CONF = 80.0


@dataclass
class Word:
    idx: int
    text: str
    conf: float      # 0..100
    x: int
    y: int
    w: int
    h: int
    line: int
    src: str = "ocr"


def init():
    if _J:
        return
    from jnius import autoclass
    _J["BitmapFactory"] = autoclass("android.graphics.BitmapFactory")
    _J["InputImage"] = autoclass("com.google.mlkit.vision.common.InputImage")
    _J["TextRecognition"] = autoclass("com.google.mlkit.vision.text.TextRecognition")
    _J["Options"] = autoclass(
        "com.google.mlkit.vision.text.latin.TextRecognizerOptions")
    _J["Tasks"] = autoclass("com.google.android.gms.tasks.Tasks")

    # Preload every class the worker thread will touch. Lookups by name
    # only work for classes already loaded on the main thread.
    for name in (
        "com.google.mlkit.vision.text.TextRecognizerOptionsInterface",
        "com.google.mlkit.vision.text.TextRecognizer",
        "com.google.mlkit.vision.text.Text",
        "com.google.mlkit.vision.text.Text$TextBlock",
        "com.google.mlkit.vision.text.Text$Line",
        "com.google.mlkit.vision.text.Text$Element",
        "com.google.android.gms.tasks.Task",
    ):
        try:
            autoclass(name)
        except Exception as e:
            print("preload failed:", name, e)


def run_ocr(path):
    """-> (list[Word], has_confidence)"""
    from jnius import cast
    if not _J:
        init()

    bmp = _J["BitmapFactory"].decodeFile(path)
    if bmp is None:
        raise RuntimeError("could not decode image: " + path)

    image = _J["InputImage"].fromBitmap(bmp, 0)     # already upright (phone_io)
    recognizer = _J["TextRecognition"].getClient(_J["Options"].DEFAULT_OPTIONS)

    try:
        task = recognizer.process(image)
        text = cast(
            "com.google.mlkit.vision.text.Text",
            getattr(_J["Tasks"], "await")(task),
        )

        words, line_no, got_conf = [], 0, False
        blocks = text.getTextBlocks()
        for bi in range(blocks.size()):
            lines = blocks.get(bi).getLines()
            for li in range(lines.size()):
                elements = lines.get(li).getElements()
                for ei in range(elements.size()):
                    el = elements.get(ei)
                    box = el.getBoundingBox()
                    t = str(el.getText()).strip()
                    if box is None or not t:
                        continue
                    try:
                        conf = float(el.getConfidence()) * 100.0
                        got_conf = got_conf or conf > 0
                    except Exception:
                        conf = 0.0
                    words.append(Word(len(words), t, conf,
                                      int(box.left), int(box.top),
                                      int(box.right - box.left),
                                      int(box.bottom - box.top),
                                      line_no))
                line_no += 1
    finally:
        recognizer.close()

    if not got_conf:
        for w in words:
            w.conf = NEUTRAL_CONF
    return words, got_conf

def run_ocr_async(path, callback):
    """Call on the MAIN thread. callback(words, has_conf, error) fires on the main thread."""
    from jnius import autoclass, cast, PythonJavaClass, java_method
    if not _J:
        init()

    class OnSuccess(PythonJavaClass):
        __javainterfaces__ = ["com/google/android/gms/tasks/OnSuccessListener"]
        __javacontext__ = "app"

        def __init__(self, fn):
            super().__init__()
            self.fn = fn

        @java_method("(Ljava/lang/Object;)V")
        def onSuccess(self, result):
            self.fn(result)

    class OnFailure(PythonJavaClass):
        __javainterfaces__ = ["com/google/android/gms/tasks/OnFailureListener"]
        __javacontext__ = "app"

        def __init__(self, fn):
            super().__init__()
            self.fn = fn

        @java_method("(Ljava/lang/Exception;)V")
        def onFailure(self, e):
            self.fn(e)

    bmp = _J["BitmapFactory"].decodeFile(path)
    if bmp is None:
        callback(None, False, "could not decode image: " + path)
        return

    image = _J["InputImage"].fromBitmap(bmp, 0)
    recognizer = _J["TextRecognition"].getClient(_J["Options"].DEFAULT_OPTIONS)

    def done_ok(result):
        try:
            text = cast("com.google.mlkit.vision.text.Text", result)
            words, line_no, got_conf = [], 0, False
            blocks = text.getTextBlocks()
            for bi in range(blocks.size()):
                lines = blocks.get(bi).getLines()
                for li in range(lines.size()):
                    elements = lines.get(li).getElements()
                    for ei in range(elements.size()):
                        el = elements.get(ei)
                        box = el.getBoundingBox()
                        t = str(el.getText()).strip()
                        if box is None or not t:
                            continue
                        try:
                            conf = float(el.getConfidence()) * 100.0
                            got_conf = got_conf or conf > 0
                        except Exception:
                            conf = 0.0
                        words.append(Word(len(words), t, conf,
                                          int(box.left), int(box.top),
                                          int(box.right - box.left),
                                          int(box.bottom - box.top),
                                          line_no))
                    line_no += 1
            if not got_conf:
                for w in words:
                    w.conf = NEUTRAL_CONF
            recognizer.close()
            callback(words, got_conf, None)
        except Exception as e:
            import traceback
            traceback.print_exc()
            callback(None, False, str(e))

    def done_fail(e):
        recognizer.close()
        callback(None, False, str(e))

    ok, fail = OnSuccess(done_ok), OnFailure(done_fail)
    _J["_keep"] = (ok, fail, recognizer, bmp, image)   # stop garbage collection
    recognizer.process(image).addOnSuccessListener(ok).addOnFailureListener(fail)