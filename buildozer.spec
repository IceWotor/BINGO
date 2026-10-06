
[app]
title = Bingo
package.name = bingo
package.domain = org.group4

source.dir = .
source.include_exts = py,png,jpg,kv,ttf,txt
source.exclude_dirs = .buildozer,bin,venv,__pycache__

version = 0.1
requirements = python3,kivy==2.3.0,pillow,sqlite3,pyjnius,android

orientation = portrait
fullscreen = 0

# OnePlus 10T: arm64, Android 12/13 or newer
android.api = 33
android.minapi = 29
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True

# ML Kit text recognition (bundled model, works offline)
android.enable_androidx = True
android.gradle_dependencies = com.google.mlkit:text-recognition:16.0.0

[buildozer]
log_level = 2
warn_on_root = 1