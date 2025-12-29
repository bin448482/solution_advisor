import base64
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Iterable


class CommandError(RuntimeError):
    """Raised when a subprocess call fails."""


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def compute_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def save_json(data: Any, path: Path) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def run_command(cmd: Iterable[str], cwd: Path | None = None, timeout: int = 600) -> None:
    result = subprocess.run(
        list(cmd),
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise CommandError(f"Command failed: {' '.join(cmd)}\nstdout: {result.stdout}\nstderr: {result.stderr}")


def encode_image_to_data_url(image_path: Path) -> str:
    mime = "image/png"
    if image_path.suffix.lower() in {".jpg", ".jpeg"}:
        mime = "image/jpeg"
    data = image_path.read_bytes()
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def command_exists(executable: str) -> bool:
    return shutil.which(executable) is not None
