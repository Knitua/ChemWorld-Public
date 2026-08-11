"""Report contracts for executable physical-constitution checks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    message: str = ""
    value: float | None = None
    tolerance: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
            "value": self.value,
            "tolerance": self.tolerance,
        }


@dataclass(frozen=True)
class ConstitutionReport:
    checks: list[CheckResult]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def failures(self) -> list[CheckResult]:
        return [check for check in self.checks if not check.passed]

    def to_list(self) -> list[dict[str, object]]:
        return [check.to_dict() for check in self.checks]


__all__ = ["CheckResult", "ConstitutionReport"]
