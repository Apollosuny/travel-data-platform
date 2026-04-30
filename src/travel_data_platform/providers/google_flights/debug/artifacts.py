from datetime import UTC, datetime
from pathlib import Path
import json


def write_debug_artifact(name: str, content: str, suffix: str = "txt") -> str:
    debug_dir = Path("debug/google_flights")
    debug_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = debug_dir / f"{timestamp}_{name}.{suffix}"
    path.write_text(content, encoding="utf-8")
    return str(path)


def write_debug_bytes(name: str, content: bytes, suffix: str) -> str:
    debug_dir = Path("debug/google_flights")
    debug_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = debug_dir / f"{timestamp}_{name}.{suffix}"
    path.write_bytes(content)
    return str(path)


def write_debug_json(name: str, data: object) -> str:
    debug_dir = Path("debug/google_flights")
    debug_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = debug_dir / f"{timestamp}_{name}.json"
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return str(path)