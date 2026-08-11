"""Portable, repository-confined references for evaluation artifacts."""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_LEGACY_FLAGSHIP_MARKER = ("chemworld", "runs", "flagship-mechanism-diagnostics")


def repository_relative_reference(
    path: str | Path, *, repository_root: Path = REPOSITORY_ROOT
) -> str:
    """Serialize a repository artifact without retaining an author-machine root."""

    root = repository_root.resolve()
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError as error:
        raise ValueError(f"artifact is outside repository root: {path}") from error


def resolve_flagship_trajectory_reference(
    reference: str | Path, *, repository_root: Path = REPOSITORY_ROOT
) -> Path:
    """Resolve current relative paths and the frozen v0.1 Windows-path contract.

    The historical v0.1 report is immutable and contains paths rooted at an author
    checkout.  Only the recognized ``ChemWorld/runs/flagship-mechanism-diagnostics``
    suffix may be rebound.  Other external absolute paths are rejected.
    """

    text = str(reference).strip()
    if not text:
        raise ValueError("trajectory reference cannot be empty")
    root = repository_root.resolve()
    native = Path(text)
    windows = PureWindowsPath(text)
    posix = PurePosixPath(text)
    is_absolute = native.is_absolute() or windows.is_absolute() or posix.is_absolute()

    if not is_absolute:
        return _confined(root / native, root=root, reference=text)

    if native.is_absolute():
        resolved_native = native.resolve()
        if resolved_native.is_relative_to(root):
            return resolved_native

    pure_parts = windows.parts if windows.is_absolute() else posix.parts
    folded = tuple(part.casefold() for part in pure_parts)
    marker_index = _subsequence_index(folded, _LEGACY_FLAGSHIP_MARKER)
    if marker_index is None:
        raise ValueError(f"unrecognized external trajectory reference: {text}")
    runs_index = marker_index + 1
    rebound = root.joinpath(*pure_parts[runs_index:])
    return _confined(rebound, root=root, reference=text)


def _confined(path: Path, *, root: Path, reference: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"trajectory reference escapes repository root: {reference}")
    return resolved


def _subsequence_index(
    values: tuple[str, ...], marker: tuple[str, ...]
) -> int | None:
    width = len(marker)
    return next(
        (
            index
            for index in range(len(values) - width + 1)
            if values[index : index + width] == marker
        ),
        None,
    )


__all__ = [
    "REPOSITORY_ROOT",
    "repository_relative_reference",
    "resolve_flagship_trajectory_reference",
]
