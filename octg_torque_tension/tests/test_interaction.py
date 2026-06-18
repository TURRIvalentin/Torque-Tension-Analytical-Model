"""Tests for core/interaction.py — Eq. 7, 8, 9 (corrected forms).

Nomenclature:
    p_btc   : Eq. 8 — consumed tensile capacity (fSMYS MINUS sqrt form). Tq in ft·lbf.
    q_t     : Eq. 7 — torsional yield strength under tension. Returns ft·lbf.
    p_total : Eq. 9 — F_TQ + P_BTC (consumed capacity, NOT F_TQ + F_hook).

Key properties verified:
    - p_btc(Tq=0) = 0 for any cross-section.
    - p_btc is strictly monotone increasing in Tq.
    - p_btc = area × fSMYS at or beyond torsional yield.
    - q_t uses coefficient 0.096167 (NOT 2/√3 in in·lbf).
    - q_t and p_btc are inverses: p_btc(q_t(P=0)) ≈ area × fSMYS.
    - p_total = F_TQ + P_BTC (not F_TQ + F_hook).
"""
import math

import pytest

from octg_torque_tension.core.geometry import bccs_area, polar_moment_annulus
from octg_torque_tension.core.interaction import p_btc, p_total, q_t

_SMYS = 110_000.0   # psi — P110
_C = 0.096167       # API RP 7G coefficient (same as interaction._C)


# ---------------------------------------------------------------------------
# Eq. 8 — p_btc
# ---------------------------------------------------------------------------

class TestPBtcAtZeroTorque:
    """p_btc = 0 at Tq=0 for any cross-section (no torsional penalty)."""

    def test_pipe_body(self):
        a = bccs_area(5.5, 4.778)
        j = polar_moment_annulus(5.5, 4.778)
        assert p_btc(0.0, 5.5, j, _SMYS, a) == 0.0

    def test_btc630_coupling(self):
        a = bccs_area(6.30, 5.385)
        j = polar_moment_annulus(6.30, 5.385)
        assert p_btc(0.0, 6.30, j, _SMYS, a) == 0.0

    def test_btc605_coupling(self):
        a = bccs_area(6.05, 5.385)
        j = polar_moment_annulus(6.05, 5.385)
        assert p_btc(0.0, 6.05, j, _SMYS, a) == 0.0


class TestPBtcMonotonicity:
    """p_btc must increase strictly with torque."""

    def test_btc630_monotone_increasing(self):
        a = bccs_area(6.30, 5.385)
        j = polar_moment_annulus(6.30, 5.385)
        torques = [5_000.0 * i for i in range(1, 8)]
        values = [p_btc(tq, 6.30, j, _SMYS, a) for tq in torques]
        for prev, curr in zip(values[:-1], values[1:]):
            assert curr > prev, "p_btc must increase with torque"

    def test_pipe_body_monotone_increasing(self):
        a = bccs_area(5.5, 4.778)
        j = polar_moment_annulus(5.5, 4.778)
        torques = [5_000.0 * i for i in range(1, 8)]
        values = [p_btc(tq, 5.5, j, _SMYS, a) for tq in torques]
        for prev, curr in zip(values[:-1], values[1:]):
            assert curr > prev


class TestPBtcAtFullTorsionalYield:
    """At or beyond torsional yield, p_btc saturates to area × fSMYS."""

    def test_very_high_torque_returns_full_capacity(self):
        a = bccs_area(5.5, 4.778)
        j = polar_moment_annulus(5.5, 4.778)
        very_high_tq = 1e9  # ft·lbf — far beyond yield
        result = p_btc(very_high_tq, 5.5, j, _SMYS, a)
        assert result == a * _SMYS

    def test_at_torsional_yield_torque_saturates(self):
        """At Q_T_pure (P=0 torsional yield): p_btc = area × fSMYS."""
        a = bccs_area(6.30, 5.385)
        j = polar_moment_annulus(6.30, 5.385)
        tq_yield = _C * (j / 6.30) * _SMYS  # Q_T at P=0 — ft·lbf
        result = p_btc(tq_yield, 6.30, j, _SMYS, a)
        assert abs(result - a * _SMYS) < 1.0


class TestPBtcNumericalValues:
    """Spot-check numerical values for regression detection."""

    def test_btc605_at_20k_ftlbf(self):
        """BTC6.05 at 20,000 ft·lbf — computed from correct Eq. 8."""
        a = bccs_area(6.05, 5.385)
        j = polar_moment_annulus(6.05, 5.385)
        tq = 20_000.0  # ft·lbf
        term = tq * 6.05 / (_C * j)  # psi
        expected = a * (_SMYS - math.sqrt(_SMYS**2 - term**2))
        result = p_btc(tq, 6.05, j, _SMYS, a)
        assert abs(result - expected) < 1.0

    def test_pipe_body_at_30600_ftlbf(self):
        """Pipe body P_BTC at BTC operating torque — small but nonzero."""
        a = bccs_area(5.5, 4.778)
        j = polar_moment_annulus(5.5, 4.778)
        tq = 30_600.0  # ft·lbf
        term = tq * 5.5 / (_C * j)
        expected = a * (_SMYS - math.sqrt(_SMYS**2 - term**2))
        result = p_btc(tq, 5.5, j, _SMYS, a)
        assert abs(result - expected) < 1.0
        assert result > 0.0  # non-trivial penalty even for pipe body at this Tq

    def test_p_btc_increases_with_cod_at_same_torque(self):
        """Larger COD → larger shear stress → larger P_BTC at same torque."""
        j605 = polar_moment_annulus(6.05, 5.385)
        j630 = polar_moment_annulus(6.30, 5.385)
        a605 = bccs_area(6.05, 5.385)
        a630 = bccs_area(6.30, 5.385)
        tq = 20_000.0
        pbtc_per_area_605 = p_btc(tq, 6.05, j605, _SMYS, a605) / a605
        pbtc_per_area_630 = p_btc(tq, 6.30, j630, _SMYS, a630) / a630
        assert pbtc_per_area_630 < pbtc_per_area_605, (
            "BTC6.30 has larger J/COD ratio → lower stress per unit area → smaller P_BTC/A"
        )


class TestPBtcInputValidation:
    def test_negative_torque_raises(self):
        with pytest.raises(ValueError):
            p_btc(-1.0, 6.05, 40.0, _SMYS, 5.0)

    def test_zero_j_raises(self):
        with pytest.raises(ValueError):
            p_btc(10_000.0, 6.05, 0.0, _SMYS, 5.0)

    def test_zero_area_raises(self):
        with pytest.raises(ValueError):
            p_btc(10_000.0, 6.05, 40.0, _SMYS, 0.0)


# ---------------------------------------------------------------------------
# Eq. 7 — q_t (corrected coefficient 0.096167, returns ft·lbf)
# ---------------------------------------------------------------------------

class TestQT:
    def test_at_zero_tension_uses_correct_coefficient(self):
        """Q_T at P=0 must use 0.096167, not 2/√3 in in·lbf form."""
        j = polar_moment_annulus(6.30, 5.385)
        a = bccs_area(6.30, 5.385)
        result = q_t(j, 6.30, _SMYS, 0.0, a)
        expected_ft_lbf = _C * (j / 6.30) * _SMYS
        assert abs(result - expected_ft_lbf) < 0.1

    def test_decreases_with_applied_tension(self):
        """More tension → less torsional capacity."""
        j = polar_moment_annulus(6.30, 5.385)
        a = bccs_area(6.30, 5.385)
        qt_no_tension = q_t(j, 6.30, _SMYS, 0.0, a)
        qt_with_tension = q_t(j, 6.30, _SMYS, 200_000.0, a)
        assert qt_with_tension < qt_no_tension

    def test_q_t_and_p_btc_are_inverses(self):
        """q_t(P=0) is the torque at full torsional yield → p_btc at that Tq = A×fSMYS."""
        j = polar_moment_annulus(6.30, 5.385)
        a = bccs_area(6.30, 5.385)
        tq_yield = q_t(j, 6.30, _SMYS, 0.0, a)  # ft·lbf at P=0
        result = p_btc(tq_yield, 6.30, j, _SMYS, a)
        assert abs(result - a * _SMYS) < 1.0

    def test_rejects_tension_above_yield(self):
        j = polar_moment_annulus(5.5, 4.778)
        a = bccs_area(5.5, 4.778)
        with pytest.raises(ValueError, match="yield"):
            q_t(j, 5.5, _SMYS, _SMYS * a * 1.01, a)


# ---------------------------------------------------------------------------
# Eq. 9 — p_total
# ---------------------------------------------------------------------------

class TestPTotal:
    def test_adds_f_tq_and_p_btc(self):
        assert abs(p_total(50_000.0, 43_000.0) - 93_000.0) < 1e-9

    def test_zero_f_tq_for_wedge(self):
        """Wedge connections: F_TQ=0 → p_total = p_btc only."""
        pbtc_val = 75_000.0
        assert p_total(0.0, pbtc_val) == pbtc_val

    def test_rejects_negative_f_tq(self):
        with pytest.raises(ValueError):
            p_total(-1.0, 50_000.0)

    def test_rejects_negative_p_btc(self):
        with pytest.raises(ValueError):
            p_total(50_000.0, -1.0)
