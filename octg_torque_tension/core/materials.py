"""Steel grade properties. All values in imperial units (psi).

Source: API 5CT (2018) Table C.1.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SteelGrade:
    """Immutable steel grade specification."""

    name: str
    smys: float  # psi — Specified Minimum Yield Strength (API 5CT)
    E: float = 30_000_000.0  # psi — Young's modulus (standard for steel)

    def __post_init__(self) -> None:
        if self.smys <= 0:
            raise ValueError(f"SMYS must be positive, got {self.smys}")
        if self.E <= 0:
            raise ValueError(f"Young's modulus must be positive, got {self.E}")


# Pre-built grades used in SPE-232499-MS and common OCTG applications
P110 = SteelGrade(name="P110", smys=110_000.0)  # paper reference grade
N80 = SteelGrade(name="N80", smys=80_000.0)
L80 = SteelGrade(name="L80", smys=80_000.0)
Q125 = SteelGrade(name="Q125", smys=125_000.0)
