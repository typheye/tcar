import platform
import time

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QFormLayout, QGroupBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class PCInfoPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        metrics = QHBoxLayout()
        self.cpu = self._metric("CPU")
        self.memory = self._metric("Memory")
        self.uptime = self._metric("Uptime")
        for metric in (self.cpu, self.memory, self.uptime):
            metrics.addWidget(metric)
        root.addLayout(metrics)

        details = QGroupBox("System")
        form = QFormLayout(details)
        for key, value in (("OS", platform.platform()),
                           ("Python", platform.python_version()),
                           ("Machine", platform.machine()),
                           ("Processor", platform.processor())):
            label = QLabel(value or "-")
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            form.addRow(QLabel(key), label)
        root.addWidget(details)
        root.addStretch(1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.refresh()

    @staticmethod
    def _metric(title):
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        value = QLabel("--")
        value.setAlignment(Qt.AlignCenter)
        value.setStyleSheet("font: bold 24px monospace;")
        layout.addWidget(value)
        box.value_label = value
        return box

    def refresh(self):
        try:
            import psutil
            self.cpu.value_label.setText(f"{psutil.cpu_percent():.1f}%")
            self.memory.value_label.setText(f"{psutil.virtual_memory().percent:.1f}%")
            elapsed = max(0, int(time.time() - psutil.boot_time()))
            self.uptime.value_label.setText(f"{elapsed // 3600} h")
        except ImportError:
            self.cpu.value_label.setText("install psutil")
