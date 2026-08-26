#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tCarKit application shell, matching the JanPNP desktop conventions."""

import os
import socket
import sys

from PyQt5.QtCore import QEvent, QObject, QSettings, Qt, QTimer
from PyQt5.QtGui import QColor, QIcon, QPainter, QPalette, QPen, QPixmap
from PyQt5.QtWidgets import (
    QAction, QActionGroup, QApplication, QDialog, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QProgressBar, QProxyStyle, QPushButton,
    QStyle, QTabBar, QTabWidget, QVBoxLayout, QWidget,
)

from tcarkit.ui.home_page import HomePage
from tcarkit.ui.performance_page import PCInfoPage


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
        pc_info = getattr(window, "pc_info", None)
        if pc_info:
            pc_info.set_theme(dark)
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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("tCarKit")
        self.setWindowIcon(QIcon(resource_path(os.path.join("assets", "favicon.ico"))))
        self.setWindowFlags(
            (self.windowFlags() | Qt.Window) & ~Qt.WindowContextHelpButtonHint
        )
        self.setFixedSize(380, 154)
        self._edit_height = 154
        self._settings = QSettings("tCar", "tCarKit")
        self._connecting = False
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(20, 14, 20, 14)
        self.message = QLabel("")
        self.message.hide()
        layout.addWidget(self.message)
        self.ip_label = QLabel("IP Address")
        layout.addWidget(self.ip_label)
        self.ip_edit = QLineEdit()
        self.ip_edit.setPlaceholderText("Input your device's IP address")
        self.ip_edit.setText(self._settings.value("connection/ip", "192.168.66.3"))
        self.ip_edit.textChanged.connect(
            lambda value: self._settings.setValue("connection/ip", value)
        )
        self.ip_edit.returnPressed.connect(self._begin_connect)
        layout.addWidget(self.ip_edit)
        self.connect_button = QPushButton("Connect")
        self.connect_button.setMinimumHeight(36)
        self.connect_button.clicked.connect(self._begin_connect)
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
        if not self.ip_edit.text().strip():
            QMessageBox.warning(self, "tCarKit", "IP Address is required")
            return
        self._connecting = True
        self.message.setText("Connecting...")
        self.message.show()
        for widget in (self.ip_label, self.ip_edit, self.connect_button):
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
        ip = self.ip_edit.text().strip()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.0)
        try:
            sock.sendto(b"get_data", (ip, 8888))
            packet, _ = sock.recvfrom(1024)
            if len(packet) not in (40, 56, 60):
                raise RuntimeError(f"Unexpected telemetry packet: {len(packet)} bytes")
            super().accept()
        except Exception as exc:
            self._reset(str(exc)[:100])
        finally:
            sock.close()

    def _reset(self, message):
        self.progress.hide()
        self.message.hide()
        for widget in (self.ip_label, self.ip_edit, self.connect_button):
            widget.show()
        self.setFixedSize(380, self._edit_height)
        self._connecting = False
        QMessageBox.warning(self, "tCarKit", f"Connection failed:\n{message}")

    def get_ip(self):
        return self.ip_edit.text().strip()


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
        self.pc_info = PCInfoPage()
        self._pages = {"PC Info": self.pc_info}
        self._build_menus()
        self.tabs = QTabWidget()
        self.tabs.setTabBar(TabBar())
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(False)
        self.tabs.setStyleSheet(TAB_STYLE)
        self._install_tab_style()
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.setCentralWidget(self.tabs)
        home_index = self.tabs.addTab(self.home, "Home")
        self.tabs.tabBar().setTabButton(home_index, QTabBar.RightSide, None)
        self._restore_session()
        self.home.set_theme(_current_dark)
        self.pc_info.set_theme(_current_dark)
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
        pc_action = QAction("PC Info", self)
        pc_action.setData("PC Info")
        pc_action.triggered.connect(self._open_tab)
        open_menu.addAction(pc_action)
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

    def _restore_session(self):
        names = self._settings.value("session/tabs", [])
        if isinstance(names, str):
            names = [names]
        if "PC Info" in names and not any(
            self.tabs.tabText(index) == "PC Info"
            for index in range(self.tabs.count())
        ):
            index = self.tabs.addTab(self.pc_info, "PC Info")
            self._add_close_button(index)

    def closeEvent(self, event):
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
        self.home.stop()
        event.accept()


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
