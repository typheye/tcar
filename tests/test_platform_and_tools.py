"""Regression coverage for platform dispatch and non-destructive releases."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
from tcarkit import platform_support as platform

spec = importlib.util.spec_from_file_location("manage", PROJECT / "scripts/manage.py")
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)


class PlatformTests(unittest.TestCase):
    def test_linux_backend_selected_before_gl_import(self):
        for qt, expected in (("wayland", "egl"), ("xcb", "glx")):
            with patch.object(platform.sys, "platform", "linux"), patch.dict(os.environ, {"QT_QPA_PLATFORM": qt, "DISPLAY": ":1"}, clear=True):
                platform.configure_opengl()
                self.assertEqual(os.environ["PYOPENGL_PLATFORM"], expected)

    def test_explicit_gl_backend_not_overwritten(self):
        with patch.object(platform.sys, "platform", "linux"), patch.dict(os.environ, {"DISPLAY": ":1", "PYOPENGL_PLATFORM": "egl"}, clear=True):
            platform.configure_opengl()
            self.assertEqual(os.environ["PYOPENGL_PLATFORM"], "egl")

    def test_linux_commands_not_executed_on_windows(self):
        registry = types.ModuleType("winreg")
        registry.HKEY_CURRENT_USER = 1
        registry.OpenKey = Mock(side_effect=OSError("no setting"))
        with patch.object(platform.sys, "platform", "win32"), patch.dict(sys.modules, {"winreg": registry}), patch.object(platform.subprocess, "run") as run:
            self.assertFalse(platform.system_is_dark())
            run.assert_not_called()

    def test_windows_registry_theme(self):
        registry = types.ModuleType("winreg")
        registry.HKEY_CURRENT_USER = 1
        key = Mock()
        context = Mock(__enter__=Mock(return_value=key), __exit__=Mock(return_value=False))
        registry.OpenKey = Mock(return_value=context)
        registry.QueryValueEx = Mock(return_value=(0, 4))
        with patch.object(platform.sys, "platform", "win32"), patch.dict(sys.modules, {"winreg": registry}):
            self.assertTrue(platform.system_is_dark())

    def test_missing_gsettings_falls_back(self):
        with patch.object(platform.sys, "platform", "linux"), patch.object(platform.subprocess, "run", side_effect=FileNotFoundError):
            self.assertFalse(platform.system_is_dark())


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="pc-app tests ")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        context = patch.object(manage, "ROOT", self.root)
        context.start()
        self.addCleanup(context.stop)

    def test_executable_name_matches_host(self):
        with patch.object(manage.sys, "platform", "win32"):
            self.assertEqual(manage.executable_name(), "tCarKit.exe")
        with patch.object(manage.sys, "platform", "linux"):
            self.assertEqual(manage.executable_name(), "tCarKit")

    def test_clean_preserves_distribution_and_install(self):
        for folder in ("build", "dist", "installed", "src/__pycache__"):
            (self.root / folder).mkdir(parents=True)
            (self.root / folder / "artifact").write_text("keep")
        manage.clean(argparse.Namespace(all=False))
        self.assertFalse((self.root / "build").exists())
        self.assertFalse((self.root / "src/__pycache__").exists())
        self.assertTrue((self.root / "dist/artifact").exists())
        self.assertTrue((self.root / "installed/artifact").exists())
        manage.clean(argparse.Namespace(all=True))
        self.assertFalse((self.root / "dist").exists())
        self.assertTrue((self.root / "installed/artifact").exists())

    def test_atomic_publish_failure_preserves_previous_file(self):
        source, target = self.root / "new", self.root / "published"
        source.write_bytes(b"new executable")
        target.write_bytes(b"previous executable")
        with patch.object(manage.os, "replace", side_effect=PermissionError("in use")):
            with self.assertRaises(PermissionError): manage.atomic_copy(source, target)
        self.assertEqual(target.read_bytes(), b"previous executable")
        self.assertEqual(list(self.root.glob(".tcarkit-*")), [])

    def test_failed_build_keeps_old_dist(self):
        (self.root / "dist").mkdir()
        old = self.root / "dist" / manage.executable_name()
        old.write_bytes(b"previous")
        with patch.object(manage, "check_dependencies"), patch.object(manage, "run", side_effect=subprocess.CalledProcessError(1, "PyInstaller")):
            with self.assertRaises(subprocess.CalledProcessError):
                manage.build(argparse.Namespace(install=False))
        self.assertEqual(old.read_bytes(), b"previous")

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux desktop integration")
    def test_install_is_independent_of_checkout(self):
        (self.root / "dist").mkdir()
        (self.root / "dist/tCarKit").write_bytes(b"executable")
        assets = self.root / "src/tcarkit/assets"
        assets.mkdir(parents=True)
        (assets / "favicon.ico").write_bytes(b"icon")
        (assets.parent / "metadata.json").write_text('{}')
        data = self.root / "xdg data"
        with patch.dict(os.environ, {"XDG_DATA_HOME": str(data)}), patch.object(manage.shutil, "which", side_effect=lambda name: "/usr/bin/env" if name == "env" else None), patch.object(manage.Path, "home", return_value=self.root):
            manage.install(argparse.Namespace(desktop=True))
        entry = (data / "applications/tcarkit.desktop").read_text()
        self.assertIn(f'Exec=/usr/bin/env "{data / "tcarkit/tCarKit"}"', entry)
        self.assertIn(f'TryExec={data / "tcarkit/tCarKit"}', entry)
        self.assertIn("StartupNotify=false", entry)
        manage.clean(argparse.Namespace(all=True))
        self.assertTrue((data / "tcarkit/tCarKit").is_file())
        self.assertEqual((self.root / "Desktop/tcarkit.desktop").read_text(), entry)

    def test_linux_launcher_updates_in_place_and_cleans_only_our_duplicates(self):
        data, desktop = self.root / "data", self.root / "Desktop"
        applications = data / "applications"
        applications.mkdir(parents=True)
        desktop.mkdir()
        canonical = applications / "tcarkit.desktop"
        old = '[Desktop Entry]\nName=tCarKit\nExec=/deleted/linux-pc/dist/tCarKit\n'
        canonical.write_text(old)
        inode = canonical.stat().st_ino
        duplicate = applications / "old-tCarKit.desktop"
        duplicate.write_text(old)
        (desktop / "old-tCarKit.desktop").write_text(old)
        unrelated = applications / "other.desktop"
        unrelated.write_text('[Desktop Entry]\nName=Another app\nExec=/usr/bin/true\n')
        with patch.object(manage.shutil, "which", side_effect=lambda name: "/usr/bin/env" if name == "env" else None), patch.object(manage.Path, "home", return_value=self.root):
            manage.install_linux_launchers(data / "tcarkit/tCarKit", data / "tcarkit/favicon.ico", applications, desktop, False)
        self.assertEqual(canonical.stat().st_ino, inode)
        self.assertFalse(duplicate.exists())
        self.assertFalse((desktop / "old-tCarKit.desktop").exists())
        self.assertTrue((desktop / "tcarkit.desktop").exists())
        self.assertTrue(unrelated.exists())
        self.assertNotIn('Exec="', canonical.read_text())
        self.assertNotIn('linux-pc', canonical.read_text())

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux GIO desktop parsing")
    def test_gio_resolves_and_launches_generated_desktop_entries(self):
        python = Path('/usr/bin/python3')
        probe = subprocess.run([str(python), '-c', 'from gi.repository import Gio, GLib'], capture_output=True) if python.exists() else None
        if probe is None or probe.returncode:
            self.skipTest('system Python GIO bindings unavailable')
        paths = tempfile.TemporaryDirectory(prefix='tcarkit-gio-')
        self.addCleanup(paths.cleanup)
        check = '''
import sys
from gi.repository import Gio, GLib
app = Gio.DesktopAppInfo.new_from_filename(sys.argv[1])
assert app.should_show()
assert GLib.find_program_in_path(app.get_executable()), repr(app.get_executable())
assert app.launch([], None)
'''
        for name in ('plain', 'with spaces', 'with "quote" and $dollar and %percent'):
            folder = Path(paths.name) / name
            folder.mkdir()
            marker = folder / 'launched'
            binary = folder / 'tCarKit'
            binary.write_text('#!/usr/bin/env python3\nfrom pathlib import Path\nPath(__file__).with_name("launched").touch()\n')
            binary.chmod(0o755)
            launcher = folder / 'tcarkit.desktop'
            launcher.write_text(manage.desktop_entry(binary, folder / 'icon.ico'))
            result = subprocess.run([str(python), '-c', check, str(launcher)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            import time
            deadline = time.monotonic() + 3
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(marker.exists(), f'launcher did not execute {binary}')
            if shutil.which('desktop-file-validate'):
                result = subprocess.run(['desktop-file-validate', str(launcher)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_windows_install_shortcut_paths_are_not_code(self):
        (self.root / "dist").mkdir()
        (self.root / "dist/tCarKit.exe").write_bytes(b"executable")
        assets = self.root / "src/tcarkit/assets"
        assets.mkdir(parents=True)
        (assets / "favicon.ico").write_bytes(b"icon")
        (assets.parent / "metadata.json").write_text('{}')
        with patch.object(manage, "platform_name", return_value="windows"), patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "Windows user")} ), patch.object(manage, "run") as run:
            manage.install(argparse.Namespace(desktop=True))
        environment = run.call_args.kwargs["env"]
        self.assertTrue(Path(environment["TCARKIT_EXE"]).is_file())
        self.assertNotIn(environment["TCARKIT_EXE"], run.call_args.kwargs["input"])


class PackagingTests(unittest.TestCase):
    def test_shared_login_and_sensor_widgets_start(self):
        code = """
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer
from tcarkit.app import IPDialog, apply_theme, THEME_DARK, THEME_LIGHT
from tcarkit.platform_support import install_window_integration
from tcarkit.ui.sensor_page import SensorChart, SensorTableModel
app = QApplication([])
install_window_integration(app, lambda: True)
apply_theme(app, THEME_DARK)
dialog = IPDialog()
assert not dialog.windowIcon().isNull()
dialog.show()
chart = SensorChart(SensorTableModel())
chart.resize(800, 400)
chart.show()
QTimer.singleShot(100, app.quit)
assert app.exec_() == 0
apply_theme(app, THEME_LIGHT)
"""
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=str(PROJECT / "src"))
        result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_spec_has_windows_resources_and_common_assets(self):
        source = PROJECT / "src/tcarkit"
        # Execute both spec branches with build actions stubbed. Native builds
        # remain the job of the Windows/Linux CI runners.
        versioninfo = types.ModuleType("PyInstaller.utils.win32.versioninfo")
        for name in ("VSVersionInfo", "FixedFileInfo", "StringFileInfo", "StringTable", "StringStruct", "VarFileInfo", "VarStruct"):
            setattr(versioninfo, name, Mock(name=name))
        for host in ("linux", "win32"):
            analysis = Mock(return_value=types.SimpleNamespace(pure=[], scripts=[], binaries=[], datas=[]))
            exe = Mock()
            hooks = types.ModuleType("PyInstaller.utils.hooks")
            hooks.collect_submodules = lambda _name: ["OpenGL.platform.glx", "OpenGL.platform.win32"]
            with patch.object(sys, "platform", host), patch.dict(sys.modules, {"PyInstaller.utils.hooks": hooks, "PyInstaller.utils.win32.versioninfo": versioninfo}):
                exec(compile((source / "tcarkit.spec").read_text(), "tcarkit.spec", "exec"),
                     {"SPECPATH": str(source), "Analysis": analysis, "PYZ": Mock(), "EXE": exe})
            options = exe.call_args.kwargs
            self.assertEqual("version" in options, host == "win32")
            self.assertEqual("icon" in options, host == "win32")
            self.assertIn((str(source / "assets/tCar.STL"), "tcarkit/assets"), analysis.call_args.kwargs["datas"])

    def test_tasks_share_actions_without_machine_specific_paths(self):
        tasks = json.loads((PROJECT / ".vscode/tasks.json").read_text())["tasks"]
        self.assertEqual({t["label"] for t in tasks}, {"Setup", "Play", "Build", "Install", "Clean", "Test"})
        for task in tasks:
            self.assertEqual(task["args"][1:], task["windows"]["args"])
            self.assertTrue(task["icon"]["id"])
            self.assertTrue(task["icon"]["tooltip"])
            self.assertNotIn("Administrator", str(task))


if __name__ == "__main__":
    unittest.main()
