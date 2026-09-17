"""Where a downloaded attachment lands on disk."""

from pathlib import Path

from app.source.models import Attachment


def safe_path_part(value: str) -> str:
    """Make an id/file name safe to use as a single filesystem path segment."""
    return value.replace("/", "_").replace(":", "_").replace("\\", "_")


def save_attachment(
    root: Path, run_id: str, scenario_id: str, attachment: Attachment, data: bytes
) -> Path:
    """Write one attachment and return where it landed."""
    folder = root / safe_path_part(run_id)
    if scenario_id:
        folder = folder / safe_path_part(scenario_id)
    folder.mkdir(parents=True, exist_ok=True)

    name = safe_path_part(attachment.label) or safe_path_part(attachment.file_name)
    dest = folder / name
    stem, suffix = dest.stem, dest.suffix
    index = 2
    while dest.exists():
        dest = folder / f"{stem}-{index}{suffix}"
        index += 1

    dest.write_bytes(data)
    return dest


def save_build_log(root: Path, run_id: str, text: str) -> Path:
    """Write the job-level build log and return where it landed."""
    root.mkdir(parents=True, exist_ok=True)
    dest = root / f"{safe_path_part(run_id)}.log"
    dest.write_text(text, encoding="utf-8")
    return dest


__all__ = ["safe_path_part", "save_attachment", "save_build_log"]
