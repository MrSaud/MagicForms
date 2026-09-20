#!/usr/bin/env python3
"""Export SForms app icons from brand SVGs for iOS and Android."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICON_SVG = ROOT / "brand" / "sforms-app-icon.svg"
FOREGROUND_SVG = ROOT / "brand" / "sforms-app-icon-foreground.svg"


def ensure_cairosvg():
    try:
        import cairosvg  # noqa: F401
    except ImportError:
        venv = ROOT / ".venv-icon-export"
        if not venv.exists():
            subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
        pip = venv / "bin" / "pip"
        subprocess.check_call([str(pip), "install", "-q", "cairosvg"])
        return str(venv / "bin" / "python")
    return sys.executable


def export_icons() -> None:
    import cairosvg

    ios = ROOT / "ios/MagicFormsMobile/Resources/Assets.xcassets/AppIcon.appiconset/AppIcon.png"
    ios.parent.mkdir(parents=True, exist_ok=True)
    cairosvg.svg2png(url=str(ICON_SVG), write_to=str(ios), output_width=1024, output_height=1024)

    fg = ROOT / "android/app/src/main/res/drawable-nodpi/ic_launcher_foreground_img.png"
    fg.parent.mkdir(parents=True, exist_ok=True)
    cairosvg.svg2png(url=str(FOREGROUND_SVG), write_to=str(fg), output_width=432, output_height=432)

    for folder, size in {
        "mipmap-mdpi": 48,
        "mipmap-hdpi": 72,
        "mipmap-xhdpi": 96,
        "mipmap-xxhdpi": 144,
        "mipmap-xxxhdpi": 192,
    }.items():
        d = ROOT / "android/app/src/main/res" / folder
        d.mkdir(parents=True, exist_ok=True)
        for name in ("ic_launcher.png", "ic_launcher_round.png"):
            cairosvg.svg2png(
                url=str(ICON_SVG),
                write_to=str(d / name),
                output_width=size,
                output_height=size,
            )


def main() -> None:
    if not ICON_SVG.is_file():
        raise SystemExit(f"Missing {ICON_SVG}")
    if not FOREGROUND_SVG.is_file():
        raise SystemExit(f"Missing {FOREGROUND_SVG}")
    py = ensure_cairosvg()
    if py != sys.executable:
        subprocess.check_call([py, str(Path(__file__).resolve())])
        return
    export_icons()
    print("Exported iOS AppIcon, Android mipmaps, and adaptive foreground.")


if __name__ == "__main__":
    main()
