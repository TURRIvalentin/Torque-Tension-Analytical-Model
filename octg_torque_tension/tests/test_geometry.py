"""Tests for core/geometry.py — Eq. 2, Eq. 3, polar moment.

Validation targets from SPE-232499-MS:
  - 5.5-in 20# P110 pipe body: 641 kips at 110 ksi → A_pipe ≈ 5.828 in²
  - BTC6.30: 44% BCCS area advantage over pipe body → A_BCCS ≈ 8.39 in²
  - BTC6.05: 2.7% advantage → A_BCCS ≈ 5.969 in²
"""
import math

import pytest

from octg_torque_tension.core.geometry import bccs_area, fa_pin, polar_moment_annulus


# ---- Pipe body reference (5.5-in 20# P110) ----

def test_pipe_body_area() -> None:
    """A_pipe × SMYS ≈ 641 kips — matches Table 1 tension capacity."""
    a = bccs_area(5.5, 4.778)  # pipe body as special case: COD=OD, BCR≈ID
    tension_kips = a * 110_000 / 1_000
    assert abs(tension_kips - 641.0) < 1.5, (
        f"Pipe body tension {tension_kips:.1f} kips, expected 641 kips"
    )


# ---- BTC6.30 area — paper states 44% advantage ----

def test_btc630_bccs_area_44pct_advantage() -> None:
    """A_BCCS(BTC6.30) / A_pipe ≈ 1.44 (paper: 44% coupling strength advantage)."""
    a_pipe = bccs_area(5.5, 4.778)
    a_btc630 = bccs_area(6.30, 5.385)
    ratio = a_btc630 / a_pipe
    assert abs(ratio - 1.44) < 0.03, (
        f"Ratio {ratio:.3f}, expected ~1.44 (±0.03)"
    )


# ---- BTC6.05 area — paper states 2.7% advantage ----

def test_btc605_bccs_area_27pct_advantage() -> None:
    """A_BCCS(BTC6.05) / A_pipe ≈ 1.027 (paper: only 2.7% advantage)."""
    a_pipe = bccs_area(5.5, 4.778)
    a_btc605 = bccs_area(6.05, 5.385)
    ratio = a_btc605 / a_pipe
    assert abs(ratio - 1.027) < 0.025, (
        f"Ratio {ratio:.3f}, expected ~1.027 (±0.025)"
    )


# ---- BTC6.05 approximately 30% less than BTC6.30 ----

def test_btc605_bccs_30pct_less_than_btc630() -> None:
    """Paper states BTC6.05 BCCS is ~30% smaller than BTC6.30."""
    a_630 = bccs_area(6.30, 5.385)
    a_605 = bccs_area(6.05, 5.385)
    reduction = 1.0 - a_605 / a_630
    assert abs(reduction - 0.29) < 0.05, (
        f"Reduction {reduction:.3f}, expected ~0.29 (±0.05)"
    )


# ---- fa_pin geometry ----

def test_fa_pin_positive() -> None:
    area = fa_pin(5.5, 4.778)
    assert area > 0


def test_fa_pin_equals_pipe_area_when_st_pin_equals_od() -> None:
    """When STpin == pipe OD and ID == pipe ID, FA_pin equals pipe body area."""
    a_pin = fa_pin(5.5, 4.778)
    a_pipe = bccs_area(5.5, 4.778)
    assert abs(a_pin - a_pipe) < 1e-9


# ---- Validation inputs ----

def test_bccs_area_rejects_cod_le_bcr() -> None:
    with pytest.raises(ValueError, match="COD"):
        bccs_area(5.0, 5.5)


def test_bccs_area_rejects_equal_diameters() -> None:
    with pytest.raises(ValueError):
        bccs_area(5.5, 5.5)


def test_fa_pin_rejects_st_pin_le_id() -> None:
    with pytest.raises(ValueError, match="STpin"):
        fa_pin(4.0, 5.0)


# ---- Polar moment ----

def test_polar_moment_positive() -> None:
    j = polar_moment_annulus(6.30, 5.385)
    assert j > 0


def test_polar_moment_formula() -> None:
    """J = π/32 × (OD⁴ − ID⁴)."""
    od, id_ = 6.30, 5.385
    expected = math.pi / 32.0 * (od**4 - id_**4)
    assert abs(polar_moment_annulus(od, id_) - expected) < 1e-9
