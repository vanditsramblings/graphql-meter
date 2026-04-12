"""Vendor library manager — ensure Preact/HTM .mjs files are present."""

import urllib.request
from pathlib import Path

VENDOR_LIBS = {
    "preact.mjs": "https://unpkg.com/preact@10.24.3/dist/preact.mjs",
    "preact-hooks.mjs": "https://unpkg.com/preact@10.24.3/hooks/dist/hooks.mjs",
    "htm.mjs": "https://unpkg.com/htm@3.1.1/dist/htm.mjs",
}

VENDOR_FONTS = {
    "inter.woff2": "https://fonts.gstatic.com/s/inter/v20/UcC73FwrK3iLTeHuS_nVMrMxCp50SjIq15j8eUY.woff2",
    "jetbrains-mono.woff2": "https://fonts.gstatic.com/s/jetbrainsmono/v24/tDbv2o-flEEny0FZhsfKu5WU4zr3E_BX0PnT8RD8yKwBNntkaToggR7BYRbKDxLWxSsl.woff2",
}


def _find_frontend_dir() -> Path | None:
    """Locate the frontend directory (works in dev and installed mode)."""
    # Installed mode: frontend is bundled inside the backend package
    pkg_frontend = Path(__file__).parent / "frontend"
    if pkg_frontend.exists():
        return pkg_frontend
    # Development mode: frontend at repo root
    dev_frontend = Path(__file__).parent.parent / "frontend"
    if dev_frontend.exists():
        return dev_frontend
    return None


def ensure_vendor_libs() -> None:
    """Download vendored frontend libs and fonts if missing."""
    frontend_dir = _find_frontend_dir()
    if frontend_dir is None:
        return

    vendor_dir = frontend_dir / "vendor"
    vendor_dir.mkdir(parents=True, exist_ok=True)

    all_present = all((vendor_dir / name).exists() for name in VENDOR_LIBS)
    if not all_present:
        for name, url in VENDOR_LIBS.items():
            dest = vendor_dir / name
            if dest.exists():
                continue
            print(f"  Downloading {name}...")
            with urllib.request.urlopen(url) as resp:
                dest.write_bytes(resp.read())
        print("  Vendor libraries ready.")

    # Download fonts
    fonts_dir = vendor_dir / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)
    all_fonts = all((fonts_dir / name).exists() for name in VENDOR_FONTS)
    if not all_fonts:
        for name, url in VENDOR_FONTS.items():
            dest = fonts_dir / name
            if dest.exists():
                continue
            print(f"  Downloading font {name}...")
            with urllib.request.urlopen(url) as resp:
                dest.write_bytes(resp.read())
        print("  Vendor fonts ready.")
