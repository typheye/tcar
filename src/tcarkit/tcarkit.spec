from pathlib import Path

root = Path(SPECPATH)
source_root = root.parent

a = Analysis(
    [str(root / "app.py")],
    pathex=[str(source_root)],
    binaries=[],
    datas=[(str(root / "assets" / "favicon.ico"), "tcarkit/assets")],
    hiddenimports=["PyQt5", "PyQt5.QtOpenGL", "OpenGL", "pyqtgraph"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="tCarKit",
    console=False,
    icon=str(root / "assets" / "favicon.ico"),
    version=str(root / "version_info.txt"),
)
