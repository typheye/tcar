"""Core-host device setup and live two-axis gimbal calibration."""

import copy
import json
import queue
import time
import urllib.error
import urllib.request

from PyQt5.QtCore import QSettings, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QScrollArea, QSlider, QSpinBox,
    QVBoxLayout, QWidget,
)


class SetupWorker(QThread):
    succeeded = pyqtSignal(str, dict)
    failed = pyqtSignal(str, str)

    def __init__(self, ip, credentials, parent=None):
        super().__init__(parent)
        self.base = f"http://{ip}:8080"
        self.credentials = dict(credentials)
        self.token = None
        self.jobs = queue.Queue()

    def _http(self, path, body=None, token=None):
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base + path,
            data=None if body is None else json.dumps(body).encode(),
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=2.0) as response:
                result = json.load(response)
            if not isinstance(result, dict): raise ValueError("invalid Core response")
            return result
        except urllib.error.HTTPError as error:
            try:
                detail = json.loads(error.read()).get("error", str(error))
            except (ValueError, AttributeError):
                detail = str(error)
            if error.code == 401: self.token = None
            raise RuntimeError(str(detail)) from error

    def run(self):
        while True:
            job = self.jobs.get()
            if job is None: return
            kind, body = job
            try:
                if self.token is None:
                    self.token = self._http("/api/login", self.credentials).get("token")
                    if not self.token:
                        raise RuntimeError("Core host needs the OOBE API update")
                path = "config" if kind in ("load", "save") else kind
                result = self._http("/api/v1/setup/" + path, body, self.token)
                if kind == "save":
                    account = body["account"]
                    self.credentials["username"] = account["username"]
                    if account.get("password"):
                        self.credentials["password"] = account["password"]
                    self.token = None
                self.succeeded.emit(kind, result)
            except Exception as error:
                self.failed.emit(kind, str(error))


class OOBEPage(QWidget):
    needs_setup = pyqtSignal()

    def __init__(self, ip, credentials, parent=None):
        super().__init__(parent)
        self.config = None
        self.session = None
        self.positions = {}
        self.busy = False
        self.active = False
        self.dirty = False
        self.filling = False
        self.leaving = False
        self.closing = False
        self.last_heartbeat = 0.0
        self.next_servo = 1
        self._saving_account = None
        self.worker = SetupWorker(ip, credentials, self)
        self.worker.succeeded.connect(self._done)
        self.worker.failed.connect(self._failed)
        self.worker.start()
        root = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        contents = QWidget()
        form = QVBoxLayout(contents)
        self.device_group = QGroupBox("Device")
        device = QFormLayout(self.device_group)
        self.name = QLineEdit()
        self.name.setMaxLength(64)
        self.initialized = QCheckBox("Device setup complete")
        self.revision = QLabel()
        device.addRow("Device name", self.name)
        device.addRow("Configuration", self.revision)
        device.addRow(self.initialized)
        form.addWidget(self.device_group)

        self.servo_group = QGroupBox("Gimbal calibration — pulse width (µs)")
        servos = QVBoxLayout(self.servo_group)
        hint = QLabel("Start calibration to move the sliders. 1 = tilt, 2 = pan. "
                      "Move slowly while watching the mechanism; stop before a mechanical limit. "
                      "Position is the commanded pulse (no hardware position feedback).")
        hint.setWordWrap(True)
        servos.addWidget(hint)
        row = QHBoxLayout()
        self.start_button = QPushButton("Start calibration")
        self.end_button = QPushButton("Stop / release control")
        self.start_button.clicked.connect(lambda: self._request("begin", {}))
        self.end_button.clicked.connect(self._release)
        row.addWidget(self.start_button)
        row.addWidget(self.end_button)
        servos.addLayout(row)
        self.servo_widgets = {}
        for i, title in ((1, "Servo 1 — tilt"), (2, "Servo 2 — pan")):
            box = QGroupBox(title)
            layout = QVBoxLayout(box)
            fields = QHBoxLayout()
            values = {}
            for key, label in (("min_us", "Min"), ("default_us", "Default"), ("max_us", "Max")):
                field = QSpinBox()
                field.setRange(500, 2500)
                field.setSuffix(" µs")
                field.setMaximumWidth(130)
                field.valueChanged.connect(self._changed)
                fields.addWidget(QLabel(label))
                fields.addWidget(field)
                values[key] = field
            layout.addLayout(fields)
            motion = QHBoxLayout()
            slider = QSlider(Qt.Horizontal)
            slider.setRange(500, 2500)
            slider.setSingleStep(1)
            target = QSpinBox()
            target.setRange(500, 2500)
            target.setSuffix(" µs")
            target.setMaximumWidth(130)
            slider.valueChanged.connect(target.setValue)
            target.valueChanged.connect(slider.setValue)
            reported = QLabel("Commanded: --")
            motion.addWidget(slider, 1)
            motion.addWidget(target)
            motion.addWidget(reported)
            layout.addLayout(motion)
            buttons = QHBoxLayout()
            marks = []
            for key, label in (("min_us", "Set min here"), ("default_us", "Set default here"), ("max_us", "Set max here")):
                button = QPushButton(label)
                button.clicked.connect(lambda _checked=False, axis=i, field=values[key]: self._mark(axis, field))
                buttons.addWidget(button)
                marks.append(button)
            center = QPushButton("Go to default")
            center.clicked.connect(lambda _checked=False, value=values["default_us"], control=target: control.setValue(value.value()))
            buttons.addWidget(center)
            marks.append(center)
            layout.addLayout(buttons)
            values.update(slider=slider, target=target, reported=reported, marks=marks)
            self.servo_widgets[i] = values
            servos.addWidget(box)
        form.addWidget(self.servo_group)

        self.battery_group = QGroupBox("Battery — 2S pack")
        battery = QFormLayout(self.battery_group)
        self.empty = self._decimal(5.8, 8.8, " V", 2)
        self.full = self._decimal(5.8, 8.8, " V", 2)
        self.runtime = self._decimal(1, 10080, " min", 1)
        battery.addRow("Empty voltage", self.empty)
        battery.addRow("Full voltage", self.full)
        battery.addRow("Reference runtime at full charge", self.runtime)
        estimate = QLabel("Core estimates remaining runtime as full runtime × battery percentage.")
        estimate.setWordWrap(True)
        battery.addRow(estimate)
        form.addWidget(self.battery_group)

        self.account_group = QGroupBox("Device application account")
        account = QFormLayout(self.account_group)
        self.username = QLineEdit()
        self.username.setMaxLength(64)
        self.password = QLineEdit()
        self.password.setMaxLength(256)
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("Leave blank to keep current password (8+ characters to change)")
        self.confirm = QLineEdit()
        self.confirm.setMaxLength(256)
        self.confirm.setEchoMode(QLineEdit.Password)
        account.addRow("Username", self.username)
        account.addRow("New password", self.password)
        account.addRow("Confirm password", self.confirm)
        form.addWidget(self.account_group)
        for field in (self.name, self.username, self.password, self.confirm):
            field.textChanged.connect(self._changed)
        self.initialized.toggled.connect(self._changed)
        form.addStretch(1)
        scroll.setWidget(contents)
        root.addWidget(scroll, 1)
        actions = QHBoxLayout()
        self.reload_button = QPushButton("Reload from 4B")
        self.reload_button.clicked.connect(self._reload)
        self.save_button = QPushButton("Save and apply to 4B")
        self.save_button.clicked.connect(self._save)
        actions.addWidget(self.reload_button)
        actions.addStretch(1)
        actions.addWidget(self.save_button)
        root.addLayout(actions)
        self.status = QLabel("Reading device configuration…")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        self._update_controls()
        QTimer.singleShot(0, lambda: self._request("load"))

    def _decimal(self, low, high, suffix, decimals):
        field = QDoubleSpinBox()
        field.setRange(low, high)
        field.setDecimals(decimals)
        field.setSingleStep(0.05 if suffix == " V" else 1.0)
        field.setSuffix(suffix)
        field.valueChanged.connect(self._changed)
        return field

    def _changed(self, *_args):
        if not self.filling:
            self.dirty = True
            self.status.setText("Unsaved changes — save to apply device settings.")

    def _update_controls(self):
        loaded = self.config is not None
        for group in (self.device_group, self.servo_group, self.battery_group, self.account_group):
            group.setEnabled(loaded and not self.closing)
        self.reload_button.setEnabled(not self.busy and not self.session and not self.closing)
        self.save_button.setEnabled(loaded and not self.busy and not self.leaving and not self.closing)
        self.start_button.setEnabled(loaded and not self.session and not self.busy and self.active)
        self.end_button.setEnabled(bool(self.session) and not self.leaving)
        for values in self.servo_widgets.values():
            for widget in (values["slider"], values["target"], *values["marks"]):
                widget.setEnabled(bool(self.session) and not self.leaving and not self.closing)

    def _request(self, kind, body=None):
        if self.busy: return
        self.busy = True
        self._update_controls()
        self.worker.jobs.put((kind, body))

    def _fill(self, data):
        self.filling = True
        try:
            self.config = copy.deepcopy(data)
            self.name.setText(data["device_name"])
            self.initialized.setChecked(data["initialized"])
            self.revision.setText(f"v{data['schema_version']} / revision {data['revision']}")
            self.username.setText(data["account"]["username"])
            self.password.clear()
            self.confirm.clear()
            self.empty.setValue(data["battery"]["empty_voltage"])
            self.full.setValue(data["battery"]["full_voltage"])
            self.runtime.setValue(data["battery"]["full_runtime_minutes"])
            for i, widgets in self.servo_widgets.items():
                for key in ("min_us", "default_us", "max_us"):
                    widgets[key].setValue(data["servos"][str(i)][key])
                widgets["target"].setValue(widgets["default_us"].value())
            self.dirty = False
        finally:
            self.filling = False

    def _done(self, kind, data):
        self.busy = False
        if kind in ("load", "save"):
            self._fill(data)
            if kind == "save":
                self.session = None
                settings = QSettings("tCar", "tCarKit")
                settings.setValue("auth/user", self._saving_account["username"])
                if self._saving_account.get("password"):
                    settings.setValue("auth/pass", self._saving_account["password"])
                self._saving_account = None
            self.status.setText("Configuration saved and applied on 4B." if kind == "save" else "Configuration loaded from 4B.")
            if kind == "load" and not data["initialized"]:
                self.needs_setup.emit()
        elif kind == "begin":
            self.session = data["session"]
            self._positions(data["positions"], reset_targets=True)
            self.status.setText("Calibration active — gimbal control reserved; R2 cancels calibration.")
        elif kind == "preview":
            self._positions(data["positions"])
        elif kind == "end":
            self.session = None
            self._positions(data["positions"], reset_targets=True)
            self.status.setText("Calibration stopped. Saved limits restored; edits remain unsaved.")
        self._continue_leave()
        self._update_controls()

    def _positions(self, positions, reset_targets=False):
        self.positions = {int(k): int(v) for k, v in positions.items()}
        for i, position in self.positions.items():
            self.servo_widgets[i]["reported"].setText(f"Commanded: {position} µs")
            if reset_targets:
                self.servo_widgets[i]["target"].setValue(position)

    def _failed(self, kind, message):
        self.busy = False
        # A timed-out begin may still have reached Core: its lease will expire.
        # Stop heartbeats after any session error so control is always released.
        self.session = None
        self.status.setText(f"{kind}: {message}. If calibration was active, Core releases it within 5 seconds.")
        self._continue_leave()
        self._update_controls()

    def _reload(self):
        if self.dirty and QMessageBox.question(self, "OOBE", "Discard unsaved edits and reload?") != QMessageBox.Yes:
            return
        self._request("load")

    def _mark(self, axis, field):
        if axis in self.positions:
            field.setValue(self.positions[axis])

    def _save(self):
        if self.password.text() != self.confirm.text():
            self.status.setText("Passwords do not match."); return
        if self.password.text() and len(self.password.text()) < 8:
            self.status.setText("New password needs at least 8 characters."); return
        if not self.name.text().strip() or not self.username.text().strip():
            self.status.setText("Device name and username are required."); return
        if self.full.value() - self.empty.value() < 0.2 - 1e-9:
            self.status.setText("Full voltage must exceed empty voltage by at least 0.2 V."); return
        servos = {}
        for i, widgets in self.servo_widgets.items():
            values = {k: widgets[k].value() for k in ("min_us", "default_us", "max_us")}
            if not values["min_us"] <= values["default_us"] <= values["max_us"] or values["min_us"] == values["max_us"]:
                self.status.setText(f"Servo {i}: require min <= default <= max, with min < max."); return
            servos[str(i)] = values
        data = copy.deepcopy(self.config)
        data.update(device_name=self.name.text().strip(), initialized=self.initialized.isChecked(),
                    servos=servos, session=self.session,
                    battery={"empty_voltage": self.empty.value(), "full_voltage": self.full.value(),
                             "full_runtime_minutes": self.runtime.value()},
                    account={"username": self.username.text().strip(), "password": self.password.text()})
        self._saving_account = dict(data["account"])
        self.status.setText("Saving and applying device configuration…")
        self._request("save", data)

    def _tick(self):
        if not self.session or self.busy or self.leaving: return
        for i in (self.next_servo, 3 - self.next_servo):
            target = self.servo_widgets[i]["target"].value()
            if target != self.positions.get(i):
                self.next_servo = 3 - i
                self._request("preview", {"session": self.session, "servo_id": i, "pulse_us": target})
                return
        if time.monotonic() - self.last_heartbeat >= 1.0:
            self.last_heartbeat = time.monotonic()
            self._request("preview", {"session": self.session})

    def _release(self):
        self.leaving = True
        self._continue_leave()
        self._update_controls()

    def _continue_leave(self):
        if self.busy: return
        if self.leaving and self.session:
            self._request("end", {"session": self.session})
        else:
            self.leaving = False
            if self.closing:
                self.worker.jobs.put(None)

    def set_active(self, active):
        self.active = bool(active)
        if not active and (self.session or self.busy):
            self._release()
        self._update_controls()

    def set_theme(self, _dark):
        self.update()

    def stop(self):
        self.timer.stop()
        self.closing = True
        self._release()
        return (self.worker,)
