@echo off
set ADB=C:\platform-tools\adb.exe
set PKG=org.group4.bingo

%ADB% shell rm -rf /data/local/tmp/src
%ADB% shell mkdir -p /data/local/tmp/src
%ADB% push main.py /data/local/tmp/src/
%ADB% push phone_io.py /data/local/tmp/src/
%ADB% push bingo.kv /data/local/tmp/src/
%ADB% push reconstruction /data/local/tmp/src/
%ADB% push assets /data/local/tmp/src/

%ADB% shell "run-as %PKG% cp -r /data/local/tmp/src/. files/app/"
%ADB% shell "run-as %PKG% rm -f files/app/main.pyc"
%ADB% shell am force-stop %PKG%
%ADB% shell monkey -p %PKG% -c android.intent.category.LAUNCHER 1
