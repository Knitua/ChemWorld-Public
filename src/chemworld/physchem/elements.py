"""Small element and formula utilities for ChemWorld.

This module is intentionally compact. It follows the design lesson of larger
property packages: keep composition parsing and elemental bookkeeping separate
from thermodynamic property models.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class ElementSpec:
    symbol: str
    atomic_number: int
    atomic_weight_g_mol: float

    def to_dict(self) -> dict[str, float | int | str]:
        return {
            "symbol": self.symbol,
            "atomic_number": self.atomic_number,
            "atomic_weight_g_mol": self.atomic_weight_g_mol,
        }


ELEMENTS: dict[str, ElementSpec] = {
    "H": ElementSpec("H", 1, 1.008),
    "He": ElementSpec("He", 2, 4.002602),
    "Li": ElementSpec("Li", 3, 6.94),
    "Be": ElementSpec("Be", 4, 9.0121831),
    "B": ElementSpec("B", 5, 10.81),
    "C": ElementSpec("C", 6, 12.011),
    "N": ElementSpec("N", 7, 14.007),
    "O": ElementSpec("O", 8, 15.999),
    "F": ElementSpec("F", 9, 18.998403163),
    "Ne": ElementSpec("Ne", 10, 20.1797),
    "Na": ElementSpec("Na", 11, 22.98976928),
    "Mg": ElementSpec("Mg", 12, 24.305),
    "Al": ElementSpec("Al", 13, 26.9815385),
    "Si": ElementSpec("Si", 14, 28.085),
    "P": ElementSpec("P", 15, 30.973761998),
    "S": ElementSpec("S", 16, 32.06),
    "Cl": ElementSpec("Cl", 17, 35.45),
    "Ar": ElementSpec("Ar", 18, 39.948),
    "K": ElementSpec("K", 19, 39.0983),
    "Ca": ElementSpec("Ca", 20, 40.078),
    "Fe": ElementSpec("Fe", 26, 55.845),
    "Cu": ElementSpec("Cu", 29, 63.546),
    "Zn": ElementSpec("Zn", 30, 65.38),
    "Br": ElementSpec("Br", 35, 79.904),
    "I": ElementSpec("I", 53, 126.90447),
    "Pt": ElementSpec("Pt", 78, 195.084),
}

_TOKEN_RE = re.compile(r"([A-Z][a-z]?|\(|\)|\d+(?:\.\d*)?|\.\d+)")
_TRAILING_CHARGE_RE = re.compile(r"(?:\([+-]?\d*[+-]\)|[+-]\d*|\d+[+-])$")


def parse_formula(formula: str) -> dict[str, float]:
    """Parse a compact chemical formula into an element-count mapping.

    Supported syntax covers the benchmark core: element symbols, integer or
    decimal counts, nested parentheses, and simple trailing charge annotations.
    Hydrate dots and isotope labels are intentionally out of scope for this
    first core layer.
    """

    cleaned = _TRAILING_CHARGE_RE.sub("", formula.strip())
    if not cleaned:
        raise ValueError("Formula cannot be empty")
    if "." in cleaned or "·" in cleaned:
        raise ValueError("Hydrate/dot formulas are not supported by the core parser")

    tokens = _TOKEN_RE.findall(cleaned)
    if "".join(tokens) != cleaned:
        raise ValueError(f"Unsupported formula syntax: {formula}")

    position = 0

    def parse_group(stop_on_close: bool) -> dict[str, float]:
        nonlocal position
        counts: dict[str, float] = {}
        while position < len(tokens):
            token = tokens[position]
            if token == ")":
                if not stop_on_close:
                    raise ValueError(f"Unmatched closing parenthesis in formula: {formula}")
                position += 1
                return counts
            if token == "(":
                position += 1
                nested = parse_group(stop_on_close=True)
                multiplier = read_multiplier()
                _merge_counts(counts, nested, multiplier)
                continue
            if _is_number(token):
                raise ValueError(f"Unexpected multiplier in formula: {formula}")
            if token not in ELEMENTS:
                raise ValueError(f"Unknown element symbol in formula: {token}")
            position += 1
            multiplier = read_multiplier()
            counts[token] = counts.get(token, 0.0) + multiplier
        if stop_on_close:
            raise ValueError(f"Unmatched opening parenthesis in formula: {formula}")
        return counts

    def read_multiplier() -> float:
        nonlocal position
        if position >= len(tokens) or not _is_number(tokens[position]):
            return 1.0
        value = float(tokens[position])
        position += 1
        if value <= 0:
            raise ValueError(f"Formula multipliers must be positive: {formula}")
        return value

    parsed = parse_group(stop_on_close=False)
    if not parsed:
        raise ValueError("Formula did not contain any elements")
    return {element: count for element, count in parsed.items() if count != 0.0}


def molecular_weight(composition: dict[str, float]) -> float:
    """Return molecular weight in g/mol from an element-count mapping."""

    weight = 0.0
    for symbol, count in composition.items():
        if symbol not in ELEMENTS:
            raise ValueError(f"Unknown element symbol: {symbol}")
        if count < 0:
            raise ValueError(f"Element count cannot be negative: {symbol}={count}")
        weight += ELEMENTS[symbol].atomic_weight_g_mol * count
    if weight <= 0:
        raise ValueError("Molecular weight must be positive")
    return weight


def atom_fractions(composition: dict[str, float]) -> dict[str, float]:
    total = sum(composition.values())
    if total <= 0:
        raise ValueError("Total atom count must be positive")
    return {symbol: count / total for symbol, count in composition.items()}


def mass_fractions_from_formula(composition: dict[str, float]) -> dict[str, float]:
    weight = molecular_weight(composition)
    return {
        symbol: ELEMENTS[symbol].atomic_weight_g_mol * count / weight
        for symbol, count in composition.items()
    }


def element_matrix(
    compositions: Iterable[dict[str, float]],
    element_order: tuple[str, ...] | None = None,
) -> tuple[tuple[tuple[float, ...], ...], tuple[str, ...]]:
    rows = list(compositions)
    if element_order is None:
        symbols = sorted(
            {symbol for composition in rows for symbol in composition},
            key=lambda symbol: ELEMENTS[symbol].atomic_number,
        )
    else:
        symbols = list(element_order)
        for symbol in symbols:
            if symbol not in ELEMENTS:
                raise ValueError(f"Unknown element symbol: {symbol}")
    matrix = tuple(tuple(row.get(symbol, 0.0) for symbol in symbols) for row in rows)
    return matrix, tuple(symbols)


def hill_formula(composition: dict[str, float]) -> str:
    """Return a Hill-system formula string for display and stable IDs."""

    symbols = list(composition)
    if "C" in composition:
        ordered = ["C"]
        if "H" in composition:
            ordered.append("H")
        ordered.extend(sorted(symbol for symbol in symbols if symbol not in {"C", "H"}))
    else:
        ordered = sorted(symbols)
    return "".join(f"{symbol}{_format_count(composition[symbol])}" for symbol in ordered)


def _merge_counts(target: dict[str, float], source: dict[str, float], multiplier: float) -> None:
    if multiplier <= 0:
        raise ValueError("Formula multipliers must be positive")
    for symbol, count in source.items():
        target[symbol] = target.get(symbol, 0.0) + count * multiplier


def _is_number(token: str) -> bool:
    return token[0].isdigit() or token[0] == "."


def _format_count(count: float) -> str:
    if abs(count - 1.0) < 1e-12:
        return ""
    if abs(count - round(count)) < 1e-12:
        return str(round(count))
    return f"{count:g}"
