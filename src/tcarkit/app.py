#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tCarKit application shell, matching the JanPNP desktop conventions."""

import os
import socket
import sys
import time
import ipaddress
import json
import urllib.error
import urllib.request

from PyQt5.QtCore import QEvent, QObject, QSettings, Qt, QTimer
from PyQt5.QtGui import QColor, QIcon, QPainter, QPalette, QPen, QPixmap
from PyQt5.QtWidgets import (
    QAction, QActionGroup, QApplication, QDialog, QLabel, QLineEdit, QMenu,
    QMainWindow, QMessageBox, QProgressBar, QProxyStyle, QPushButton,
    QStyle, QTabBar, QTabWidget, QVBoxLayout, QWidget,
)

from tcarkit.ui.home_page import HomePage
from tcarkit.ui.performance_page import PerformancePage
from tcarkit.ui.vision_page import VisionPage


THEME_SYSTEM = "system"
THEME_LIGHT = "light"
THEME_DARK = "dark"
_current_dark = False


def resource_path(relative_path):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    if hasattr(sys, "_MEIPASS"):
        base = os.path.join(base, "tcarkit")
    return os.path.join(base, relative_path)


def win_dark_titlebar(hwnd, enable=True):
    try:
        import ctypes
        value = ctypes.c_int(1 if enable else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(value), ctypes.sizeof(value)
        )
    except Exception:
        pass


def system_is_dark():
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return value == 0
    except Exception:
        return False


def dark_palette():
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.WindowText, QColor(212, 212, 212))
    palette.setColor(QPalette.Base, QColor(26, 26, 26))
    palette.setColor(QPalette.AlternateBase, QColor(37, 37, 38))
    palette.setColor(QPalette.ToolTipBase, QColor(37, 37, 38))
    palette.setColor(QPalette.ToolTipText, QColor(212, 212, 212))
    palette.setColor(QPalette.Text, QColor(212, 212, 212))
    palette.setColor(QPalette.Button, QColor(51, 51, 51))
    palette.setColor(QPalette.ButtonText, QColor(212, 212, 212))
    palette.setColor(QPalette.BrightText, QColor(244, 71, 71))
    palette.setColor(QPalette.Link, QColor(0, 122, 204))
    palette.setColor(QPalette.Highlight, QColor(9, 71, 113))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(100, 100, 100))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(100, 100, 100))
    return palette


def apply_theme(app, mode):
    dark = mode == THEME_DARK or (mode == THEME_SYSTEM and system_is_dark())
    app.setStyle("Fusion")
    app.setPalette(dark_palette() if dark else app.style().standardPalette())
    global _current_dark
    _current_dark = dark
    for window in app.topLevelWidgets():
        if window and window.winId():
            win_dark_titlebar(int(window.winId()), dark)
        home = getattr(window, "home", None)
        if home:
            home.set_theme(dark)
        vision = getattr(window, "vision", None)
        if vision:
            vision.set_theme(dark)
        performance = getattr(window, "performance", None)
        if performance:
            performance.set_theme(dark)
    return dark


class TitleBarFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Show and isinstance(obj, QWidget) and obj.isWindow():
            try:
                win_dark_titlebar(int(obj.winId()), _current_dark)
            except Exception:
                pass
        return False


class IPDialog(QDialog):
    ROUTER_DISCOVERY_URL = "http://192.168.66.1/test"
    AUTH_PORT = 8080

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("tCarKit")
        self.setWindowIcon(QIcon(resource_path(os.path.join("assets", "favicon.ico"))))
        self.setWindowFlags(
            (self.windowFlags() | Qt.Window) & ~Qt.WindowContextHelpButtonHint
        )
        self.setFixedSize(380, 202)
        self._edit_height = 202
        self._settings = QSettings("tCar", "tCarKit")
        self._connecting = False
        self._resolved_ip = None
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(20, 14, 20, 14)
        self.message = QLabel("")
        self.message.hide()
        layout.addWidget(self.message)
        self.username_label = QLabel("Username")
        layout.addWidget(self.username_label)
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Input your username")
        self.username_edit.setText(self._settings.value("auth/user", "tcar"))
        self.username_edit.textChanged.connect(
            lambda value: self._settings.setValue("auth/user", value)
        )
        layout.addWidget(self.username_edit)
        self.password_label = QLabel("Password")
        layout.addWidget(self.password_label)
        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("Input your password")
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setStyleSheet(
            "QLineEdit { lineedit-password-character: 8901; }"
        )
        self.password_edit.setText(self._settings.value("auth/pass", "admin123"))
        self.password_edit.textChanged.connect(
            lambda value: self._settings.setValue("auth/pass", value)
        )
        self.password_edit.returnPressed.connect(self._begin_connect)
        layout.addWidget(self.password_edit)
        self.connect_button = QPushButton("Connect")
        self.connect_button.setMinimumHeight(36)
        self.connect_button.clicked.connect(self._begin_connect)
        layout.addSpacing(8)
        layout.addWidget(self.connect_button)
        self.progress = QProgressBar()
        self.progress.setMaximum(10)
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)
        layout.addStretch(1)

    def _begin_connect(self):
        if self._connecting:
            return
        if not self.username_edit.text().strip():
            QMessageBox.warning(self, "tCarKit", "Username is required")
            return
        if not self.password_edit.text():
            QMessageBox.warning(self, "tCarKit", "Password is required")
            return
        self._connecting = True
        self.message.setText("Connecting...")
        self.message.show()
        for widget in self._edit_widgets():
            widget.hide()
        self.progress.setValue(0)
        self.progress.show()
        self.setFixedSize(380, 80)
        self._ticks = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._progress_step)
        self._timer.start(60)

    def _progress_step(self):
        self._ticks += 1
        self.progress.setValue(self._ticks)
        if self._ticks >= 10:
            self._timer.stop()
            self._try_connect()

    def _try_connect(self):
        sock = None
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.0)
        try:
            self.message.setText("Discovering Core host...")
            QApplication.processEvents()
            ip = self._discover_core_host()
            self.message.setText(f"Authenticating {ip}...")
            QApplication.processEvents()
            self._authenticate(ip)
            sock.sendto(b"get_data", (ip, 8888))
            packet, _ = sock.recvfrom(1024)
            if len(packet) not in (40, 56, 60, 64, 68):
                raise RuntimeError(f"Unexpected telemetry packet: {len(packet)} bytes")
            self._resolved_ip = ip
            super().accept()
        except Exception as exc:
            self._reset(str(exc)[:100])
        finally:
            sock.close()

    def _reset(self, message):
        self.progress.hide()
        self.message.hide()
        for widget in self._edit_widgets():
            widget.show()
        self.setFixedSize(380, self._edit_height)
        self._connecting = False
        QMessageBox.warning(self, "tCarKit", f"Connection failed:\n{message}")

    def get_ip(self):
        return self._resolved_ip

    def _edit_widgets(self):
        return (
            self.username_label,
            self.username_edit,
            self.password_label,
            self.password_edit,
            self.connect_button,
        )

    def _discover_core_host(self):
        request = urllib.request.Request(
            self.ROUTER_DISCOVERY_URL,
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=3.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("status") != 1:
            raise RuntimeError("Invalid response from the tCar router")
        devices = payload.get("devices")
        if not isinstance(devices, list):
            raise RuntimeError("Router response has no device list")
        core = next(
            (
                device for device in devices
                if isinstance(device, dict)
                and device.get("name") == "Core host"
                and device.get("status") is True
            ),
            None,
        )
        if core is None:
            raise RuntimeError("Core host is offline or not registered")
        address = str(ipaddress.ip_address(str(core.get("ip", ""))))
        if ipaddress.ip_address(address).version != 4:
            raise RuntimeError("Core host did not provide an IPv4 address")
        return address

    def _authenticate(self, ip):
        credentials = json.dumps({
            "username": self.username_edit.text().strip(),
            "password": self.password_edit.text(),
        }).encode("utf-8")
        request = urllib.request.Request(
            f"http://{ip}:{self.AUTH_PORT}/api/login",
            data=credentials,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=3.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise RuntimeError("Invalid username or password") from exc
            raise
        if not isinstance(payload, dict) or payload.get("status") != 1:
            raise RuntimeError("Authentication failed")


class TabBar(QTabBar):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().color(QPalette.Window))
        painter.end()
        super().paintEvent(event)


TAB_FRAME_PRIMITIVES = {
    QStyle.PE_FrameTabWidget,
    getattr(QStyle, "PE_FrameTabBarBase", None),
}
TAB_FRAME_PRIMITIVES.discard(None)


class TabWidgetStyle(QProxyStyle):
    def drawPrimitive(self, element, option, painter, widget=None):
        if element in TAB_FRAME_PRIMITIVES:
            return
        super().drawPrimitive(element, option, painter, widget)


TAB_STYLE = """
QTabWidget { border: 0px; }
QTabWidget::pane { border: 0px; margin: 0px; top: 0px; }
QTabWidget::tab-bar { left: 0px; }
QTabBar { border: 0px; }
QTabBar::base { height: 0px; border: 0px; }
"""


class TCarKitWindow(QMainWindow):
    def __init__(self, ip):
        super().__init__()
        self.ip = ip
        self._settings = QSettings("tCar", "tCarKit")
        self._theme_mode = self._settings.value("theme/mode", THEME_SYSTEM)
        self.setWindowTitle("tCarKit")
        self.setWindowIcon(QIcon(resource_path(os.path.join("assets", "favicon.ico"))))
        self.setMinimumSize(800, 500)
        self.home = HomePage(ip)
        self.vision = VisionPage(ip)
        self.performance = PerformancePage(ip)
        self.home.set_active(False)
        self.vision.set_active(False)
        self.performance.set_active(False)
        self._pages = {"Vision": self.vision, "Performance": self.performance}
        self._build_menus()
        self.tabs = QTabWidget()
        self.tabs.setTabBar(TabBar())
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(False)
        self.tabs.setStyleSheet(TAB_STYLE)
        self._install_tab_style()
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tabs)
        home_index = self.tabs.addTab(self.home, "Home")
        self.tabs.tabBar().setTabButton(home_index, QTabBar.RightSide, None)
        self._restore_session()
        self._on_tab_changed(self.tabs.currentIndex())
        self.home.set_theme(_current_dark)
        self.vision.set_theme(_current_dark)
        self.performance.set_theme(_current_dark)
        self.showMaximized()

    def _install_tab_style(self):
        base = QApplication.instance().style()
        self._tab_widget_style = TabWidgetStyle(base)
        self._tab_bar_style = TabWidgetStyle(base)
        self.tabs.setStyle(self._tab_widget_style)
        self.tabs.tabBar().setStyle(self._tab_bar_style)

    @staticmethod
    def _close_icon():
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(160, 160, 160), 1.5))
        painter.drawLine(8, 8, 16, 16)
        painter.drawLine(16, 8, 8, 16)
        painter.end()
        return QIcon(pixmap)

    def _add_close_button(self, index):
        button = QPushButton()
        button.setIcon(self._close_icon())
        button.setFlat(True)
        button.setFixedSize(22, 22)
        button.setStyleSheet(
            "QPushButton{border:none;}"
            "QPushButton:hover{background:rgba(255,0,0,0.25);border-radius:4px;}"
        )
        button.clicked.connect(lambda: self.tabs.tabCloseRequested.emit(index))
        self.tabs.tabBar().setTabButton(index, QTabBar.RightSide, button)

    def _build_menus(self):
        file_menu = self.menuBar().addMenu("File(&F)")
        open_menu = file_menu.addMenu("Open(&O)")
        vision_action = QAction("Vision", self)
        vision_action.setData("Vision")
        vision_action.triggered.connect(self._open_tab)
        open_menu.addAction(vision_action)
        performance_action = QAction("Performance", self)
        performance_action.setData("Performance")
        performance_action.triggered.connect(self._open_tab)
        open_menu.addAction(performance_action)
        file_menu.addSeparator()
        theme_menu = file_menu.addMenu("Theme(&T)")
        self._theme_group = QActionGroup(self)
        self._theme_group.setExclusive(True)
        for label, mode in (
            ("Follow System(&S)", THEME_SYSTEM),
            ("Light(&L)", THEME_LIGHT),
            ("Dark(&D)", THEME_DARK),
        ):
            action = QAction(label, self, checkable=True)
            action.setData(mode)
            action.setChecked(mode == self._theme_mode)
            self._theme_group.addAction(action)
            theme_menu.addAction(action)
        self._theme_group.triggered.connect(self._on_theme)
        file_menu.addSeparator()
        exit_action = QAction("Exit(&X)", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        self._edit_menu = self.menuBar().addMenu("Edit(&E)")
        self._debug_menu = QMenu("Debug Information", self)
        self._show_debug = QAction("Show", self, checkable=True)
        show_debug = self._read_bool_setting("vision/debug/show", False)
        self._show_debug.setChecked(show_debug)
        self._show_debug.toggled.connect(
            lambda enabled: self._set_debug_option("show", enabled)
        )
        self._debug_menu.addAction(self._show_debug)
        self._debug_menu.addSeparator()
        self._fps_debug = QAction("FPS", self, checkable=True)
        show_fps = self._read_bool_setting("vision/debug/fps", True)
        self._fps_debug.setChecked(show_fps)
        self._fps_debug.toggled.connect(
            lambda enabled: self._set_debug_option("fps", enabled)
        )
        self._debug_menu.addAction(self._fps_debug)
        self._frame_delay_debug = QAction("Frame Delay", self, checkable=True)
        show_frame_delay = self._read_bool_setting(
            "vision/debug/frame_delay", True
        )
        self._frame_delay_debug.setChecked(show_frame_delay)
        self._frame_delay_debug.toggled.connect(
            lambda enabled: self._set_debug_option("frame_delay", enabled)
        )
        self._debug_menu.addAction(self._frame_delay_debug)
        self._network_delay_debug = QAction("Network Delay", self, checkable=True)
        show_network_delay = self._read_bool_setting(
            "vision/debug/network_delay", False
        )
        self._network_delay_debug.setChecked(show_network_delay)
        self._network_delay_debug.toggled.connect(
            lambda enabled: self._set_debug_option("network_delay", enabled)
        )
        self._debug_menu.addAction(self._network_delay_debug)
        self.vision.set_debug_visible(show_debug)
        self.vision.set_debug_metric("fps", show_fps)
        self.vision.set_debug_metric("frame_delay", show_frame_delay)
        self.vision.set_debug_metric("network_delay", show_network_delay)

        help_menu = self.menuBar().addMenu("Help(&H)")
        about_action = QAction("About(&A)", self)
        about_action.triggered.connect(
            lambda: QMessageBox.about(
                self, "About tCarKit",
                f"<b>tCarKit</b><br><br>3D attitude and system monitor"
                f"<br><br>Connected to: {self.ip}",
            )
        )
        help_menu.addAction(about_action)

    def _read_bool_setting(self, key, default):
        value = self._settings.value(key, None)
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in ("true", "1"):
                return True
            if normalized in ("false", "0"):
                return False
        # Ignore and remove malformed values instead of carrying legacy or
        # corrupt configuration into a fresh application session.
        self._settings.remove(key)
        return default

    def _set_debug_option(self, option, enabled):
        enabled = bool(enabled)
        self._settings.setValue(f"vision/debug/{option}", enabled)
        if option == "show":
            self.vision.set_debug_visible(enabled)
        else:
            self.vision.set_debug_metric(option, enabled)

    def _on_theme(self, action):
        self._theme_mode = action.data()
        self._settings.setValue("theme/mode", self._theme_mode)
        apply_theme(QApplication.instance(), self._theme_mode)
        self.tabs.setStyleSheet(TAB_STYLE)
        self._install_tab_style()

    def _open_tab(self):
        name = self.sender().data()
        for index in range(self.tabs.count()):
            if self.tabs.tabText(index) == name:
                self.tabs.setCurrentIndex(index)
                return
        index = self.tabs.addTab(self._pages[name], name)
        self._add_close_button(index)
        self.tabs.setCurrentIndex(index)

    def _close_tab(self, index):
        if self.tabs.tabText(index) != "Home":
            self.tabs.removeTab(index)

    def _on_tab_changed(self, index):
        self._edit_menu.clear()
        active_name = self.tabs.tabText(index) if index >= 0 else ""
        self.home.set_active(active_name == "Home")
        self.vision.set_active(active_name == "Vision")
        self.performance.set_active(active_name == "Performance")
        if active_name == "Vision":
            self._edit_menu.addMenu(self._debug_menu)
            self._edit_menu.menuAction().setVisible(True)
        else:
            self._edit_menu.menuAction().setVisible(False)

    def _restore_session(self):
        names = self._settings.value("session/tabs", [])
        if isinstance(names, str):
            names = [names]
        for name in ("Vision", "Performance"):
            if name in names and not any(
                self.tabs.tabText(index) == name
                for index in range(self.tabs.count())
            ):
                index = self.tabs.addTab(self._pages[name], name)
                self._add_close_button(index)

    def closeEvent(self, event):
        if getattr(self, "_shutdown_complete", False):
            event.accept()
            return
        if getattr(self, "_shutdown_started", False):
            event.ignore()
            return
        answer = QMessageBox.question(
            self, "tCarKit", "Are you sure you want to exit?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            event.ignore()
            return
        names = [
            self.tabs.tabText(index) for index in range(self.tabs.count())
            if self.tabs.tabText(index) != "Home"
        ]
        self._settings.setValue("session/tabs", names)
        self._shutdown_started = True
        self.hide()
        QApplication.setQuitOnLastWindowClosed(False)
        workers = []
        workers.extend(self.home.stop())
        workers.extend(self.vision.stop())
        workers.extend(self.performance.stop())
        self._shutdown_workers = workers
        self._shutdown_deadline = time.monotonic() + 1.75
        self._shutdown_timer = QTimer(self)
        self._shutdown_timer.setInterval(20)
        self._shutdown_timer.timeout.connect(self._finish_shutdown)
        self._shutdown_timer.start()
        event.ignore()

    def _finish_shutdown(self):
        running = []
        for worker in self._shutdown_workers:
            if hasattr(worker, "isRunning"):
                if worker.isRunning():
                    running.append(worker)
            elif worker.is_alive():
                running.append(worker)
        if running and time.monotonic() < self._shutdown_deadline:
            return
        # A camera connect can remain inside the standard-library URL opener
        # until its 1.5 s timeout. At the deadline, terminate only residual Qt
        # receivers during final process shutdown to avoid destroying a live
        # QThread object.
        for worker in running:
            if hasattr(worker, "terminate"):
                worker.terminate()
                worker.wait(100)
        self._shutdown_timer.stop()
        self._shutdown_complete = True
        self._settings.sync()
        QApplication.setQuitOnLastWindowClosed(True)
        self.close()
        # All application workers are stopped above. Qt/OpenGL can otherwise
        # remain in native teardown after the event loop has ended, leaving a
        # headless tCarKit process behind for several seconds.
        os._exit(0)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("tCarKit")
    app.setOrganizationName("tCar")
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("tCar.tCarKit.1")
    except Exception:
        pass
    app.setWindowIcon(QIcon(resource_path(os.path.join("assets", "favicon.ico"))))
    settings = QSettings("tCar", "tCarKit")
    apply_theme(app, settings.value("theme/mode", THEME_SYSTEM))
    app.installEventFilter(TitleBarFilter(app))
    dialog = IPDialog()
    if dialog.exec_() != QDialog.Accepted:
        return 0
    window = TCarKitWindow(dialog.get_ip())
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
