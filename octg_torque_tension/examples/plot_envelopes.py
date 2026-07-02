"""Example: reproduce SPE-232499-MS Figures 12 & 13 qualitatively.

Generates torque-tension envelopes for all four connections from Table 1
and compares:
  - Fig. 12 analogue: BTC6.30 and BTC6.05 (shouldered, screw-jack)
  - Fig. 13 analogue: BSP6.05 and BSL5.90 (wedge, flat envelope)

Run from the project root:
    python -m octg_torque_tension.examples.plot_envelopes

Output: saves PNGs to examples/output/.
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")  # non-interactive backend for scripts
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from octg_torque_tension.core.connections import BTC6_05, BTC6_30, BSL5_90, BSP6_05
from octg_torque_tension.core.envelope import compute_envelope

# ---- Shared placeholder screw-jack params (not given numerically in paper) ----
# ⚠️ TODO: replace with experimental torque-turn data from Fig. 11.
# Calibration rationale:
#   LFArea ≈ 60 in² estimated from API 5B buttress geometry (5 TPI, 5.5-in):
#     n_threads ≈ 47, circumference ≈ π×5.8 in, h ≈ 0.07 in → ~60 in²
#   delta_mu + delta_ot ≈ 0.30 rev produces F_TQ(BTC6.30) ≈ 180 kips at op. torque,
#   giving F_available ≈ 456 kips — consistent with paper Fig.12a (pipe body governs).
#   At larger values (e.g. 5.0 rev) F_TQ becomes unphysically large (>> tension capacity).
SCREWJACK_PARAMS = dict(
    lf_area_in2=60.0,    # in² — estimated from API 5B thread geometry
    delta_mu=0.20,        # rev — estimated; TODO from Fig. 11a (typically 0.1–0.5 rev)
    delta_ot=0.10,        # rev — estimated at rated torque; TODO from Fig. 11b
)


def _plot_envelope(ax: plt.Axes, conn, result, color: str, linestyle: str = "-") -> None:
    """Plot one connection's envelope curves on an axes."""
    tq = result.torques_ft_lbf / 1_000  # kft·lbf for readability

    # Pipe body curve
    ax.plot(tq, result.pipe_curve_kips, color="black", lw=1, ls=":",
            label="Pipe body curve")

    # BCCS curve (coupling torsional + screw-jack)
    ax.plot(tq, result.bccs_curve_kips, color=color, lw=1.5, ls="--",
            label=f"{conn.name} — BCCS curve")

    # Envelope = min(BCCS, Pipe)
    if result.screwjack_params_available or not result.has_screwjack:
        ax.plot(tq, result.envelope_kips, color=color, lw=2, ls=linestyle,
                label=f"{conn.name} — Envelope")
        ax.fill_between(tq, result.envelope_kips, alpha=0.12, color=color)


def _style_ax(ax: plt.Axes, title: str) -> None:
    ax.set_xlabel("Applied Torque [kft·lbf]", fontsize=11)
    ax.set_ylabel("Available Tension [kips]", fontsize=11)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_ylim(0, 1100)
    ax.legend(fontsize=8, loc="lower left")
    ax.grid(True, alpha=0.3)
    ax.annotate(
        "Note: screw-jack params (LFArea, ΔMU, ΔOT) are placeholder estimates.\n"
        "Shapes are qualitative — see MODEL_NOTES §7 for missing data.",
        xy=(0.02, 0.02), xycoords="axes fraction", fontsize=7, color="dimgray",
    )


def plot_fig12_btc(output_dir: str) -> None:
    """Fig. 12 analogue: BTC shouldered connections."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    fig.suptitle(
        "SPE-232499-MS Fig.12 — Torque–Tension Envelope: BTC Shouldered Connections\n"
        "5.5-in 20# P110",
        fontsize=12,
    )

    r630 = compute_envelope(BTC6_30, **SCREWJACK_PARAMS)
    r605 = compute_envelope(BTC6_05, **SCREWJACK_PARAMS)

    _plot_envelope(ax1, BTC6_30, r630, color="#1f77b4")
    _style_ax(ax1, "BTC6.30 (Standard Clearance, COD=6.30 in)")

    _plot_envelope(ax2, BTC6_05, r605, color="#d62728")
    _style_ax(ax2, "BTC6.05 (Enhanced Clearance, COD=6.05 in)")

    # Annotate transition region for BTC6.05 (paper: ~20 kft·lbf transition)
    ax2.axvline(20, color="orange", lw=1, ls="-.", alpha=0.7,
                label="~Torque-limited transition (~20 kft·lbf)")
    ax2.legend(fontsize=7, loc="lower left")

    _print_summary("BTC6.30", BTC6_30, r630)
    _print_summary("BTC6.05", BTC6_05, r605)

    plt.tight_layout()
    path = os.path.join(output_dir, "fig12_btc_envelope.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"Saved: {path}")
    plt.close()


def plot_fig13_wedge(output_dir: str) -> None:
    """Fig. 13 analogue: wedge connections — flat envelopes."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    fig.suptitle(
        "SPE-232499-MS Fig.13 — Torque–Tension Envelope: Wedge Connections\n"
        "5.5-in 20# P110 | F_TQ = 0 (no screw-jack)",
        fontsize=12,
    )

    rbsp = compute_envelope(BSP6_05)
    rbsl = compute_envelope(BSL5_90)

    _plot_envelope(ax1, BSP6_05, rbsp, color="#2ca02c")
    _style_ax(ax1, "BSP6.05 — Bushmaster® SP (Wedge, COD=6.05 in)")

    _plot_envelope(ax2, BSL5_90, rbsl, color="#9467bd")
    _style_ax(ax2, "BSL5.90 — Bushmaster® SL (Wedge, COD=5.90 in)")

    _print_summary("BSP6.05", BSP6_05, rbsp)
    _print_summary("BSL5.90", BSL5_90, rbsl)

    plt.tight_layout()
    path = os.path.join(output_dir, "fig13_wedge_envelope.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"Saved: {path}")
    plt.close()


def plot_all_connections(output_dir: str) -> None:
    """Overlay all four connections for direct comparison."""
    fig, ax = plt.subplots(figsize=(10, 6))

    configs = [
        (BTC6_30, "#1f77b4", "-",  SCREWJACK_PARAMS),
        (BTC6_05, "#d62728", "-",  SCREWJACK_PARAMS),
        (BSP6_05, "#2ca02c", "--", {}),
        (BSL5_90, "#9467bd", "--", {}),
    ]

    ax.axhline(641, color="gray", lw=1.2, ls=":", label="Pipe body 641 kips")

    for conn, color, ls, extra in configs:
        r = compute_envelope(conn, n_points=300, **extra)
        tq = r.torques_ft_lbf / 1_000
        label_base = conn.name.split(" ")[0]
        ax.plot(tq, r.envelope_kips, color=color, lw=2, ls=ls,
                label=f"{label_base} — Envelope")

    ax.set_xlabel("Applied Torque [kft·lbf]", fontsize=12)
    ax.set_ylabel("Max Allowable Hook Load [kips]", fontsize=12)
    ax.set_title(
        "SPE-232499-MS — All Four Connections: Torque–Tension Envelopes\n"
        "5.5-in 20# P110",
        fontsize=12, fontweight="bold",
    )
    ax.set_ylim(0, 900)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.annotate(
        "BTC curves use placeholder ΔMU/ΔOT/LFArea — shapes are qualitative.",
        xy=(0.02, 0.02), xycoords="axes fraction", fontsize=8, color="dimgray",
    )

    plt.tight_layout()
    path = os.path.join(output_dir, "all_connections_comparison.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"Saved: {path}")
    plt.close()


def _print_summary(label: str, conn, result) -> None:
    """Print key envelope values to console."""
    tq_op = conn.operating_torque_ft_lbf
    print(f"\n{label}:")
    print(f"  BCCS curve @ Tq=0:      {result.bccs_curve_kips[0]:.1f} kips")
    print(f"  BCCS curve @ Tq_op:     {result.bccs_curve_kips[-1]:.1f} kips")
    print(f"  Pipe curve @ Tq_op:     {result.pipe_curve_kips[-1]:.1f} kips")
    print(f"  Envelope @ Tq_op:       {result.envelope_kips[-1]:.1f} kips")
    if result.f_tq_kips is not None:
        print(f"  F_TQ @ Tq_op:           {result.f_tq_kips[-1]:.1f} kips")
    print(f"  Pipe body reference:    {result.pipe_body_kips:.1f} kips")


if __name__ == "__main__":
    out_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(out_dir, exist_ok=True)

    print("=" * 60)
    print("SPE-232499-MS — Torque-Tension Envelope Plots")
    print("=" * 60)
    plot_fig12_btc(out_dir)
    plot_fig13_wedge(out_dir)
    plot_all_connections(out_dir)
    print("\nDone. Check examples/output/ for PNG files.")
