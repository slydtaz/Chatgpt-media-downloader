"""Create a clean ZIP and SHA-256 file for this library."""
from __future__ import annotations
import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
ZIP_PATH = DIST / "reusable-neon-ui-0.1.0.zip"
SKIP = {"__pycache__", ".pytest_cache", ".git", ".venv", "venv", "dist"}

def main():
    DIST.mkdir(parents=True, exist_ok=True)
    with ZipFile(ZIP_PATH, "w", ZIP_DEFLATED, compresslevel=8) as archive:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file() or any(part in SKIP for part in path.parts):
                continue
            if path.suffix.lower() in {".pyc", ".pyo", ".pfx", ".p12", ".pem", ".key"}:
                continue
            if path.name.lower() in {".env", "credentials.json", "secrets.json"}:
                continue
            archive.write(path, Path("reusable-neon-ui") / path.relative_to(ROOT))
    digest = hashlib.sha256(ZIP_PATH.read_bytes()).hexdigest()
    (DIST / "SHA256SUMS.txt").write_text(
        f"{digest}  {ZIP_PATH.name}\n", encoding="utf-8"
    )
    print(f"ZIP: {ZIP_PATH}")
    print(f"SHA256: {digest}")

if __name__ == "__main__":
    main()
