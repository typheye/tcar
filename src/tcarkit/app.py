import os
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QIcon, QPalette
from PyQt5.QtWidgets import QAction, QActionGroup, QApplication, QMainWindow, QTabWidget

from tcarkit.ui.home_page import HomePage
from tcarkit.ui.performance_page import PCInfoPage


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    package = os.path.join(base, "tcarkit") if hasattr(sys, "_MEIPASS") else base
    return os.path.join(package, "assets", name)


def system_is_dark():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return value == 0
    except Exception:
        return False


def apply_theme(app, mode):
    dark = mode == "dark" or (mode == "system" and system_is_dark())
    app.setStyle("Fusion")
    if dark:
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(30, 30, 30))
        palette.setColor(QPalette.WindowText, QColor(212, 212, 212))
        palette.setColor(QPalette.Base, QColor(26, 26, 26))
        palette.setColor(QPalette.Text, QColor(212, 212, 212))
        palette.setColor(QPalette.Button, QColor(51, 51, 51))
        palette.setColor(QPalette.ButtonText, QColor(212, 212, 212))
        palette.setColor(QPalette.Highlight, QColor(9, 71, 113))
        palette.setColor(QPalette.HighlightedText, Qt.white)
        app.setPalette(palette)
    else:
        app.setPalette(app.style().standardPalette())
    for window in app.topLevelWidgets():
        home = getattr(window, "home", None)
        if home:
            home.view.set_dark_theme(dark)
    return dark


class TCarKitWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("tCarKit")
        self.setWindowIcon(QIcon(resource_path("favicon.ico")))
        self.setMinimumSize(1000, 700)
        self.home = HomePage()
        self.home.view.set_dark_theme(self.palette().color(QPalette.Window).lightness() < 128)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.home, "Home")
        self.tabs.addTab(PCInfoPage(), "PC Info")
        self.setCentralWidget(self.tabs)
        self._build_menu()

    def _build_menu(self):
        file_menu = self.menuBar().addMenu("File")
        for label, index in (("Home", 0), ("PC Info", 1)):
            action = QAction(label, self)
            action.triggered.connect(lambda checked=False, i=index: self.tabs.setCurrentIndex(i))
            file_menu.addAction(action)
        theme_menu = file_menu.addMenu("Theme")
        group = QActionGroup(self)
        for label, mode in (("Follow System", "system"), ("Light", "light"), ("Dark", "dark")):
            action = QAction(label, self, checkable=True)
            action.triggered.connect(lambda checked=False, m=mode: apply_theme(QApplication.instance(), m))
            group.addAction(action)
            theme_menu.addAction(action)
        theme_menu.actions()[0].setChecked(True)
        file_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

    def closeEvent(self, event):
        self.home.stop()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    apply_theme(app, "system")
    window = TCarKitWindow()
    window.showMaximized()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
