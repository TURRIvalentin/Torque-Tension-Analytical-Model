"""Tests for core/screwjack.py — Eq. 1, 4, 5, 6.

Key invariants from SPE-232499-MS and corrected equations:
  - 0 < εR < 1 always (Eq. 4, by construction)
  - δ < LOT always (Eq. 5, since εR < 1)
  - F_TQ = 0 when LOT = 0
  - F_TQ increases monotonically with LOT
"""
import pytest

from octg_torque_tension.core.geometry import bccs_area, fa_pin
from octg_torque_tension.core.screwjack import (
    delta_displacement,
    epsilon_r,
    f_tq,
    l_ot,
)

# Shared geometry constants (BTC6.30 estimated values)
_COD = 6.30
_BCR = 5.385
_ST_PIN = 5.50
_ID = 4.778
_LF_AREA = 15.0  # in² — placeholder for tests; real value from API 5B
_A_BCCS = bccs_area(_COD, _BCR)
_FA_PIN = fa_pin(_ST_PIN, _ID)
_E = 30_000_000.0   # psi
_L_B = 9.375        # in
_L_FL = 0.200       # in/rev


# ---- Eq. 1 — l_ot ----

def test_l_ot_basic() -> None:
    """LOT = (ΔMU + ΔOT) × LFL."""
    assert abs(l_ot(3.0, 1.5, 0.200) - 0.900) < 1e-9


def test_l_ot_zero_turns() -> None:
    assert l_ot(0.0, 0.0, 0.200) == 0.0


def test_l_ot_rejects_negative_turns() -> None:
    with pytest.raises(ValueError):
        l_ot(-1.0, 0.5, 0.200)


def test_l_ot_rejects_zero_lead() -> None:
    with pytest.raises(ValueError):
        l_ot(1.0, 1.0, 0.0)


# ---- Eq. 4 — epsilon_r ----

def test_epsilon_r_bounds() -> None:
    """εR must be strictly in (0, 1)."""
    eps = epsilon_r(_A_BCCS, _FA_PIN, _LF_AREA)
    assert 0.0 < eps < 1.0


def test_epsilon_r_decreases_as_lf_area_increases() -> None:
    """More load-flank area → BCCS carries smaller fraction → εR decreases."""
    eps_small = epsilon_r(_A_BCCS, _FA_PIN, 5.0)
    eps_large = epsilon_r(_A_BCCS, _FA_PIN, 50.0)
    assert eps_small > eps_large


def test_epsilon_r_increases_as_a_bccs_increases() -> None:
    """Larger BCCS → larger fraction of total area → εR increases."""
    eps_small = epsilon_r(5.0, _FA_PIN, _LF_AREA)
    eps_large = epsilon_r(15.0, _FA_PIN, _LF_AREA)
    assert eps_large > eps_small


def test_epsilon_r_rejects_non_positive_areas() -> None:
    with pytest.raises(ValueError):
        epsilon_r(0.0, _FA_PIN, _LF_AREA)
    with pytest.raises(ValueError):
        epsilon_r(_A_BCCS, 0.0, _LF_AREA)
    with pytest.raises(ValueError):
        epsilon_r(_A_BCCS, _FA_PIN, 0.0)


# ---- Eq. 5 — delta_displacement ----

def test_delta_less_than_lot() -> None:
    """δ < LOT when εR < 1 — fundamental invariant of corrected Eq. 5."""
    eps = epsilon_r(_A_BCCS, _FA_PIN, _LF_AREA)
    lot = 0.45
    d = delta_displacement(lot, eps)
    assert d < lot


def test_delta_at_zero_lot() -> None:
    eps = epsilon_r(_A_BCCS, _FA_PIN, _LF_AREA)
    assert delta_displacement(0.0, eps) == 0.0


def test_delta_scales_linearly_with_lot() -> None:
    eps = epsilon_r(_A_BCCS, _FA_PIN, _LF_AREA)
    d1 = delta_displacement(0.2, eps)
    d2 = delta_displacement(0.4, eps)
    assert abs(d2 / d1 - 2.0) < 1e-9


def test_delta_rejects_invalid_eps_r() -> None:
    with pytest.raises(ValueError):
        delta_displacement(0.5, 0.0)
    with pytest.raises(ValueError):
        delta_displacement(0.5, 1.0)
    with pytest.raises(ValueError):
        delta_displacement(0.5, 1.5)


# ---- Eq. 6 — f_tq ----

def test_f_tq_zero_at_zero_displacement() -> None:
    """F_TQ = 0 when δ = 0 (no screw-jack advance)."""
    assert f_tq(0.0, _E, _A_BCCS, _L_B) == 0.0


def test_f_tq_positive_for_positive_delta() -> None:
    eps = epsilon_r(_A_BCCS, _FA_PIN, _LF_AREA)
    lot = l_ot(3.5, 1.5, _L_FL)
    d = delta_displacement(lot, eps)
    result = f_tq(d, _E, _A_BCCS, _L_B)
    assert result > 0


def test_f_tq_monotone_with_delta() -> None:
    """F_TQ increases with δ (Eq. 6 is linear in δ)."""
    f1 = f_tq(0.01, _E, _A_BCCS, _L_B)
    f2 = f_tq(0.02, _E, _A_BCCS, _L_B)
    assert f2 > f1


def test_f_tq_formula_explicit() -> None:
    """F_TQ = δ × E × A_BCCS / L_B."""
    d, e, a, lb = 0.05, 30_000_000.0, 8.39, 9.375
    expected = d * e * a / lb
    assert abs(f_tq(d, e, a, lb) - expected) < 1.0  # within 1 lbf


def test_f_tq_rejects_negative_delta() -> None:
    with pytest.raises(ValueError):
        f_tq(-0.01, _E, _A_BCCS, _L_B)


# ---- Integration: chain Eq. 1 → 4 → 5 → 6 ----

def test_chain_non_zero_result() -> None:
    """Full chain produces a positive F_TQ for typical BTC inputs."""
    lot = l_ot(3.5, 1.5, _L_FL)
    eps = epsilon_r(_A_BCCS, _FA_PIN, _LF_AREA)
    d = delta_displacement(lot, eps)
    result = f_tq(d, _E, _A_BCCS, _L_B)
    assert result > 0, f"Expected positive F_TQ, got {result}"
