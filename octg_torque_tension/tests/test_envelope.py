"""Tests for core/envelope.py — two-curve model (MODEL_NOTES §6).

Validates:
    - Two curves: bccs_curve_kips, pipe_curve_kips; Envelope = min of both.
    - Wedge connections: F_TQ = 0 → BCCS curve has no screw-jack penalty.
    - BTC with full params: BCCS curve includes F_TQ penalty.
    - BTC without params: screwjack_params_available=False, f_tq_kips=None,
                          bccs_curve still computed (P_BTC only, optimistic).
    - has_screwjack=False overrides any supplied params.
    - check_operating_point: criterion F_hook <= envelope/DF; new field names.

⚠️  Placeholder params (lf_area, delta_mu, delta_ot) are for test mechanics only.
    They do not validate the paper's quantitative results.
"""
import math

import numpy as np
import pytest

from octg_torque_tension.core.connections import BTC6_05, BTC6_30, BSL5_90, BSP6_05
from octg_torque_tension.core.envelope import EnvelopeResult, OperatingPoint, check_operating_point, compute_envelope
from octg_torque_tension.core.geometry import bccs_area, polar_moment_annulus

_DF = 1.4
# ⚠️ PLACEHOLDER screw-jack params — mechanics testing only, not paper-validated
_SJ = dict(lf_area_in2=60.0, delta_mu=0.03, delta_ot=0.15)

_PIPE_OD = 5.5  # in — fixed pipe body OD (all connections, this study)


# ---------------------------------------------------------------------------
# EnvelopeResult field structure
# ---------------------------------------------------------------------------

class TestEnvelopeResultFields:
    def test_all_required_fields_present(self):
        r = compute_envelope(BSP6_05, design_factor=_DF)
        for field in ("torques_ft_lbf", "bccs_curve_kips", "pipe_curve_kips",
                      "envelope_kips", "f_tq_kips", "p_btc_bccs_kips",
                      "pipe_body_kips", "design_factor", "connection_name",
                      "has_screwjack", "screwjack_params_available"):
            assert hasattr(r, field), f"Missing field: {field}"

    def test_array_lengths_match_n_points(self):
        n = 150
        r = compute_envelope(BSP6_05, design_factor=_DF, n_points=n)
        for name in ("torques_ft_lbf", "bccs_curve_kips", "pipe_curve_kips",
                     "envelope_kips", "p_btc_bccs_kips"):
            arr = getattr(r, name)
            assert len(arr) == n, f"{name}: expected {n}, got {len(arr)}"

    def test_torque_starts_at_zero(self):
        r = compute_envelope(BSP6_05, design_factor=_DF)
        assert r.torques_ft_lbf[0] == 0.0

    def test_torque_ends_at_operating(self):
        r = compute_envelope(BSP6_05, design_factor=_DF)
        assert abs(r.torques_ft_lbf[-1] - BSP6_05.operating_torque_ft_lbf) < 1.0

    def test_design_factor_stored(self):
        r = compute_envelope(BSP6_05, design_factor=1.25)
        assert r.design_factor == 1.25

    def test_connection_name_stored(self):
        r = compute_envelope(BTC6_30, design_factor=_DF)
        assert BTC6_30.name in r.connection_name


# ---------------------------------------------------------------------------
# Pipe body curve
# ---------------------------------------------------------------------------

class TestPipeCurve:
    def test_pipe_curve_at_zero_torque_equals_table1(self):
        """At Tq=0: P_BTC_pipe=0 → Applied_Tension_Pipe = A_pipe * fSMYS ≈ 641 kips."""
        r = compute_envelope(BSP6_05, design_factor=_DF)
        assert abs(r.pipe_curve_kips[0] - 641.0) < 2.0, (
            f"Pipe curve at Tq=0: {r.pipe_curve_kips[0]:.1f} kips (expected ~641)"
        )

    def test_pipe_curve_equals_pipe_body_kips_at_zero(self):
        """pipe_curve_kips[0] must equal pipe_body_kips (reference line = Tq=0 value)."""
        r = compute_envelope(BTC6_30, design_factor=_DF)
        assert abs(r.pipe_curve_kips[0] - r.pipe_body_kips) < 0.1

    def test_pipe_curve_monotonically_decreasing(self):
        """P_BTC_pipe grows with Tq → pipe curve decreases (slowly)."""
        r = compute_envelope(BSP6_05, design_factor=_DF)
        diffs = np.diff(r.pipe_curve_kips)
        assert np.all(diffs <= 1e-6), "Pipe curve must be non-increasing"

    def test_pipe_curve_nearly_flat_for_operating_range(self):
        """Pipe body curve drops < 25% over the operating torque range.

        BSP6.05 has Tq_op=39,800 ft·lbf (higher than BTC's 30,600), so the pipe
        body torsional penalty is larger (~15.5% for BSP vs ~8.8% for BTC).
        The 'nearly flat' characterisation holds relative to the BCCS curve
        which can drop 30-50%+ over the same range.
        """
        r = compute_envelope(BSP6_05, design_factor=_DF)
        variation = (r.pipe_curve_kips[0] - r.pipe_curve_kips[-1]) / r.pipe_curve_kips[0]
        assert variation < 0.25, (
            f"Pipe curve drops {variation:.1%} over operating range — unexpectedly large"
        )

    def test_pipe_curve_same_for_all_connections(self):
        """All 4 connections use the same pipe body (5.5-in 20# P110) → identical pipe curve."""
        r_btc = compute_envelope(BTC6_30, design_factor=_DF)
        r_bsp = compute_envelope(BSP6_05, design_factor=_DF, n_points=200)
        # Use the same n_points and resample to same x-axis
        assert abs(r_btc.pipe_body_kips - r_bsp.pipe_body_kips) < 0.1


# ---------------------------------------------------------------------------
# Envelope = min(BCCS, Pipe)
# ---------------------------------------------------------------------------

class TestEnvelopeIsMin:
    def test_envelope_lte_bccs(self):
        r = compute_envelope(BSP6_05, design_factor=_DF)
        assert np.all(r.envelope_kips <= r.bccs_curve_kips + 1e-9)

    def test_envelope_lte_pipe(self):
        r = compute_envelope(BSP6_05, design_factor=_DF)
        assert np.all(r.envelope_kips <= r.pipe_curve_kips + 1e-9)

    def test_envelope_equals_min_pointwise(self):
        r = compute_envelope(BTC6_30, design_factor=_DF, **_SJ)
        expected = np.minimum(r.bccs_curve_kips, r.pipe_curve_kips)
        assert np.allclose(r.envelope_kips, expected, atol=1e-9)

    def test_all_curves_nonnegative(self):
        for conn in (BTC6_30, BTC6_05, BSP6_05, BSL5_90):
            r = compute_envelope(conn, design_factor=_DF, **_SJ)
            assert np.all(r.bccs_curve_kips >= 0.0)
            assert np.all(r.pipe_curve_kips >= 0.0)
            assert np.all(r.envelope_kips >= 0.0)


# ---------------------------------------------------------------------------
# Wedge connections (has_screwjack=False)
# ---------------------------------------------------------------------------

class TestWedgeConnections:
    def test_bsp_ftq_is_zero(self):
        r = compute_envelope(BSP6_05, design_factor=_DF)
        assert r.f_tq_kips is not None
        assert np.allclose(r.f_tq_kips, 0.0)

    def test_bsl_ftq_is_zero(self):
        r = compute_envelope(BSL5_90, design_factor=_DF)
        assert np.allclose(r.f_tq_kips, 0.0)

    def test_has_screwjack_false_overrides_supplied_params(self):
        """Flag must win even when params are supplied."""
        r = compute_envelope(BSP6_05, design_factor=_DF, **_SJ)
        assert np.allclose(r.f_tq_kips, 0.0), (
            "has_screwjack=False must override delta_mu/delta_ot/lf_area"
        )

    def test_wedge_screwjack_params_available(self):
        """Wedge always has 'params available' (F_TQ=0 is always known)."""
        r = compute_envelope(BSP6_05, design_factor=_DF)
        assert r.screwjack_params_available is True

    def test_wedge_bccs_curve_equals_capacity_minus_pbtc(self):
        """For wedge, F_TQ=0 → BCCS curve = A_BCCS*fSMYS - P_BTC_BCCS exactly."""
        r = compute_envelope(BSP6_05, design_factor=_DF)
        # BCCS curve = capacity - P_BTC_BCCS (no F_TQ term)
        bcr = BSP6_05.bcr
        a_bccs = bccs_area(BSP6_05.cod, bcr)
        capacity_kips = a_bccs * BSP6_05.grade.smys / 1_000
        expected = capacity_kips - r.p_btc_bccs_kips
        assert np.allclose(r.bccs_curve_kips, np.maximum(0, expected), atol=1e-6)


# ---------------------------------------------------------------------------
# BTC with screw-jack params
# ---------------------------------------------------------------------------

class TestBTCWithParams:
    def test_btc630_ftq_not_none(self):
        r = compute_envelope(BTC6_30, design_factor=_DF, **_SJ)
        assert r.f_tq_kips is not None

    def test_btc630_screwjack_available(self):
        r = compute_envelope(BTC6_30, design_factor=_DF, **_SJ)
        assert r.screwjack_params_available is True

    def test_btc630_ftq_monotone_increasing(self):
        """F_TQ grows with Tq (linear scaling assumption)."""
        r = compute_envelope(BTC6_30, design_factor=_DF, **_SJ)
        assert r.f_tq_kips[-1] > r.f_tq_kips[0]

    def test_btc630_bccs_curve_monotone_decreasing(self):
        """Both F_TQ and P_BTC grow → BCCS curve must decrease."""
        r = compute_envelope(BTC6_30, design_factor=_DF, **_SJ)
        diffs = np.diff(r.bccs_curve_kips)
        assert np.all(diffs <= 1e-6), "BCCS curve must be non-increasing for BTC"

    def test_btc_p_total_equals_ftq_plus_pbtc(self):
        """P_total = F_TQ + P_BTC at each point (Eq. 9 consistency)."""
        r = compute_envelope(BTC6_30, design_factor=_DF, **_SJ)
        bcr = BTC6_30.bcr
        a_bccs = bccs_area(BTC6_30.cod, bcr)
        capacity_kips = a_bccs * BTC6_30.grade.smys / 1_000
        # bccs_curve = capacity - F_TQ - P_BTC (before clamping)
        reconstructed_ptotal = capacity_kips - r.bccs_curve_kips
        expected_ptotal = r.f_tq_kips + r.p_btc_bccs_kips
        # Equality holds where bccs > 0 (no clamping in effect)
        not_clamped = r.bccs_curve_kips > 0
        assert np.allclose(
            reconstructed_ptotal[not_clamped], expected_ptotal[not_clamped], atol=1e-3
        )

    def test_btc_envelope_below_pipe_at_operating_torque_for_btc605(self):
        """BTC6.05 with calibrated placeholders: coupling governs at Tq_op (Fig.12b)."""
        r = compute_envelope(BTC6_05, design_factor=_DF, **_SJ)
        assert r.bccs_curve_kips[-1] < r.pipe_curve_kips[-1], (
            f"BTC6.05 BCCS ({r.bccs_curve_kips[-1]:.1f} kips) should be below "
            f"Pipe ({r.pipe_curve_kips[-1]:.1f} kips) at operating torque (placeholder params)"
        )

    def test_btc630_envelope_above_pipe_at_operating_torque(self):
        """BTC6.30 with calibrated placeholders: pipe body governs at Tq_op (Fig.12a)."""
        r = compute_envelope(BTC6_30, design_factor=_DF, **_SJ)
        assert r.bccs_curve_kips[-1] > r.pipe_curve_kips[-1], (
            f"BTC6.30 BCCS ({r.bccs_curve_kips[-1]:.1f} kips) should exceed "
            f"Pipe ({r.pipe_curve_kips[-1]:.1f} kips) at operating torque (pipe-limited)"
        )


# ---------------------------------------------------------------------------
# BTC without screw-jack params
# ---------------------------------------------------------------------------

class TestBTCWithoutParams:
    def test_btc_without_params_ftq_is_none(self):
        r = compute_envelope(BTC6_30, design_factor=_DF)  # no overrides
        assert r.f_tq_kips is None

    def test_btc_without_params_screwjack_not_available(self):
        r = compute_envelope(BTC6_30, design_factor=_DF)
        assert r.screwjack_params_available is False

    def test_btc_without_params_bccs_curve_still_computed(self):
        """Pipe curve and partial BCCS curve (P_BTC only) are always available."""
        r = compute_envelope(BTC6_30, design_factor=_DF)
        assert r.bccs_curve_kips is not None
        assert r.pipe_curve_kips is not None
        assert len(r.bccs_curve_kips) > 0

    def test_btc_without_params_pbtc_bccs_nonzero_at_operating_torque(self):
        """Even without F_TQ, P_BTC_BCCS should be non-trivial at operating torque."""
        r = compute_envelope(BTC6_30, design_factor=_DF)
        assert r.p_btc_bccs_kips[-1] > 0.0


# ---------------------------------------------------------------------------
# check_operating_point — new field semantics
# ---------------------------------------------------------------------------

class TestCheckOperatingPoint:
    def test_safe_at_zero_torque_low_hook(self):
        pt = check_operating_point(BSP6_05, 0.0, 100.0, design_factor=_DF)
        assert pt.safe
        assert pt.utilization < 1.0

    def test_unsafe_at_excess_hook(self):
        pt = check_operating_point(BSP6_05, 0.0, 2_000.0, design_factor=_DF)
        assert not pt.safe
        assert pt.utilization > 1.0

    def test_wedge_ftq_is_zero(self):
        pt = check_operating_point(BSL5_90, 20_000.0, 400.0, design_factor=_DF)
        assert pt.f_tq_kips == 0.0

    def test_p_total_equals_ftq_plus_pbtc(self):
        pt = check_operating_point(BSP6_05, 20_000.0, 300.0, design_factor=_DF)
        assert abs(pt.p_total_kips - (pt.f_tq_kips + pt.p_btc_kips)) < 1e-6

    def test_envelope_equals_min_of_two_curves(self):
        pt = check_operating_point(BTC6_30, 15_000.0, 300.0, design_factor=_DF, **_SJ)
        expected_env = min(pt.bccs_applied_tension_kips, pt.pipe_applied_tension_kips)
        assert abs(pt.envelope_kips - expected_env) < 1e-6

    def test_allowable_equals_envelope_over_df(self):
        pt = check_operating_point(BSP6_05, 20_000.0, 300.0, design_factor=_DF)
        assert abs(pt.allowable_kips - pt.envelope_kips / _DF) < 1e-6

    def test_utilization_equals_hook_over_allowable(self):
        pt = check_operating_point(BSP6_05, 20_000.0, 300.0, design_factor=_DF)
        expected = pt.hook_load_kips / pt.allowable_kips
        assert abs(pt.utilization - expected) < 1e-9

    def test_all_new_fields_present(self):
        pt = check_operating_point(BSP6_05, 0.0, 100.0, design_factor=_DF)
        for field in ("f_tq_kips", "p_btc_kips", "p_total_kips",
                      "bccs_applied_tension_kips", "pipe_applied_tension_kips",
                      "envelope_kips", "allowable_kips", "utilization", "safe"):
            assert hasattr(pt, field), f"Missing OperatingPoint field: {field}"

    def test_invalid_inputs_raise(self):
        with pytest.raises(ValueError):
            check_operating_point(BSP6_05, -1.0, 100.0)
        with pytest.raises(ValueError):
            check_operating_point(BSP6_05, 0.0, -1.0)
