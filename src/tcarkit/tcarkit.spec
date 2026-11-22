# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import json
import sys

from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH)
source_root = root.parent
windows_options = {}
if sys.platform == "win32":
    from PyInstaller.utils.win32.versioninfo import (
        VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable,
        StringStruct, VarFileInfo, VarStruct,
    )
    metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    version = metadata["version"]
    numbers = tuple(int(part) for part in version.split("."))
    numbers = (numbers + (0, 0, 0, 0))[:4]
    windows_options = {
        "icon": str(root / "assets" / "favicon.ico"),
        "version": VSVersionInfo(
            ffi=FixedFileInfo(filevers=numbers, prodvers=numbers, mask=0x3f,
                              flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
            kids=[StringFileInfo([StringTable("040904B0", [
                StringStruct("CompanyName", metadata["developer"]),
                StringStruct("FileDescription", "tCarKit"),
                StringStruct("FileVersion", version),
                StringStruct("InternalName", "tCarKit"),
                StringStruct("OriginalFilename", "tCarKit.exe"),
                StringStruct("ProductName", "tCarKit"),
                StringStruct("ProductVersion", version),
            ])]), VarFileInfo([VarStruct("Translation", [1033, 1200])])],
        ),
    }

a = Analysis(
    [str(root / "app.py")],
    pathex=[str(source_root)],
    binaries=[],
    datas=[
        (str(root / "assets" / "favicon.ico"), "tcarkit/assets"),
        (str(root / "assets" / "tCar.STL"), "tcarkit/assets"),
        (str(root / "metadata.json"), "tcarkit"),
    ],
    hiddenimports=[
        "PyQt5", "PyQt5.QtOpenGL", "OpenGL", "pyqtgraph",
        # PyOpenGL selects its display backend at runtime, so PyInstaller cannot
        # see these imports. Without them the frozen app logs
        # "Unable to import OpenGL.platform.egl.EGLPlatform".
        *collect_submodules("OpenGL.platform"),
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="tCarKit",
    console=False,
    **windows_options,
)
