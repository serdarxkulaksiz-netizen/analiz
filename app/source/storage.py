"""Where a downloaded attachment lands on disk — one rule, both sources.

`<attachments>/<run_id>/<scenario_id>/<device_id><extension>`

The file is named the way VisiumGo's UI names it (`browser.default.html`,
`test.properties`) rather than with the API's uniqueness number, and the
scenario folder is what keeps those names apart: every scenario of a run
produces its own `browser.default.html`.

MockSource writes here too. A mock that only pretends to save files would leave
the "did it actually land on disk?" question untestable on the machine where
all development happens.
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


__all__ = ["safe_path_part", "save_attachment"]
