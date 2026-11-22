#!/usr/bin/env python3
"""Cross-platform development, native packaging and per-user installation."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DEPENDENCIES = ("PyQt5", "OpenGL", "numpy", "psutil", "pyqtgraph", "PyInstaller")


def platform_name():
    if sys.platform == "win32":
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    raise RuntimeError("Supported build hosts: Linux and Windows")


def executable_name():
    return "tCarKit.exe" if platform_name() == "windows" else "tCarKit"


def run(command, **kwargs):
    print("[RUN] " + subprocess.list2cmdline([str(arg) for arg in command]), flush=True)
    return subprocess.run([str(arg) for arg in command], check=True, cwd=ROOT, **kwargs)


def conda_command():
    candidates = [os.environ.get("CONDA_EXE"), shutil.which("conda.exe"), shutil.which("conda")]
    # Also handles the common case of invoking Python directly inside a Conda
    # environment without activating it in the current terminal.
    for base in (Path(sys.prefix), Path(sys.prefix).parent.parent,
                 Path.home() / "miniconda3", Path.home() / "miniforge3",
                 Path.home() / "anaconda3"):
        candidates.extend((base / "Scripts" / "conda.exe", base / "bin" / "conda"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise RuntimeError("Conda was not found. Install Miniconda/Miniforge, or use --current-env with an existing Python environment.")


def ensure_environment(args):
    if args.current_env:
        return
    conda = conda_command()
    result = subprocess.run([conda, "env", "list", "--json"], check=True,
                            capture_output=True, text=True)
    environments = json.loads(result.stdout)["envs"]
    selected = next((Path(path) for path in environments if Path(path).name == "tcar"), None)
    if selected is None:
        raise RuntimeError("The 'tcar' environment is missing. Run the Setup task first.")
    if selected.resolve() != Path(sys.prefix).resolve():
        argv = list(sys.argv[1:])
        argv.append("--current-env")
        # Let Conda apply DLL/PATH settings, including Qt on Windows.
        run([conda, "run", "--no-capture-output", "-p", selected,
             "python", Path(__file__).resolve(), *argv])
        raise SystemExit(0)


def check_dependencies():
    missing = [name for name in DEPENDENCIES if importlib.util.find_spec(name) is None]
    if missing:
        raise RuntimeError("Missing dependencies: " + ", ".join(missing) + ". Run Setup or install requirement.txt in this environment.")


def setup_environment():
    conda = conda_command()
    result = subprocess.run([conda, "env", "list", "--json"], check=True,
                            capture_output=True, text=True)
    exists = any(Path(path).name == "tcar" for path in json.loads(result.stdout)["envs"])
    if exists:
        run([conda, "env", "update", "-n", "tcar", "-f", ROOT / "environment.yml"])
    else:
        run([conda, "env", "create", "-f", ROOT / "environment.yml"])
    print("[OK] Environment ready. Run Play or Build next.")


def atomic_copy(source, target, executable=False):
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".tcarkit-", suffix=target.suffix, dir=target.parent)
    os.close(fd)
    try:
        shutil.copyfile(source, temporary)
        if executable:
            os.chmod(temporary, 0o755)
        else:
            os.chmod(temporary, 0o644)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_text(target, text, executable=False):
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".tcarkit-", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.chmod(temporary, 0o755 if executable else 0o644)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def build(args):
    check_dependencies()
    build_root = ROOT / "build" / platform_name()
    build_root.mkdir(parents=True, exist_ok=True)
    # Keep the previous dist executable usable if packaging fails.
    with tempfile.TemporaryDirectory(prefix="staging-", dir=build_root) as staging:
        run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
             "--distpath", staging, "--workpath", build_root / "pyinstaller",
             ROOT / "src" / "tcarkit" / "tcarkit.spec"])
        source = Path(staging) / executable_name()
        if not source.is_file():
            raise RuntimeError("PyInstaller did not produce " + str(source))
        target = ROOT / "dist" / executable_name()
        atomic_copy(source, target, executable=True)
    print(f"[OK] Built {target} ({target.stat().st_size // 1024} KiB)")
    if args.install:
        install(args)


def desktop_entry(binary, icon):
    # Desktop Exec quoting is not shell quoting; escape percent field codes.
    path = str(binary).replace("\\", "\\\\\\\\").replace('"', '\\\\"')
    path = path.replace("`", "\\\\`").replace("$", "\\\\$").replace("%", "%%")
    return ("[Desktop Entry]\nVersion=1.0\nType=Application\nName=tCarKit\n"
            "Comment=tCar desktop controller\n"
            f'Exec="{path}"\nPath={binary.parent}\nIcon={icon}\n'
            "Terminal=false\nStartupNotify=false\nStartupWMClass=tCarKit\nCategories=Utility;\n")


def install(args):
    source = ROOT / "dist" / executable_name()
    if not source.is_file():
        raise RuntimeError("No native executable found. Run Build first.")
    if platform_name() == "linux":
        data = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
        target_dir = data / "tcarkit"
    else:
        target_dir = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "tCarKit"
    binary = target_dir / executable_name()
    icon = target_dir / "favicon.ico"
    atomic_copy(source, binary, executable=True)
    atomic_copy(ROOT / "src/tcarkit/assets/favicon.ico", icon)
    atomic_copy(ROOT / "src/tcarkit/metadata.json", target_dir / "metadata.json")
    if platform_name() == "linux":
        applications = data / "applications"
        entry = desktop_entry(binary, icon)
        atomic_text(applications / "tcarkit.desktop", entry)
        desktop = Path.home() / "Desktop"
        if shutil.which("xdg-user-dir"):
            result = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                desktop = Path(result.stdout.strip())
        if args.desktop or (desktop / "tcarkit.desktop").exists():
            shortcut = desktop / "tcarkit.desktop"
            atomic_text(shortcut, entry, executable=True)
            if shutil.which("gio"):
                subprocess.run(["gio", "set", str(shortcut), "metadata::trusted", "true"], check=False)
        if shutil.which("update-desktop-database"):
            subprocess.run(["update-desktop-database", str(applications)], check=True)
    else:
        # Pass paths in environment variables, never interpolate them as
        # PowerShell code. WScript writes standard Start Menu/Desktop links.
        environment = dict(os.environ, TCARKIT_EXE=str(binary), TCARKIT_ICON=str(icon),
                           TCARKIT_DESKTOP="1" if args.desktop else "0")
        script = """
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
$menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'tCarKit.lnk'
$links = @($menu)
$desktop = Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) 'tCarKit.lnk'
if ($env:TCARKIT_DESKTOP -eq '1' -or (Test-Path $desktop)) { $links += $desktop }
foreach ($path in $links) {
    $link = $shell.CreateShortcut($path)
    $link.TargetPath = $env:TCARKIT_EXE
    $link.WorkingDirectory = Split-Path $env:TCARKIT_EXE
    $link.IconLocation = $env:TCARKIT_ICON
    $link.Save()
}
"""
        run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "-"],
            input=script, text=True, env=environment)
    print(f"[OK] Installed at {binary}; application launcher updated.")


def clean(args):
    targets = [ROOT / "build"]
    if args.all:
        targets.append(ROOT / "dist")
    for parent in (ROOT / "src", ROOT / "scripts", ROOT / "tests"):
        if parent.is_dir():
            targets.extend(parent.rglob("__pycache__"))
            targets.extend(parent.rglob("*.pyc"))
    for target in sorted(set(targets), key=lambda path: len(path.parts), reverse=True):
        if target.is_symlink():
            raise RuntimeError(f"Refusing to clean a symlink: {target}")
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    print("[OK] Build cache cleaned." + (" dist removed." if args.all else " dist and installed app preserved."))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("setup", "run", "build", "install", "clean", "test", "doctor"):
        action = sub.add_parser(name)
        action.add_argument("--current-env", action="store_true",
                            help="use this Python environment instead of selecting Conda tcar")
        if name in ("build", "install"):
            action.add_argument("--desktop", action="store_true", help="also create a desktop shortcut")
        if name == "build":
            action.add_argument("--install", action="store_true", help="install after successful build")
        if name == "clean":
            action.add_argument("--all", action="store_true", help="also remove dist; installed app stays intact")
    args = parser.parse_args()
    platform_name()
    if args.action == "setup":
        setup_environment()
    elif args.action == "clean":
        clean(args)
    elif args.action == "install":
        install(args)
    else:
        ensure_environment(args)
        check_dependencies()
        if args.action == "build":
            build(args)
        elif args.action == "doctor":
            print(f"[OK] {platform_name()} / Python {sys.version.split()[0]} / {sys.executable}")
            print(f"[OK] Project: {ROOT}; native output: dist/{executable_name()}")
        elif args.action == "test":
            run([sys.executable, "-m", "unittest", "discover", "-s", ROOT / "tests", "-v"])
        else:
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + environment.get("PYTHONPATH", "")
            run([sys.executable, "-m", "tcarkit.app"], env=environment)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        raise SystemExit(1)
