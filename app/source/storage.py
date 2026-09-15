"""Where a downloaded attachment lands on disk — one rule, both sources.

`<attachments>/<run_id>/<scenario_id>/<device_id><extension>`

The file is named the way VisiumGo's UI names it (`browser.default.html`,
`test.properties`) rather than with the API's uniqueness number, and the
scenario folder is what keeps those names apart: every scenario of a run
produces its own `browser.default.html`.

Every downloaded attachment goes through here, so "did it actually land on
disk?" has one answer and one naming rule.
"""

from pathlib import Path

from app.source.models import Attachment


def safe_path_part(value: str) -> str:
    """Make an id/file name safe to use as a single filesystem path segment."""
    return value.replace("/", "_").replace(":", "_").replace("\\", "_")


def save_attachment(
    root: Path, run_id: str, scenario_id: str, attachment: Attachment, data: bytes
) -> Path:
    """Write one attachment and return where it landed.

    Same device + extension twice in one scenario has not been observed; if it
    ever happens, both are kept (`-2`, `-3`, …) instead of one silently
    overwriting the other.
    """
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
    """Write the job-level build log and return where it landed.

    `<build_logs>/<run_id>.log` — one file per RUN, not per scenario, because
    that is what the log is: the whole run's output. It lives apart from
    `attachments/` for the same reason it has its own report field — it never
    came from a scenario's `attachments[]`.

    Kept on disk instead of inline in the run row: a job log is large, and a
    run row is read for status.
    """
    root.mkdir(parents=True, exist_ok=True)
    dest = root / f"{safe_path_part(run_id)}.log"
    dest.write_text(text, encoding="utf-8")
    return dest


__all__ = ["safe_path_part", "save_attachment", "save_build_log"]
