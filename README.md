# tCarKit

PyQt5 desktop monitor migrated from the JanPNP `win-pc` shell. Home embeds the
TurboPi attitude 3D scene, UDP telemetry, and the MJPEG camera preview. The
only additional tab is PC Info; the File menu contains navigation, theme, and
exit actions.

Run from this directory:

```powershell
$env:PYTHONPATH="$PWD/src"
python -m tcarkit.app
```

The source package follows the JanPNP layout under `src/tcarkit`.
