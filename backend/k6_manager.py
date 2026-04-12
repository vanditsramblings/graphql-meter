"""k6 binary dependency manager — detect or auto-download k6."""

import hashlib
import os
import platform
import shutil
import stat
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

import requests

K6_VERSION = "v0.54.0"

# SHA-256 checksums for official k6 release archives.
# Update these when bumping K6_VERSION.
K6_CHECKSUMS: dict[str, str] = {
    # Populated on first release pin — leave empty to skip verification.
}

_DOWNLOAD_BASE = f"https://github.com/grafana/k6/releases/download/{K6_VERSION}"


def _platform_key() -> tuple[str, str]:
    """Return (os_name, arch) matching k6 release naming."""
    raw_os = platform.system().lower()
    machine = platform.machine().lower()

    if raw_os == "darwin":
        os_name = "macos"
    elif raw_os == "windows":
        os_name = "windows"
    else:
        os_name = "linux"

    if machine in ("x86_64", "amd64"):
        arch = "amd64"
    elif machine in ("aarch64", "arm64"):
        arch = "arm64"
    else:
        arch = machine

    return os_name, arch


def _download_url() -> str:
    os_name, arch = _platform_key()
    if os_name in ("macos", "windows"):
        return f"{_DOWNLOAD_BASE}/k6-{K6_VERSION}-{os_name}-{arch}.zip"
    return f"{_DOWNLOAD_BASE}/k6-{K6_VERSION}-{os_name}-{arch}.tar.gz"


def _verify_checksum(filepath: Path) -> bool:
    """Verify SHA-256 checksum if available."""
    key = filepath.name
    expected = K6_CHECKSUMS.get(key)
    if not expected:
        return True  # no checksum to verify

    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest() == expected


def find_k6() -> str | None:
    """Find k6 binary in common locations. Returns path or None."""
    from backend.config import get_settings

    settings = get_settings()

    # 1. Explicit config
    if settings.K6_BINARY_PATH and Path(settings.K6_BINARY_PATH).exists():
        return settings.K6_BINARY_PATH

    # 2. Inside the active virtual-env
    if sys.prefix != sys.base_prefix:
        suffix = ".exe" if platform.system() == "Windows" else ""
        venv_k6 = Path(sys.prefix) / "bin" / f"k6{suffix}"
        if venv_k6.exists():
            return str(venv_k6)

    # 3. System PATH
    return shutil.which("k6")


def _default_install_dir() -> Path:
    """Pick a target directory for the downloaded k6 binary."""
    # Prefer virtualenv bin if active
    if sys.prefix != sys.base_prefix:
        return Path(sys.prefix) / "bin"
    # Fall back to ~/.local/bin
    local_bin = Path.home() / ".local" / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)
    return local_bin


def download_k6(target_dir: Path | None = None) -> str:
    """Download the k6 binary for the current platform. Returns path to binary."""
    if target_dir is None:
        target_dir = _default_install_dir()

    url = _download_url()
    os_name, arch = _platform_key()
    is_zip = url.endswith(".zip")

    print(f"  Downloading k6 {K6_VERSION} for {os_name}/{arch}...")

    with tempfile.TemporaryDirectory() as tmpdir:
        archive_path = Path(tmpdir) / ("k6.zip" if is_zip else "k6.tar.gz")

        # Stream download
        resp = requests.get(url, stream=True, timeout=120)
        resp.raise_for_status()
        with open(archive_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        # Verify checksum
        if not _verify_checksum(archive_path):
            raise RuntimeError(f"SHA-256 checksum mismatch for {archive_path.name}")

        # Extract
        binary_name = "k6.exe" if os_name == "windows" else "k6"
        extract_dir = Path(tmpdir) / "extract"
        extract_dir.mkdir()

        if is_zip:
            with zipfile.ZipFile(archive_path) as zf:
                zf.extractall(extract_dir)
        else:
            with tarfile.open(archive_path, "r:gz") as tf:
                tf.extractall(extract_dir)

        # Find the k6 binary inside extracted directory
        found = None
        for p in extract_dir.rglob(binary_name):
            found = p
            break

        if not found:
            raise RuntimeError(f"Could not find {binary_name} in downloaded archive")

        dest = target_dir / binary_name
        shutil.copy2(found, dest)
        dest.chmod(dest.stat().st_mode | stat.S_IEXEC)

    print(f"  k6 installed at {dest}")
    return str(dest)


def ensure_k6() -> str:
    """Ensure k6 is available, downloading if necessary. Returns path to binary."""
    path = find_k6()
    if path:
        return path
    return download_k6()
