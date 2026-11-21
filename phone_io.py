"""
Android-only helpers: system camera, image picker, and image cleanup.

Both intents hand back a content:// URI. We copy it into the app's cache,
fix its EXIF rotation with Pillow, shrink it, and pass the final file path
to a callback. Callbacks run on Android's thread, so wrap them with
@mainthread on the Kivy side (Scan._on_image already is).
"""
import os
import time
import traceback

from android import activity
from PIL import Image, ImageOps

from jnius import autoclass, cast

MediaStoreImagesMedia = autoclass("android.provider.MediaStore$Images$Media")
PythonActivity = autoclass("org.kivy.android.PythonActivity")
Intent = autoclass("android.content.Intent")
MediaStore = autoclass("android.provider.MediaStore")
ContentValues = autoclass("android.content.ContentValues")
FileUtils = autoclass("android.os.FileUtils")
FileOutputStream = autoclass("java.io.FileOutputStream")
OpenableColumns = autoclass("android.provider.OpenableColumns")

REQ_PICK = 7101
REQ_SHOT = 7102
RESULT_OK = -1

MAX_SIDE = 2400

_callbacks = {}
_shot_uri = None
last_name = ""        # display name of the photo that was just picked or taken
_shot_name = ""

def _activity():
    return PythonActivity.mActivity


def _cache_dir():
    return str(_activity().getCacheDir().getAbsolutePath())


def _copy_uri(uri):
    """Copy a content:// URI to a file in the cache directory."""
    dest = os.path.join(_cache_dir(), "incoming_%d.bin" % int(time.time() * 1000))
    resolver = _activity().getContentResolver()
    ins = resolver.openInputStream(uri)
    outs = FileOutputStream(dest)
    try:
        FileUtils.copy(ins, outs)
    finally:
        outs.close()
        ins.close()
    return dest


def prepare_image(path):
    """Apply EXIF rotation, convert to RGB, shrink, save as a fresh JPEG."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))

    folder = _cache_dir()
    for name in os.listdir(folder):
        if name.startswith("page_") or name.startswith("incoming_"):
            try:
                os.remove(os.path.join(folder, name))
            except OSError:
                pass

    out = os.path.join(folder, "page_%d.jpg" % int(time.time() * 1000))
    img.save(out, "JPEG", quality=92)
    return out

def _display_name(uri):
    cursor = None
    try:
        cursor = _activity().getContentResolver().query(uri, None, None, None, None)
        if cursor is not None and cursor.moveToFirst():
            i = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if i >= 0:
                return str(cursor.getString(i))
    except Exception:
        traceback.print_exc()
    finally:
        if cursor is not None:
            cursor.close()
    return ""

def _on_result(request_code, result_code, intent):
    global last_name, _shot_uri
    cb = _callbacks.pop(request_code, None)
    if cb is None:
        return

    path = None
    try:
        if request_code == REQ_PICK:
            if result_code == RESULT_OK and intent is not None:
                uri = intent.getData()
                if uri is not None:
                    last_name = _display_name(uri)
                    path = prepare_image(_copy_uri(uri))

        elif request_code == REQ_SHOT:
            uri, _shot_uri = _shot_uri, None
            if uri is not None:
                if result_code == RESULT_OK:
                    last_name = _shot_name
                    path = prepare_image(_copy_uri(uri))
                else:
                    # camera cancelled: remove the empty MediaStore row
                    _activity().getContentResolver().delete(uri, None, None)
    except Exception:
        traceback.print_exc()
        path = None

    cb(path)


activity.bind(on_activity_result=_on_result)


def pick_image(callback):
    _callbacks[REQ_PICK] = callback
    intent = Intent(Intent.ACTION_GET_CONTENT)
    intent.setType("image/*")
    intent.addCategory(Intent.CATEGORY_OPENABLE)
    _activity().startActivityForResult(intent, REQ_PICK)


def take_photo(callback):
    """Opens the OnePlus camera app. The shot is also kept in Pictures/Bingo."""
    global _shot_uri, _shot_name
    _callbacks[REQ_SHOT] = callback

    values = ContentValues()
    _shot_name = "bingo_%d.jpg" % int(time.time())
    values.put("_display_name", _shot_name)
    values.put("mime_type", "image/jpeg")
    values.put("relative_path", "Pictures/Bingo")

    resolver = _activity().getContentResolver()
    uri = resolver.insert(MediaStoreImagesMedia.EXTERNAL_CONTENT_URI, values)
    _shot_uri = uri

    intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE)
    intent.putExtra(MediaStore.EXTRA_OUTPUT, cast("android.os.Parcelable", uri))
    _activity().startActivityForResult(intent, REQ_SHOT)