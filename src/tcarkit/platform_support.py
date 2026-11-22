"""Desktop integration; keep device/UI logic identical on both platforms."""

import os
import subprocess
import sys


def configure_opengl():
    """Run before importing PyOpenGL or the GL widgets."""
    if sys.platform.startswith("linux") and "PYOPENGL_PLATFORM" not in os.environ:
        if os.environ.get("QT_QPA_PLATFORM", "").startswith("wayland"):
            os.environ["PYOPENGL_PLATFORM"] = "egl"
        elif os.environ.get("DISPLAY"):
            os.environ["PYOPENGL_PLATFORM"] = "glx"


def system_is_dark():
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                               r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                value, _kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return value == 0
        except OSError:
            return False
    if sys.platform.startswith("linux"):
        try:
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                capture_output=True, text=True, timeout=2,
            )
            return "prefer-dark" in result.stdout
        except (OSError, subprocess.TimeoutExpired):
            pass
    return False


def set_titlebar_theme(window, dark):
    if sys.platform != "win32":
        return
    try:
        import ctypes
        # HWND is pointer-sized on 64-bit Windows.
        hwnd = ctypes.c_void_p(int(window.winId()))
        value = ctypes.c_int(bool(dark))
        for attribute in (20, 19):
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
            )
            if result == 0:
                break
    except (AttributeError, OSError):
        pass


def install_window_integration(app, dark_provider):
    if sys.platform != "win32":
        return
    import ctypes
    from PyQt5.QtCore import QEvent, QObject
    from PyQt5.QtWidgets import QWidget

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("tCar.tCarKit.1")
    except (AttributeError, OSError):
        pass

    class TitleBarFilter(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.Show and isinstance(obj, QWidget) and obj.isWindow():
                set_titlebar_theme(obj, dark_provider())
            return False

    # Retain a Python reference for the lifetime of the application.
    app._titlebar_filter = TitleBarFilter(app)
    app.installEventFilter(app._titlebar_filter)
