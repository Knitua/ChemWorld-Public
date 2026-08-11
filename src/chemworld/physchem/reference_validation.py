"""Optional reference-backend validation helpers.

The helpers in this module deliberately keep external scientific packages out
of ChemWorld's runtime dependency graph. They provide a small, auditable way to
discover local reference repositories, temporarily import reference packages
when a developer opts in, and record scalar comparison results with explicit
tolerances.
"""

from __future__ import annotations

import importlib
import importlib.metadata as importlib_metadata
import importlib.util
import json
import sys
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType


@dataclass(frozen=True)
class ReferenceBackendSpec:
    """A lightweight description of an optional external reference backend."""

    backend_id: str
    package_name: str
    local_repo_names: tuple[str, ...]
    comparison_scope: tuple[str, ...]
    model_limit_notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "backend_id": self.backend_id,
            "package_name": self.package_name,
            "local_repo_names": list(self.local_repo_names),
            "comparison_scope": list(self.comparison_scope),
            "model_limit_notes": list(self.model_limit_notes),
        }


@dataclass(frozen=True)
class ReferenceBackendStatus:
    """JSON-friendly availability report for a reference backend."""

    backend_id: str
    package_name: str
    installed_available: bool
    local_repo_available: bool
    import_probe_attempted: bool
    import_available: bool | None
    source: str | None = None
    installed_version: str | None = None
    local_repo_paths: tuple[str, ...] = ()
    local_repo_commits: dict[str, str] = field(default_factory=dict)
    import_error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "backend_id": self.backend_id,
            "package_name": self.package_name,
            "installed_available": self.installed_available,
            "local_repo_available": self.local_repo_available,
            "import_probe_attempted": self.import_probe_attempted,
            "import_available": self.import_available,
            "source": self.source,
            "installed_version": self.installed_version,
            "local_repo_paths": list(self.local_repo_paths),
            "local_repo_commits": dict(self.local_repo_commits),
            "import_error": self.import_error,
        }


@dataclass(frozen=True)
class ReferenceComparison:
    """A scalar comparison between ChemWorld and an optional reference backend."""

    check_id: str
    backend_id: str
    quantity: str
    chemworld_value: float
    reference_value: float
    unit: str
    rtol: float
    atol: float
    abs_error: float
    rel_error: float | None
    passed: bool
    note: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "check_id": self.check_id,
            "backend_id": self.backend_id,
            "quantity": self.quantity,
            "chemworld_value": self.chemworld_value,
            "reference_value": self.reference_value,
            "unit": self.unit,
            "rtol": self.rtol,
            "atol": self.atol,
            "abs_error": self.abs_error,
            "rel_error": self.rel_error,
            "passed": self.passed,
            "note": self.note,
        }


@dataclass(frozen=True)
class ReferenceValidationReport:
    """JSON-friendly summary for optional reference-backend validation runs."""

    schema_version: str
    comparison_summary: dict[str, object]
    backend_statuses: tuple[ReferenceBackendStatus, ...]
    skipped_backends: tuple[dict[str, object], ...]
    tolerance_profiles: tuple[ReferenceToleranceProfile, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "comparison_summary": self.comparison_summary,
            "backend_statuses": [status.to_dict() for status in self.backend_statuses],
            "skipped_backends": [dict(item) for item in self.skipped_backends],
            "tolerance_profiles": [
                profile.to_dict() for profile in self.tolerance_profiles
            ],
        }


@dataclass(frozen=True)
class ReferenceToleranceProfile:
    """Declared tolerance intent for one optional reference comparison family."""

    profile_id: str
    backend_id: str
    quantity: str
    rtol: float
    atol: float = 0.0
    unit: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        for field_name in ("profile_id", "backend_id", "quantity"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} cannot be empty")
        if self.rtol < 0 or self.atol < 0:
            raise ValueError("rtol and atol must be nonnegative")

    def to_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "backend_id": self.backend_id,
            "quantity": self.quantity,
            "rtol": self.rtol,
            "atol": self.atol,
            "unit": self.unit,
            "note": self.note,
        }


_REFERENCE_BACKENDS: tuple[ReferenceBackendSpec, ...] = (
    ReferenceBackendSpec(
        backend_id="chemicals",
        package_name="chemicals",
        local_repo_names=("fluids", "chemicals"),
        comparison_scope=(
            "formula-level property correlations",
            "ideal-gas molar volume",
            "Rachford-Rice flash inner loop",
        ),
        model_limit_notes=(
            "ChemWorld keeps a compact benchmark subset rather than the full "
            "chemicals property database.",
        ),
    ),
    ReferenceBackendSpec(
        backend_id="fluids",
        package_name="fluids",
        local_repo_names=("fluids",),
        comparison_scope=(
            "dimensionless numbers",
            "Darcy friction factors",
            "single-phase pressure-drop utilities",
        ),
    ),
    ReferenceBackendSpec(
        backend_id="thermo",
        package_name="thermo",
        local_repo_names=("fluids", "chemicals", "thermo"),
        comparison_scope=("property-package organization", "EOS and flash workflows"),
    ),
    ReferenceBackendSpec(
        backend_id="coolprop",
        package_name="CoolProp",
        local_repo_names=("coolprop",),
        comparison_scope=("high-accuracy pure-fluid property points",),
        model_limit_notes=(
            "A source checkout may not expose an importable Python package until "
            "its compiled extension is built.",
        ),
    ),
    ReferenceBackendSpec(
        backend_id="cantera",
        package_name="cantera",
        local_repo_names=("cantera",),
        comparison_scope=("simple reaction ODE and mechanism loading checks",),
        model_limit_notes=("Cantera normally requires compiled extensions.",),
    ),
    ReferenceBackendSpec(
        backend_id="phasepy",
        package_name="phasepy",
        local_repo_names=("phasepy",),
        comparison_scope=("VLE/LLE activity-model workflows",),
        model_limit_notes=("Local source imports may require compiled activity-model modules.",),
    ),
    ReferenceBackendSpec(
        backend_id="reaktoro",
        package_name="reaktoro",
        local_repo_names=("reaktoro",),
        comparison_scope=("equilibrium toy problems",),
        model_limit_notes=("Reaktoro is a compiled backend and may be unavailable locally.",),
    ),
    ReferenceBackendSpec(
        backend_id="pycalphad",
        package_name="pycalphad",
        local_repo_names=("pycalphad",),
        comparison_scope=("solid-phase and Gibbs-energy toy cases",),
        model_limit_notes=("pycalphad source imports require optional symbolic dependencies.",),
    ),
    ReferenceBackendSpec(
        backend_id="idaes-pse",
        package_name="idaes",
        local_repo_names=("idaes-pse",),
        comparison_scope=(
            "process unit contracts",
            "material and energy port organization",
            "flowsheet initialization patterns",
        ),
        model_limit_notes=(
            "IDAES is used as a design reference, not a required runtime backend.",
        ),
    ),
    ReferenceBackendSpec(
        backend_id="teqp",
        package_name="teqp",
        local_repo_names=("teqp",),
        comparison_scope=("EOS architecture", "phase-envelope workflow patterns"),
        model_limit_notes=("teqp may require compiled extensions before imports succeed.",),
    ),
    ReferenceBackendSpec(
        backend_id="thermopack",
        package_name="thermopack",
        local_repo_names=("thermopack",),
        comparison_scope=("EOS architecture", "mixture and phase-envelope workflows"),
        model_limit_notes=("thermopack usually requires compiled shared libraries.",),
    ),
    ReferenceBackendSpec(
        backend_id="rmg-py",
        package_name="rmgpy",
        local_repo_names=("rmg-py",),
        comparison_scope=(
            "mechanism schema conventions",
            "Arrhenius and falloff rate-law taxonomy",
            "thermochemistry data organization",
        ),
        model_limit_notes=("RMG-Py has a large optional dependency surface.",),
    ),
)

_REFERENCE_TOLERANCE_PROFILES: tuple[ReferenceToleranceProfile, ...] = (
    ReferenceToleranceProfile(
        profile_id="chemicals-curated-properties-tight",
        backend_id="chemicals",
        quantity="curated vapor pressure, ideal-gas Cp, and enthalpy",
        rtol=1e-12,
        unit="declared property units",
        note="Exact equation/regression comparison against mirrored public correlations.",
    ),
    ReferenceToleranceProfile(
        profile_id="fluids-pressure-drop-tight",
        backend_id="fluids",
        quantity="Haaland friction factor and Darcy-Weisbach pressure drop",
        rtol=1e-12,
        unit="dimensionless or Pa",
        note="Same analytical branch selected on both sides.",
    ),
    ReferenceToleranceProfile(
        profile_id="thermo-activity-and-flash-reference",
        backend_id="thermo",
        quantity="activity coefficients and ideal flash",
        rtol=1e-8,
        atol=1e-10,
        unit="mixed",
        note="Allows small backend/version differences in nonlinear thermo routines.",
    ),
    ReferenceToleranceProfile(
        profile_id="thermo-cubic-eos-residual-reference",
        backend_id="thermo",
        quantity="cubic EOS Z, fugacity, residual enthalpy, and residual entropy",
        rtol=5e-5,
        atol=1e-8,
        unit="mixed",
        note=(
            "Independent PR/SRK implementations differ slightly in alpha, "
            "departure-property, and constant conventions across thermo versions."
        ),
    ),
    ReferenceToleranceProfile(
        profile_id="coolprop-pure-fluid-regression",
        backend_id="coolprop",
        quantity="pure-fluid saturation, density, and enthalpy points",
        rtol=1e-6,
        atol=1e-8,
        unit="mixed",
        note="Reserved for compiled CoolProp comparisons near documented validity regions.",
    ),
    ReferenceToleranceProfile(
        profile_id="cantera-rmg-kinetics-regression",
        backend_id="cantera",
        quantity="Arrhenius, reversible kinetics, and thermochemistry-linked rates",
        rtol=1e-8,
        atol=1e-12,
        unit="SI rate units",
        note="Used only for explicitly opt-in kinetic reference comparisons.",
    ),
    ReferenceToleranceProfile(
        profile_id="equilibrium-compiled-backend-regression",
        backend_id="reaktoro",
        quantity="small aqueous or Gibbs-minimization equilibrium examples",
        rtol=1e-7,
        atol=1e-10,
        unit="mixed",
        note="Reserved for compiled equilibrium backends with explicit model-limit notes.",
    ),
)


def reference_backend_specs() -> tuple[ReferenceBackendSpec, ...]:
    """Return the optional reference backends tracked by ChemWorld."""

    return _REFERENCE_BACKENDS


def reference_tolerance_profiles() -> tuple[ReferenceToleranceProfile, ...]:
    """Return declared tolerances for optional reference validation families."""

    return _REFERENCE_TOLERANCE_PROFILES


def repository_root() -> Path:
    """Return the repository root from this source file location."""

    return Path(__file__).resolve().parents[3]


def reference_repos_root(reference_root: str | Path | None = None) -> Path:
    """Return the expected local reference repository directory."""

    if reference_root is not None:
        return Path(reference_root)
    return repository_root() / "reference_repos"


def reference_repo_paths(
    repo_names: Iterable[str] | None = None,
    *,
    reference_root: str | Path | None = None,
) -> tuple[Path, ...]:
    """Return existing local source paths for reference repositories."""

    root = reference_repos_root(reference_root)
    names = tuple(repo_names) if repo_names is not None else _all_local_repo_names()
    paths: list[Path] = []
    for name in names:
        paths.extend(_python_path_candidates(root, name))
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path.resolve())
        if key not in seen:
            deduped.append(path)
            seen.add(key)
    return tuple(deduped)


def reference_repo_roots(
    repo_names: Iterable[str] | None = None,
    *,
    reference_root: str | Path | None = None,
) -> tuple[Path, ...]:
    """Return existing top-level local reference repository roots."""

    root = reference_repos_root(reference_root)
    names = tuple(repo_names) if repo_names is not None else _all_local_repo_names()
    roots: list[Path] = []
    seen: set[str] = set()
    for name in names:
        path = root / name
        if not path.exists():
            continue
        key = str(path.resolve())
        if key not in seen:
            roots.append(path)
            seen.add(key)
    return tuple(roots)


@contextmanager
def reference_backend_context(
    repo_names: Iterable[str] | None = None,
    *,
    reference_root: str | Path | None = None,
) -> Iterator[tuple[Path, ...]]:
    """Temporarily add local reference repositories to `sys.path`."""

    paths = reference_repo_paths(repo_names, reference_root=reference_root)
    original = list(sys.path)
    try:
        for path in reversed(paths):
            path_string = str(path)
            if path_string not in sys.path:
                sys.path.insert(0, path_string)
        yield paths
    finally:
        sys.path[:] = original


def import_reference_module(
    module_name: str,
    *,
    repo_names: Iterable[str] | None = None,
    reference_root: str | Path | None = None,
) -> ModuleType:
    """Import an optional reference module from installed or local sources."""

    with reference_backend_context(repo_names, reference_root=reference_root):
        return importlib.import_module(module_name)


def reference_backend_status(
    *,
    reference_root: str | Path | None = None,
    probe_import: bool = False,
) -> tuple[ReferenceBackendStatus, ...]:
    """Return availability reports for all tracked reference backends.

    `probe_import=False` keeps this function side-effect-light: it only checks
    whether a module spec exists. Set `probe_import=True` in manual validation
    runs to record actual import errors.
    """

    statuses: list[ReferenceBackendStatus] = []
    for spec in _REFERENCE_BACKENDS:
        installed_available = importlib.util.find_spec(spec.package_name) is not None
        installed_version = (
            _installed_package_version(spec.package_name)
            if installed_available
            else None
        )
        local_repo_roots = reference_repo_roots(
            spec.local_repo_names,
            reference_root=reference_root,
        )
        local_repo_available = bool(local_repo_roots)
        local_repo_paths = tuple(str(path) for path in local_repo_roots)
        local_repo_commits = {
            path.name: commit
            for path in local_repo_roots
            if (commit := _git_short_commit(path)) is not None
        }
        import_available: bool | None = None
        source: str | None = None
        import_error: str | None = None
        if probe_import:
            try:
                module = import_reference_module(
                    spec.package_name,
                    repo_names=spec.local_repo_names,
                    reference_root=reference_root,
                )
                import_available = True
                module_file = getattr(module, "__file__", None)
                source = str(module_file) if module_file is not None else None
            except Exception as exc:  # pragma: no cover - depends on local extras
                import_available = False
                import_error = f"{type(exc).__name__}: {exc}"
        elif installed_available or local_repo_available:
            with reference_backend_context(spec.local_repo_names, reference_root=reference_root):
                found = importlib.util.find_spec(spec.package_name)
            source = found.origin if found is not None else None
        statuses.append(
            ReferenceBackendStatus(
                backend_id=spec.backend_id,
                package_name=spec.package_name,
                installed_available=installed_available,
                local_repo_available=local_repo_available,
                import_probe_attempted=probe_import,
                import_available=import_available,
                source=source,
                installed_version=installed_version,
                local_repo_paths=local_repo_paths,
                local_repo_commits=local_repo_commits,
                import_error=import_error,
            )
        )
    return tuple(statuses)


def compare_scalar(
    *,
    check_id: str,
    backend_id: str,
    quantity: str,
    chemworld_value: float,
    reference_value: float,
    unit: str,
    rtol: float,
    atol: float = 0.0,
    note: str = "",
) -> ReferenceComparison:
    """Compare one scalar with NumPy-style absolute-plus-relative tolerance."""

    if rtol < 0 or atol < 0:
        raise ValueError("rtol and atol must be nonnegative")
    abs_error = abs(chemworld_value - reference_value)
    rel_error = None if reference_value == 0 else abs_error / abs(reference_value)
    passed = abs_error <= (atol + rtol * abs(reference_value))
    return ReferenceComparison(
        check_id=check_id,
        backend_id=backend_id,
        quantity=quantity,
        chemworld_value=chemworld_value,
        reference_value=reference_value,
        unit=unit,
        rtol=rtol,
        atol=atol,
        abs_error=abs_error,
        rel_error=rel_error,
        passed=passed,
        note=note,
    )


def summarize_reference_comparisons(
    comparisons: Sequence[ReferenceComparison],
) -> dict[str, object]:
    """Summarize a set of optional reference comparisons."""

    total = len(comparisons)
    passed = sum(1 for comparison in comparisons if comparison.passed)
    failed = total - passed
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "all_passed": failed == 0,
        "checks": [comparison.to_dict() for comparison in comparisons],
    }


def skipped_reference_backends(
    statuses: Sequence[ReferenceBackendStatus],
    specs: Sequence[ReferenceBackendSpec] | None = None,
) -> tuple[dict[str, object], ...]:
    """Return explicit skip records for unavailable optional backends."""

    spec_map = {spec.backend_id: spec for spec in (specs or _REFERENCE_BACKENDS)}
    skipped: list[dict[str, object]] = []
    for status in statuses:
        reason: str | None = None
        if status.import_probe_attempted and status.import_available is False:
            reason = status.import_error or "import probe failed"
        elif not status.installed_available and not status.local_repo_available:
            reason = "package is not installed and no local reference repository was found"
        if reason is None:
            continue
        spec = spec_map.get(status.backend_id)
        skipped.append(
            {
                "backend_id": status.backend_id,
                "package_name": status.package_name,
                "reason": reason,
                "comparison_scope": []
                if spec is None
                else list(spec.comparison_scope),
                "model_limit_notes": []
                if spec is None
                else list(spec.model_limit_notes),
            }
        )
    return tuple(skipped)


def reference_validation_report(
    comparisons: Sequence[ReferenceComparison] = (),
    *,
    reference_root: str | Path | None = None,
    probe_import: bool = False,
) -> ReferenceValidationReport:
    """Build a JSON-friendly validation report with backend skip auditing."""

    statuses = reference_backend_status(
        reference_root=reference_root,
        probe_import=probe_import,
    )
    return ReferenceValidationReport(
        schema_version="chemworld-reference-validation-report-0.1",
        comparison_summary=summarize_reference_comparisons(comparisons),
        backend_statuses=statuses,
        skipped_backends=skipped_reference_backends(statuses),
        tolerance_profiles=reference_tolerance_profiles(),
    )


def write_reference_validation_report(
    path: str | Path,
    comparisons: Sequence[ReferenceComparison] = (),
    *,
    reference_root: str | Path | None = None,
    probe_import: bool = False,
) -> ReferenceValidationReport:
    """Write a reference-validation report and return the in-memory payload."""

    report = reference_validation_report(
        comparisons,
        reference_root=reference_root,
        probe_import=probe_import,
    )
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(report.to_dict(), handle, indent=2, sort_keys=True)
    return report


def _all_local_repo_names() -> tuple[str, ...]:
    names: list[str] = []
    for spec in _REFERENCE_BACKENDS:
        names.extend(spec.local_repo_names)
    return tuple(names)


def _installed_package_version(package_name: str) -> str | None:
    try:
        return importlib_metadata.version(package_name)
    except importlib_metadata.PackageNotFoundError:
        return None


def _python_path_candidates(root: Path, repo_name: str) -> tuple[Path, ...]:
    repo = root / repo_name
    candidates = (
        repo,
        repo / "src",
        repo / "wrappers" / "Python",
        repo / "interfaces" / "python",
        repo / "interface" / "python",
        repo / "addon" / "pycThermopack",
        repo / "Python",
    )
    return tuple(path for path in candidates if path.exists())


def _git_short_commit(repo_root: Path) -> str | None:
    git_entry = repo_root / ".git"
    if git_entry.is_file():
        content = git_entry.read_text(encoding="utf-8", errors="ignore").strip()
        if not content.startswith("gitdir:"):
            return None
        git_dir = (git_entry.parent / content.split(":", 1)[1].strip()).resolve()
    elif git_entry.is_dir():
        git_dir = git_entry
    else:
        return None

    head_path = git_dir / "HEAD"
    if not head_path.exists():
        return None
    head = head_path.read_text(encoding="utf-8", errors="ignore").strip()
    if head.startswith("ref:"):
        ref_path = git_dir / head.split(":", 1)[1].strip()
        if not ref_path.exists():
            return None
        head = ref_path.read_text(encoding="utf-8", errors="ignore").strip()
    return head[:7] if head else None


__all__ = [
    "ReferenceBackendSpec",
    "ReferenceBackendStatus",
    "ReferenceComparison",
    "ReferenceToleranceProfile",
    "ReferenceValidationReport",
    "compare_scalar",
    "import_reference_module",
    "reference_backend_context",
    "reference_backend_specs",
    "reference_backend_status",
    "reference_repo_paths",
    "reference_repo_roots",
    "reference_repos_root",
    "reference_tolerance_profiles",
    "reference_validation_report",
    "repository_root",
    "skipped_reference_backends",
    "summarize_reference_comparisons",
    "write_reference_validation_report",
]
