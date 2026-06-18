"""OCTG connection specifications as dataclasses.

All geometric parameters in imperial units (inches). Torque in ft·lbf (field convention).
Source: SPE-232499-MS Table 1; API 5CT (2018); API 5B (2023).

Naming convention for pre-built instances mirrors the paper:
    BTC6_30, BTC6_05, BSP6_05, BSL5_90.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from octg_torque_tension.core.materials import P110, SteelGrade


@dataclass
class Connection:
    """OCTG connection specification and CDS ratings.

    Fields directly from SPE-232499-MS Table 1 are marked [Table 1].
    Fields derived from geometry or API standards are marked [derived] or [API].
    Fields not given in the paper are Optional and default to None — a ValueError
    with an informative message is raised by dependent calculations when accessed.
    """

    # ---- Identity & ratings [Table 1] ----
    name: str
    cod: float                          # in  — coupling outer diameter
    operating_torque_ft_lbf: float      # ft·lbf — CDS operating torque limit
    tension_capacity_kips: float        # kips — CDS tension capacity
    clearance_in: float                 # in  — radial clearance vs 7-5/8 in 29.7# intermediate
    has_screwjack: bool                 # True = BTC-shouldered; False = wedge (F_TQ = 0)
    grade: SteelGrade = field(default_factory=lambda: P110)

    # ---- Pipe geometry [API 5CT] ----
    id_: float = 4.778                  # in  — casing inside diameter (5.5-in 20# P110: t=0.361 in)

    # ---- Coupling geometry — may be None if unavailable ----
    bcr: Optional[float] = None
    # in — Box Critical Root diameter (last engaged pin thread).
    # Source: API 5B thread tables or manufacturer CDS.
    # ESTIMATED for BTC connections: derived from 44% BCCS area advantage
    # (BTC6.30) and same pin geometry (BTC6.05). See MODEL_NOTES §7.

    st_pin: Optional[float] = None
    # in — Pin-face contact outside diameter.
    # ESTIMATED: ≈ pipe OD (5.500 in) for BTC connections.
    # Confirm from manufacturer CDS.

    l_b: Optional[float] = None
    # in — Coupling length.
    # ESTIMATED: 9.375 in for BTC 5.5-in (typical, API 5CT Table E.5).
    # Confirm from CDS.

    l_fl: Optional[float] = None
    # in/rev — Thread lead (axial advance per full revolution).
    # BTC 5.5-in = 5 TPI (API 5B) → LFL = 0.200 in/rev (estimated).

    lf_area_in2: Optional[float] = None
    # in² — Helical load-flank area (active thread surface).
    # TODO: compute from API 5B thread geometry via geometry.lf_area().
    # Must be provided as external input until thread geometry is confirmed.

    delta_mu: Optional[float] = None
    # rev — Make-up delta turns past shoulder point.
    # TODO: from experimental torque-turn plot (Fig. 11a). Not given numerically.

    delta_ot: Optional[float] = None
    # rev — Operational delta turns applied by top drive.
    # TODO: from experimental torque-turn plot (Fig. 11b). Not given numerically.

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        if self.cod <= 0:
            raise ValueError(f"COD must be positive, got {self.cod}")
        if self.id_ <= 0:
            raise ValueError(f"ID must be positive, got {self.id_}")
        if self.cod <= self.id_:
            raise ValueError(f"COD ({self.cod}) must exceed ID ({self.id_})")
        if self.operating_torque_ft_lbf < 0:
            raise ValueError("Operating torque must be ≥ 0")
        if self.tension_capacity_kips <= 0:
            raise ValueError("Tension capacity must be positive")
        if self.bcr is not None and self.cod <= self.bcr:
            raise ValueError(f"COD ({self.cod}) must exceed BCR ({self.bcr})")
        if self.st_pin is not None and self.st_pin <= self.id_:
            raise ValueError(f"STpin ({self.st_pin}) must exceed ID ({self.id_})")
        if self.l_b is not None and self.l_b <= 0:
            raise ValueError(f"Coupling length l_b must be positive, got {self.l_b}")
        if self.l_fl is not None and self.l_fl <= 0:
            raise ValueError(f"Thread lead l_fl must be positive, got {self.l_fl}")
        if self.lf_area_in2 is not None and self.lf_area_in2 <= 0:
            raise ValueError(f"lf_area_in2 must be positive, got {self.lf_area_in2}")
        if self.delta_mu is not None and self.delta_mu < 0:
            raise ValueError(f"delta_mu must be ≥ 0, got {self.delta_mu}")
        if self.delta_ot is not None and self.delta_ot < 0:
            raise ValueError(f"delta_ot must be ≥ 0, got {self.delta_ot}")

    def require(self, field_name: str, value: Optional[float]) -> float:
        """Return value or raise an informative error if None."""
        if value is None:
            raise ValueError(
                f"Connection '{self.name}': parameter '{field_name}' is required "
                f"but not set. This value is not given in SPE-232499-MS and must "
                f"be supplied from API 5B, the manufacturer CDS, or experimental "
                f"torque-turn data."
            )
        return value


# ---------------------------------------------------------------------------
# Pre-built connections from SPE-232499-MS Table 1 — 5.5-in 20# P110 casing
# ---------------------------------------------------------------------------

BTC6_30 = Connection(
    name="BTC6.30",
    cod=6.300,                          # in  [Table 1]
    operating_torque_ft_lbf=30_600.0,  # ft·lbf [Table 1]
    tension_capacity_kips=641.0,        # kips [Table 1]
    clearance_in=0.225,                 # in  [Table 1]
    has_screwjack=True,
    grade=P110,
    id_=4.778,                          # in  [API 5CT, 5.5-in 20# t=0.361 in]
    # ESTIMATED from paper text: "coupling strength advantage over pipe body = 44%"
    # → A_BCCS = 1.44 × A_pipe = 1.44 × 5.828 = 8.392 in²
    # → BCR = √(COD² − 4×A_BCCS/π) = √(39.69 − 10.70) = 5.385 in
    bcr=5.385,                          # in  [ESTIMATED — confirm from CDS]
    st_pin=5.500,                       # in  [ESTIMATED ≈ pipe OD — confirm from CDS]
    l_b=9.375,                          # in  [ESTIMATED — API 5CT Table E.5 typical]
    l_fl=0.200,                         # in/rev [ESTIMATED — API 5B 5 TPI → 1/5]
    lf_area_in2=None,                   # TODO: from API 5B thread geometry
    delta_mu=None,                      # TODO: from Fig. 11a torque-turn plot
    delta_ot=None,                      # TODO: from Fig. 11b torque-turn plot
)

BTC6_05 = Connection(
    name="BTC6.05",
    cod=6.050,                          # in  [Table 1]
    operating_torque_ft_lbf=30_600.0,  # ft·lbf [Table 1]
    tension_capacity_kips=641.0,        # kips [Table 1]
    clearance_in=0.350,                 # in  [Table 1]
    has_screwjack=True,
    grade=P110,
    id_=4.778,
    # ESTIMATED: same pin as BTC6.30, BCR unchanged → A_BCCS = π/4(6.05²−5.385²)
    # = 5.969 in² → +2.4% over pipe body (paper states 2.7%, within rounding).
    bcr=5.385,                          # in  [ESTIMATED — same pin, confirm from CDS]
    st_pin=5.500,                       # in  [ESTIMATED — confirm from CDS]
    l_b=9.375,                          # in  [ESTIMATED]
    l_fl=0.200,                         # in/rev [ESTIMATED]
    lf_area_in2=None,                   # TODO
    delta_mu=None,                      # TODO
    delta_ot=None,                      # TODO
)

BSP6_05 = Connection(
    name="BSP6.05 (Bushmaster® SP)",
    cod=6.050,                          # in  [Table 1]
    operating_torque_ft_lbf=39_800.0,  # ft·lbf [Table 1]
    tension_capacity_kips=641.0,        # kips [Table 1]
    clearance_in=0.350,                 # in  [Table 1]
    has_screwjack=False,                # wedge thread — no screw-jack, F_TQ = 0
    grade=P110,
    id_=4.778,
    # ESTIMATED: A_BCCS = A_pipe = 5.828 in² (wedge matches pipe body exactly)
    # → BCR = √(6.05² − 4×5.828/π) = 5.399 in
    bcr=5.399,                          # in  [ESTIMATED — confirm from Fermata CDS]
    st_pin=None,                        # TODO — wedge geometry differs from BTC
    l_b=None,                           # TODO
    l_fl=None,                          # TODO — wedge threads, not 5 TPI BTC
    lf_area_in2=None,                   # TODO (F_TQ=0 for wedge, so not used in screw-jack)
    delta_mu=None,                      # TODO (not applicable — no screw-jack)
    delta_ot=None,                      # TODO (not applicable — no screw-jack)
)

BSL5_90 = Connection(
    name="BSL5.90 (Bushmaster® SL)",
    cod=5.900,                          # in  [Table 1]
    operating_torque_ft_lbf=38_750.0,  # ft·lbf [Table 1]
    tension_capacity_kips=641.0,        # kips [Table 1]
    clearance_in=0.425,                 # in  [Table 1] — satisfies BLM ≥0.422 in
    has_screwjack=False,                # wedge thread — no screw-jack, F_TQ = 0
    grade=P110,
    id_=4.778,
    # ESTIMATED: A_BCCS ≥ A_pipe = 5.828 in² at minimum
    # → BCR = √(5.90² − 4×5.828/π) = 5.231 in
    bcr=5.231,                          # in  [ESTIMATED — confirm from Fermata CDS]
    st_pin=None,                        # TODO
    l_b=None,                           # TODO
    l_fl=None,                          # TODO
    lf_area_in2=None,                   # TODO
    delta_mu=None,                      # TODO
    delta_ot=None,                      # TODO
)

# Lookup table for UI and tests
CATALOG: dict[str, Connection] = {
    c.name.split(" ")[0]: c
    for c in [BTC6_30, BTC6_05, BSP6_05, BSL5_90]
}
