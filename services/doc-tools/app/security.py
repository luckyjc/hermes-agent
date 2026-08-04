from pathlib import Path

from config import Settings


class SecurityError(ValueError):
    pass


class FileTooLargeError(ValueError):
    pass


def validate_source_path(path_str: str, settings: Settings) -> Path:
    candidate = Path(path_str).expanduser().resolve()

    if not candidate.exists():
        raise FileNotFoundError(f"Source does not exist: {candidate}")

    if not candidate.is_file():
        raise SecurityError(f"Source is not a file: {candidate}")

    if not any(candidate.is_relative_to(root) for root in settings.allowed_roots):
        raise SecurityError("Path is outside approved roots")

    max_bytes = settings.doc_tools_max_file_mb * 1024 * 1024
    if candidate.stat().st_size > max_bytes:
        raise FileTooLargeError(
            f"File exceeds max size of {settings.doc_tools_max_file_mb} MB"
        )

    return candidate
