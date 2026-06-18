"""Torque–tension interaction equations — Eq. 7, 8, 9 (SPE-232499-MS, corrected).

Unit conventions (critical):
    - Torque in ft·lbf throughout. The coefficient 0.096167 absorbs the conversion
      from the SI-consistent Von Mises form (in·lbf) to ft·lbf: 0.096167 ≈ 2/(12√3).
      Do NOT pre-convert torque to in·lbf before calling these functions.
    - All forces in lbf, stresses in psi, geometry in inches.

Sources:
    Eq. 7 : API RP 7G (2018); Lubinski (1962) — Von Mises yield criterion.
    Eq. 8 : algebraic rearrangement of Eq. 7, SPE-232499-MS p. 12.
    Eq. 9 : SPE-232499-MS p. 12.
"""
import math

_C = 0.096167  # API RP 7G unit-conversion coefficient; 2/(12√3) ≈ 0.09622, norm rounds to 0.096167


def q_t(j: float, cod: float, ym: float, p: float, area: float) -> float:
    """Eq. 7 — Torsional yield strength under tension [ft·lbf].

    Q_T = 0.096167 × (J / COD) × √(Ym² − (P/A)²)

    Args:
        j:    Polar moment of inertia of the cross-section [in⁴].
        cod:  Outer diameter [in] — radius arm for torsional shear.
        ym:   Material minimum yield strength [psi].
        p:    Applied tensile load [lbf].
        area: Cross-sectional area [in²].

    Returns:
        Q_T — maximum torsional yield torque at the given tension [ft·lbf].
    """
    if j <= 0 or cod <= 0 or ym <= 0 or area <= 0:
        raise ValueError("j, cod, ym, area must all be positive")
    if p < 0:
        raise ValueError(f"Tensile load p must be ≥ 0, got {p}")
    sigma = p / area
    if sigma > ym:
        raise ValueError(
            f"Axial stress {sigma:.0f} psi exceeds yield {ym:.0f} psi "
            f"(p={p:.0f} lbf, area={area:.4f} in²)"
        )
    return _C * (j / cod) * math.sqrt(ym**2 - sigma**2)


def p_btc(tq_ft_lbf: float, cod: float, j: float, f_smys: float, area: float) -> float:
    """Eq. 8 — Tensile capacity consumed by torque [lbf]. Tq must be in ft·lbf.

    P_BTC = area × (fSMYS − √(fSMYS² − (Tq·COD / (0.096167·J))²))

    P_BTC is the REDUCTION in tensile capacity due to torsion — NOT the remaining
    capacity. Monotonically increases from 0 (at Tq=0) to area×fSMYS (at full
    torsional yield). Applies to any annular cross-section: BCCS or pipe body.

    Inversion note: the inner term Tq·COD/(0.096167·J) has units of psi, equal
    to √3 × τ_outer_fiber. This is algebraically equivalent to rearranging Eq. 7
    for P given Q_T = Tq.

    Args:
        tq_ft_lbf: Applied torque [ft·lbf]. Do NOT convert to in·lbf first.
        cod:       Outer diameter of the cross-section [in].
        j:         Polar moment of inertia [in⁴].
        f_smys:    Specified minimum yield strength [psi].
        area:      Cross-sectional area [in²].

    Returns:
        P_BTC — consumed tensile capacity [lbf].
    """
    if j <= 0 or cod <= 0 or f_smys <= 0 or area <= 0:
        raise ValueError("cod, j, f_smys, area must all be positive")
    if tq_ft_lbf < 0:
        raise ValueError(f"Torque must be ≥ 0, got {tq_ft_lbf}")
    term = tq_ft_lbf * cod / (_C * j)  # psi — equivalent to √3·τ at the outer fiber
    if term >= f_smys:
        return area * f_smys  # full torsional yield: zero remaining tension capacity
    return area * (f_smys - math.sqrt(f_smys**2 - term**2))


def p_total(f_tq_val: float, p_btc_val: float) -> float:
    """Eq. 9 — Total consumed tensile capacity in the BCCS [lbf].

    P_total = F_TQ + P_BTC

    Both terms are consumed capacity, not applied hook load:
        F_TQ    : mechanical preload from screw-jack (Eq. 6). 0 for wedge connections.
        P_BTC   : capacity consumed by Von Mises torsion–tension interaction (Eq. 8).

    ⚠️ P_total ≠ F_TQ + F_hook. The hook load is a separate operational metric.
    The Applied_Tension (y-axis of Fig. 12–13) = A·fSMYS − P_total, not P_total itself.

    Args:
        f_tq_val:  Screw-jack preload from Eq. 6 [lbf]. Use 0.0 if has_screwjack=False.
        p_btc_val: Consumed capacity from torsion from Eq. 8 [lbf].

    Returns:
        P_total — total consumed capacity [lbf].
    """
    if f_tq_val < 0:
        raise ValueError(f"F_TQ must be ≥ 0, got {f_tq_val}")
    if p_btc_val < 0:
        raise ValueError(f"P_BTC must be ≥ 0, got {p_btc_val}")
    return f_tq_val + p_btc_val
