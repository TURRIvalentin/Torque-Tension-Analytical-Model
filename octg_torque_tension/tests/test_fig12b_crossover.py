"""Fig. 12b crossover validation: BTC6.05 transitions from pipe-limited to coupling-limited.

Tests the two-curve model from MODEL_NOTES §6 (⚠️ HIPÓTESIS DERIVADA):

    Applied_Tension_BCCS(Tq) = A_BCCS·fSMYS − F_TQ(Tq) − P_BTC_BCCS(Tq)   [curva coupling]
    Applied_Tension_Pipe(Tq) = A_pipe·fSMYS − P_BTC_pipe(Tq)                [curva pipe body]
    Envelope(Tq) = min(BCCS, Pipe)

Expected behavior per SPE-232499-MS Fig. 12b (BTC6.05):
    - At low torque : BCCS curve > Pipe curve  → pipe body governs
    - At Tq_op      : BCCS curve < Pipe curve  → coupling governs
    - Sign change in (BCCS − Pipe) proves crossover exists mid-range

Control (Fig. 12a, BTC6.30):
    - BCCS stays above Pipe at Tq_op → pipe body governs throughout

This test uses p_btc (corrected Eq. 8) and will FAIL with ImportError until
interaction.py must export p_btc (corrected Eq. 8 — fSMYS minus sqrt form).

⚠️ PLACEHOLDER PARAMS: ΔMU, ΔOT_rated, LB, STpin are estimates chosen to reproduce
the correct crossover topology. Replace with Fig. 11 data once available.
"""
import math

import pytest

from octg_torque_tension.core.geometry import fa_pin, polar_moment_annulus
from octg_torque_tension.core.interaction import p_btc  # Eq. 8 corrected — will fail until fixed
from octg_torque_tension.core.materials import P110
from octg_torque_tension.core.screwjack import delta_displacement, epsilon_r
from octg_torque_tension.core.screwjack import f_tq as calc_f_tq

# ---------------------------------------------------------------------------
# Pipe body geometry — 5.5-in 20# P110 (same for all 4 connections, Table 1)
# ---------------------------------------------------------------------------
_OD_PIPE = 5.5    # in
_ID_PIPE = 4.778  # in
_A_PIPE = math.pi / 4 * (_OD_PIPE**2 - _ID_PIPE**2)   # 5.828 in²
_J_PIPE = math.pi / 32 * (_OD_PIPE**4 - _ID_PIPE**4)  # in⁴

# ---------------------------------------------------------------------------
# BTC6.05 BCCS geometry  (BCR estimated — MODEL_NOTES §TODO)
# ---------------------------------------------------------------------------
_COD_605 = 6.05   # in
_BCR_605 = 5.385  # in — ⚠️ estimated from 44% area advantage claim; confirm from CDS
_A_BCCS_605 = math.pi / 4 * (_COD_605**2 - _BCR_605**2)   # ~5.97 in²
_J_BCCS_605 = math.pi / 32 * (_COD_605**4 - _BCR_605**4)  # in⁴

# ---------------------------------------------------------------------------
# BTC6.30 BCCS geometry  (same BCR — same pin cross-section, different coupling)
# ---------------------------------------------------------------------------
_COD_630 = 6.30
_BCR_630 = 5.385  # in — ⚠️ same estimate as 6.05; confirm from CDS
_A_BCCS_630 = math.pi / 4 * (_COD_630**2 - _BCR_630**2)   # ~8.40 in²
_J_BCCS_630 = math.pi / 32 * (_COD_630**4 - _BCR_630**4)  # in⁴

# ---------------------------------------------------------------------------
# ⚠️ PLACEHOLDER screw-jack params — chosen to reproduce Fig. 12b crossover.
# Actual values must come from Fig. 11 torque-turn experimental data.
#
# Rationale for these specific values:
#   ΔMU = 0.03 rev  → F_TQ(makeup only) ≈ 6.9 kips  → BCCS(Tq=0) ≈ 650 kips
#                      just above Pipe(Tq=0) = 641 kips → pipe governs at zero torque ✓
#   ΔOT = 0.15 rev  → F_TQ(Tq_op) ≈ 41 kips, P_BTC ≈ 43 kips
#                      BCCS(Tq_op) ≈ 572 kips < Pipe(Tq_op) ≈ 584 kips → coupling governs ✓
# ---------------------------------------------------------------------------
_TQ_OP = 30_600.0    # ft·lbf — BTC operating torque (Table 1)
_LB = 13.0           # in — coupling length estimate (API 5CT Gr. B); ⚠️ TODO from CDS
_LFL = 0.200         # in/rev — 5 TPI BTC per API 5B; ⚠️ confirm from API 5B Table B.4
_ST_PIN = 5.5        # in — pin face OD placeholder; ⚠️ TODO from connection CDS
_DELTA_MU = 0.03     # rev — ⚠️ PLACEHOLDER; actual from Fig. 11a
_DELTA_OT_RATED = 0.15  # rev — ⚠️ PLACEHOLDER; actual from Fig. 11b at full Tq
_LF_AREA = 60.0      # in² — estimated from API 5B thread geometry


# ---------------------------------------------------------------------------
# Helper functions — implement the two-curve model directly (no envelope.py)
# ---------------------------------------------------------------------------

def _ftq_btc605_at(tq_ft_lbf: float) -> float:
    """F_TQ for BTC6.05 from Eq. 1–6.

    ⚠️ SUPOSICIÓN (no está en el paper): ΔOT ∝ Tq (escalado lineal).
    Ver MODEL_NOTES §6 — SUPOSICIÓN OCULTA. Reemplazar con datos de Fig. 11.
    """
    dot = _DELTA_OT_RATED * tq_ft_lbf / _TQ_OP
    lot = (_DELTA_MU + dot) * _LFL
    fa_pin_area = fa_pin(_ST_PIN, _ID_PIPE)
    eps = epsilon_r(_A_BCCS_605, fa_pin_area, _LF_AREA)
    d = delta_displacement(lot, eps)
    return calc_f_tq(d, P110.E, _A_BCCS_605, _LB)


def _ftq_btc630_at(tq_ft_lbf: float) -> float:
    """F_TQ for BTC6.30 from Eq. 1–6.

    ⚠️ SUPOSICIÓN: ΔOT ∝ Tq (lineal). Ver MODEL_NOTES §6 — SUPOSICIÓN OCULTA.
    """
    dot = _DELTA_OT_RATED * tq_ft_lbf / _TQ_OP
    lot = (_DELTA_MU + dot) * _LFL
    fa_pin_area = fa_pin(_ST_PIN, _ID_PIPE)
    eps = epsilon_r(_A_BCCS_630, fa_pin_area, _LF_AREA)
    d = delta_displacement(lot, eps)
    return calc_f_tq(d, P110.E, _A_BCCS_630, _LB)


def _applied_tension_bccs_605(tq_ft_lbf: float) -> float:
    """MODEL_NOTES §6: Applied_Tension_BCCS = A·fSMYS − F_TQ − P_BTC. Units: lbf."""
    return (
        _A_BCCS_605 * P110.smys
        - _ftq_btc605_at(tq_ft_lbf)
        - p_btc(tq_ft_lbf, _COD_605, _J_BCCS_605, P110.smys, _A_BCCS_605)
    )


def _applied_tension_bccs_630(tq_ft_lbf: float) -> float:
    """MODEL_NOTES §6: Applied_Tension_BCCS for BTC6.30. Units: lbf."""
    return (
        _A_BCCS_630 * P110.smys
        - _ftq_btc630_at(tq_ft_lbf)
        - p_btc(tq_ft_lbf, _COD_630, _J_BCCS_630, P110.smys, _A_BCCS_630)
    )


def _applied_tension_pipe(tq_ft_lbf: float) -> float:
    """MODEL_NOTES §6: Applied_Tension_Pipe = A_pipe·fSMYS − P_BTC_pipe. Units: lbf.

    p_btc is applied to pipe body geometry — same Eq. 8, different (OD, J, A).
    No F_TQ term: pipe body has no screw-jack.
    """
    return (
        _A_PIPE * P110.smys
        - p_btc(tq_ft_lbf, _OD_PIPE, _J_PIPE, P110.smys, _A_PIPE)
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBTC605CrossoverFig12b:
    """BTC6.05 must transition from pipe-limited to coupling-limited (Fig. 12b)."""

    def test_pipe_governs_at_zero_torque(self):
        """At Tq=0: BCCS > Pipe → pipe body is the limiting component."""
        bccs = _applied_tension_bccs_605(0.0)
        pipe = _applied_tension_pipe(0.0)
        assert bccs > pipe, (
            f"At Tq=0: BCCS ({bccs/1000:.1f} kips) should exceed Pipe "
            f"({pipe/1000:.1f} kips). Pipe body should govern at zero torque."
        )

    def test_coupling_governs_at_operating_torque(self):
        """At Tq_op: BCCS < Pipe → coupling is the limiting component."""
        bccs = _applied_tension_bccs_605(_TQ_OP)
        pipe = _applied_tension_pipe(_TQ_OP)
        assert bccs < pipe, (
            f"At Tq={_TQ_OP/1000:.0f} kft·lbf: BCCS ({bccs/1000:.1f} kips) "
            f"must fall below Pipe ({pipe/1000:.1f} kips). Coupling should govern."
        )

    def test_crossover_exists_by_sign_change(self):
        """Intermediate value theorem: sign change in (BCCS − Pipe) proves a crossover."""
        diff_low = _applied_tension_bccs_605(0.0) - _applied_tension_pipe(0.0)
        diff_high = _applied_tension_bccs_605(_TQ_OP) - _applied_tension_pipe(_TQ_OP)
        assert diff_low > 0, f"No positive start: diff @ Tq=0 = {diff_low/1000:.2f} kips"
        assert diff_high < 0, f"No negative end: diff @ Tq_op = {diff_high/1000:.2f} kips"

    def test_bccs_curve_monotonically_decreasing(self):
        """Both F_TQ and P_BTC grow with Tq → BCCS curve must be non-increasing.

        ⚠️ Válido sólo bajo la suposición ΔOT ∝ Tq (lineal). Ver MODEL_NOTES §6.
        """
        tqs = [i * _TQ_OP / 40 for i in range(41)]
        values = [_applied_tension_bccs_605(tq) for tq in tqs]
        for i in range(1, len(values)):
            assert values[i] <= values[i - 1] + 1.0, (
                f"BCCS non-monotone at step {i}: "
                f"{values[i-1]/1000:.3f} → {values[i]/1000:.3f} kips"
            )

    def test_pipe_curve_monotonically_decreasing(self):
        """P_BTC_pipe grows with Tq → pipe curve must be non-increasing (slowly)."""
        tqs = [i * _TQ_OP / 40 for i in range(41)]
        values = [_applied_tension_pipe(tq) for tq in tqs]
        for i in range(1, len(values)):
            assert values[i] <= values[i - 1] + 1.0, (
                f"Pipe curve non-monotone at step {i}: "
                f"{values[i-1]/1000:.3f} → {values[i]/1000:.3f} kips"
            )

    def test_bccs_capacity_at_zero_torque_equals_area_times_smys_minus_ftq_mu(self):
        """At Tq=0: P_BTC=0 so BCCS capacity = A_BCCS·fSMYS − F_TQ(makeup only)."""
        bccs = _applied_tension_bccs_605(0.0)
        expected = _A_BCCS_605 * P110.smys - _ftq_btc605_at(0.0)
        assert abs(bccs - expected) < 1.0  # lbf tolerance


class TestBTC630NoCrossoverFig12a:
    """BTC6.30 control: larger COD keeps BCCS above Pipe throughout (pipe-limited)."""

    def test_pipe_governs_at_operating_torque(self):
        """BTC6.30 must remain pipe-limited at its operating torque (Fig. 12a)."""
        bccs = _applied_tension_bccs_630(_TQ_OP)
        pipe = _applied_tension_pipe(_TQ_OP)
        assert bccs > pipe, (
            f"BTC6.30 at Tq_op: BCCS ({bccs/1000:.1f} kips) should exceed "
            f"Pipe ({pipe/1000:.1f} kips). Pipe body should remain governing."
        )

    def test_bccs_630_higher_capacity_than_605_at_all_torques(self):
        """BTC6.30 has larger A_BCCS → higher coupling capacity than BTC6.05 at all Tq."""
        tqs = [i * _TQ_OP / 10 for i in range(11)]
        for tq in tqs:
            c630 = _applied_tension_bccs_630(tq)
            c605 = _applied_tension_bccs_605(tq)
            assert c630 > c605, (
                f"At Tq={tq/1000:.0f} kft·lbf: BTC6.30 BCCS ({c630/1000:.1f} kips) "
                f"should exceed BTC6.05 ({c605/1000:.1f} kips)."
            )


class TestPipeCurveProperties:
    """Pipe body curve is nearly identical for all 4 connections (same pipe)."""

    def test_pipe_capacity_at_zero_torque_equals_table1(self):
        """At Tq=0: P_BTC_pipe=0, so Applied_Tension_Pipe = A_pipe·fSMYS = 641 kips."""
        pipe_at_zero = _applied_tension_pipe(0.0)
        table1_tension = 641_000.0  # lbf — Table 1 of SPE-232499-MS
        assert abs(pipe_at_zero - table1_tension) < 2_000.0, (
            f"Pipe capacity at Tq=0: {pipe_at_zero/1000:.1f} kips "
            f"(expected ~641 kips from Table 1, tolerance ±2 kips)"
        )

    def test_pipe_btc_penalty_grows_with_torque(self):
        """P_BTC_pipe must be strictly increasing with Tq (monotone by construction of Eq. 8)."""
        tqs = [5_000.0 * i for i in range(1, 8)]
        penalties = [
            _A_PIPE * P110.smys - _applied_tension_pipe(tq) for tq in tqs
        ]
        for i in range(1, len(penalties)):
            assert penalties[i] > penalties[i - 1], (
                f"P_BTC_pipe not increasing at step {i}: "
                f"{penalties[i-1]:.0f} → {penalties[i]:.0f} lbf"
            )
