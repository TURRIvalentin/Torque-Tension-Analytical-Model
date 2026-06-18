"""OCTG Torque–Tension Interaction App — SPE-232499-MS.

SAFETY NOTICE: The BCCS curve uses placeholder parameters (BCR, STpin, LB, LFArea,
delta_MU, delta_OT) not given numerically in the paper. Results in BCCS-governed
zones are PRELIMINARY and must NOT be used for field decisions without validation
against manufacturer CDS and Fig. 11 torque-turn data.

The pipe body curve is reliable (anchored to API 5CT / Table 1 geometry).

Run locally:
    streamlit run octg_torque_tension/app/streamlit_app.py

Streamlit Community Cloud:
    Push repo root. Set main file to octg_torque_tension/app/streamlit_app.py.
    All dependencies in requirements.txt.

Architecture:
    All physics in octg_torque_tension/core/. Zero calculations in this file.
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import streamlit as st
from dataclasses import replace as dc_replace

from octg_torque_tension.core.connections import BTC6_30, BTC6_05, BSP6_05, BSL5_90, Connection
from octg_torque_tension.core.envelope import compute_envelope, check_operating_point, OperatingPoint, EnvelopeResult
from octg_torque_tension.core.geometry import bccs_area, polar_moment_annulus
from octg_torque_tension.core.materials import P110, N80, L80, Q125

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="OCTG Torque–Tension | SPE-232499-MS",
    page_icon="🔩",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Constants ─────────────────────────────────────────────────────────────────

_CATALOG: dict[str, Connection] = {
    "BTC6.30 — Standard Clearance (shouldered)": BTC6_30,
    "BTC6.05 — Enhanced Clearance (shouldered)": BTC6_05,
    "BSP6.05 — Bushmaster SP (wedge)":           BSP6_05,
    "BSL5.90 — Bushmaster SL (wedge)":           BSL5_90,
}

_COLORS = {"BTC6.30": "#1f77b4", "BTC6.05": "#d62728",
           "BSP6.05": "#2ca02c",  "BSL5.90": "#9467bd",  "Custom": "#7f7f7f"}

_GRADES = {"P110": P110, "N80": N80, "L80": L80, "Q125": Q125}

_PIPE_OD = 5.5    # in — fixed; all connections use 5.5-in 20# pipe body
_PIPE_ID = 4.778  # in — API 5CT (5.5-in, 20 lb/ft)


def _conn_color(name: str) -> str:
    for k, v in _COLORS.items():
        if k in name:
            return v
    return _COLORS["Custom"]


# ── Calibration logic ─────────────────────────────────────────────────────────

def _bccs_governs(op: OperatingPoint) -> bool:
    """True when BCCS curve (placeholder) sets the envelope at this operating point."""
    return op.bccs_applied_tension_kips < op.pipe_applied_tension_kips


def _has_placeholder_params(result: EnvelopeResult) -> bool:
    """BCR is always estimated → always True; screw-jack params add more uncertainty."""
    return True  # BCR is never confirmed from CDS in current implementation


# ── Sidebar ───────────────────────────────────────────────────────────────────

st.sidebar.title("🔩 OCTG Torque–Tension")
st.sidebar.caption("SPE-232499-MS — Ott et al. (2026)")
st.sidebar.divider()

# Connection selector
st.sidebar.subheader("Connection")
conn_choices = list(_CATALOG.keys()) + ["Custom"]
conn_label = st.sidebar.selectbox("Type", conn_choices, index=1)

if conn_label == "Custom":
    st.sidebar.markdown("**Custom connection geometry**")
    c_cod = st.sidebar.number_input("COD [in]", 5.0, 9.0, 6.30, 0.01, format="%.2f")
    c_tq  = st.sidebar.number_input("Operating Torque [ft·lbf]", 5000, 100000, 30600, 100)
    c_tens = st.sidebar.number_input("Tension Capacity [kips]", 100.0, 2000.0, 641.0, 10.0)
    c_type = st.sidebar.radio("Connection type", ["Shouldered (BTC)", "Wedge (BSP/BSL)"])
    c_grade = st.sidebar.selectbox("Steel Grade", list(_GRADES.keys()))
    base_conn = Connection(
        name="Custom",
        cod=c_cod,
        operating_torque_ft_lbf=float(c_tq),
        tension_capacity_kips=float(c_tens),
        clearance_in=0.0,
        has_screwjack=(c_type == "Shouldered (BTC)"),
        grade=_GRADES[c_grade],
        id_=_PIPE_ID,
    )
    default_bcr = c_cod - 1.0
else:
    base_conn = _CATALOG[conn_label]
    default_bcr = base_conn.bcr if base_conn.bcr is not None else (base_conn.cod - 1.0)

# Operating conditions
st.sidebar.subheader("Operating Conditions")
tq_max = int(base_conn.operating_torque_ft_lbf)
tq_applied = st.sidebar.slider("Applied Torque [ft·lbf]", 0, tq_max, int(tq_max * 0.8), 500)
hook_load  = st.sidebar.slider("Hook Load [kips]", 0, 800, 400, 10)

st.sidebar.subheader("Design Criteria")
design_factor = st.sidebar.number_input(
    "Design Factor", 1.0, 3.0, 1.4, 0.05, format="%.2f",
    help="Paper cites DF=1.4 for BTC6.30 (Liu 2021). Not confirmed for all connections."
)

# Geometric params expander
with st.sidebar.expander(
    "⚙️ Geometric Params — All PLACEHOLDER (confirm from CDS / API 5B)",
    expanded=base_conn.has_screwjack,
):
    st.caption(
        "These values are not given numerically in SPE-232499-MS. "
        "Adjust when manufacturer CDS data is available."
    )
    bcr_val = st.number_input(
        "BCR — Box Critical Root Diameter [in]",
        min_value=round(base_conn.id_ + 0.1, 3),
        max_value=round(base_conn.cod - 0.05, 3),
        value=float(default_bcr),
        step=0.005, format="%.3f",
        help="⚠️ PLACEHOLDER — estimated from paper's 44% area advantage statement. "
             "Confirm from Fermata Connections CDS.",
    )

    if base_conn.has_screwjack:
        st.markdown("**Screw-jack parameters (BTC only)** — all PLACEHOLDER")
        lf_area_val = st.number_input(
            "LFArea [in²]", 1.0, 300.0, 60.0, 5.0, format="%.1f",
            help="⚠️ PLACEHOLDER — estimated ~60 in² from API 5B buttress geometry. "
                 "TODO: compute from API 5B Table B.4."
        )
        delta_mu_val = st.number_input(
            "ΔMU — Make-up Delta Turns [rev]", 0.0, 5.0, 0.03, 0.01, format="%.3f",
            help="⚠️ PLACEHOLDER — from Fig. 11a (not given numerically)."
        )
        delta_ot_val = st.number_input(
            "ΔOT — Op. Delta Turns @ rated Tq [rev]", 0.0, 5.0, 0.15, 0.01, format="%.3f",
            help="⚠️ PLACEHOLDER — from Fig. 11b (not given numerically). "
                 "Linearly scaled for intermediate torques (ASSUMPTION — see MODEL_NOTES §6)."
        )
        l_b_val  = st.number_input("L_B — Coupling Length [in]", 2.0, 30.0, 13.0, 0.25, format="%.3f",
                                    help="⚠️ PLACEHOLDER — estimated from API 5CT.")
        st_pin_val = st.number_input("STpin — Pin Face OD [in]", round(base_conn.id_+0.1,3),
                                      round(base_conn.cod, 3), 5.5, 0.005, format="%.3f",
                                      help="⚠️ PLACEHOLDER — set to pipe OD as upper bound.")
        l_fl_val = st.number_input("LFL — Thread Lead [in/rev]", 0.05, 1.0, 0.200, 0.025, format="%.3f",
                                    help="⚠️ PLACEHOLDER — 5 TPI per API 5B. Confirm from API 5B Table B.4.")
    else:
        lf_area_val = delta_mu_val = delta_ot_val = l_b_val = st_pin_val = l_fl_val = None

# Patch connection object
patched_conn = dc_replace(base_conn, bcr=bcr_val, st_pin=st_pin_val, l_b=l_b_val, l_fl=l_fl_val)
sj_overrides: dict = {}
if base_conn.has_screwjack:
    sj_overrides = dict(lf_area_in2=lf_area_val, delta_mu=delta_mu_val, delta_ot=delta_ot_val)

# ── Compute ───────────────────────────────────────────────────────────────────

try:
    result = compute_envelope(patched_conn, design_factor=design_factor,
                               n_points=300, **sj_overrides)
except ValueError as e:
    st.error(f"Envelope error: {e}")
    st.stop()

try:
    op = check_operating_point(patched_conn, float(tq_applied), float(hook_load),
                                design_factor=design_factor, **sj_overrides)
except ValueError as e:
    st.error(f"Operating point error: {e}")
    st.stop()

bccs_gov = _bccs_governs(op)

# ── Title & calibration banner ────────────────────────────────────────────────

st.title("OCTG Torque–Tension Interaction")
st.markdown(
    f"**{conn_label}** &nbsp;|&nbsp; 5.5-in 20# P110 &nbsp;|&nbsp; "
    f"DF = {design_factor:.2f} &nbsp;|&nbsp; *SPE-232499-MS, Ott et al. (2026)*"
)

# Permanent calibration banner
st.error(
    "**⚠️ PARÁMETROS NO CALIBRADOS** — BCR, STpin, LB, LFArea, ΔMU, ΔOT son "
    "**PLACEHOLDER** (no dados numéricamente en el paper). "
    "La curva BCCS NO está validada contra datos CDS Fermata ni contra Fig. 11. "
    "**No usar para decisiones de campo hasta calibrar con datos reales.** "
    "Ver inventario de parámetros ↓",
    icon="🚨",
)

# ── KPI row ───────────────────────────────────────────────────────────────────

util_pct = op.utilization * 100

# Determine status considering calibration
if bccs_gov:
    # BCCS governs — assessment is preliminary regardless of safe/unsafe
    if op.safe:
        kpi_status = "⚠️ PRELIMINAR-SEGURO"
        kpi_color = "off"
        verdict_tag = "PRELIMINARY"
    else:
        kpi_status = "⚠️ PRELIMINAR-EXCEDIDO"
        kpi_color = "off"
        verdict_tag = "PRELIMINARY"
    governing_label = "BCCS — NO CALIBRADO"
else:
    # Pipe body governs — reliable assessment
    if op.utilization <= 0.8:
        kpi_status = "✅ SEGURO (pipe-limited)"
        kpi_color = "normal"
        verdict_tag = "RELIABLE"
    elif op.utilization <= 1.0:
        kpi_status = "⚠️ PRECAUCIÓN (pipe-limited)"
        kpi_color = "off"
        verdict_tag = "RELIABLE"
    else:
        kpi_status = "🚨 EXCEDIDO (pipe-limited)"
        kpi_color = "inverse"
        verdict_tag = "RELIABLE"
    governing_label = "Pipe body (CONFIABLE)"

c1, c2, c3, c4 = st.columns(4)
c1.metric("Estado", kpi_status)
c2.metric("Utilización", f"{util_pct:.1f}%", delta=f"{util_pct-100:.1f}% vs límite")
c3.metric("Allowable [kips]", f"{op.allowable_kips:.1f}", help="Envelope / DF")
c4.metric("Componente limitante", governing_label)

# Preliminary warning box when BCCS governs
if bccs_gov:
    st.warning(
        "**EVALUACIÓN PRELIMINAR — no usar para decisión de campo.** "
        f"El punto operativo ({tq_applied/1000:.1f} kft·lbf, {hook_load} kips) cae en la zona "
        "gobernada por la curva BCCS, que depende de parámetros placeholder no calibrados. "
        "El veredicto puede cambiar con BCR, ΔMU y ΔOT reales. "
        "La curva Pipe body (negra) sigue siendo confiable en esta zona.",
        icon="⚠️",
    )

st.divider()

# ── Plot + table ──────────────────────────────────────────────────────────────

col_plot, col_table = st.columns([3, 1])

with col_plot:
    st.subheader("Torque–Tension Envelope")
    color = _conn_color(base_conn.name)
    tq_x  = result.torques_ft_lbf / 1_000  # kft·lbf

    fig, ax = plt.subplots(figsize=(9, 5.5))

    # ── BCCS-governed zone: hatched background
    diff = result.bccs_curve_kips - result.pipe_curve_kips
    bccs_zone = diff < 0
    if bccs_zone.any():
        # Fill the region where BCCS < Pipe (preliminary zone)
        ax.fill_between(
            tq_x, result.bccs_curve_kips, result.pipe_curve_kips,
            where=bccs_zone, alpha=0.07, color="red", hatch="////",
            label="Zona BCCS-limitada (NO CALIBRADO)",
        )

    # ── Pipe body curve — RELIABLE
    ax.plot(tq_x, result.pipe_curve_kips, color="black", lw=2.0, ls="-",
            label=f"Pipe body — CONFIABLE (API 5CT, {result.pipe_body_kips:.0f} kips)")

    # ── BCCS curve — NOT CALIBRATED
    ax.plot(tq_x, result.bccs_curve_kips, color=color, lw=1.5, ls="--", alpha=0.85,
            label=f"BCCS — ⚠️ NO CALIBRADO (placeholder BCR, ΔMU, ΔOT)")

    # ── Envelope = min(BCCS, Pipe)
    ax.plot(tq_x, result.envelope_kips, color=color, lw=2.5, ls="-",
            label=f"Envelope = min(BCCS, Pipe) [DF={design_factor:.1f} para allowable]")
    ax.fill_between(tq_x, result.envelope_kips, alpha=0.08, color=color)

    # ── F_TQ component (optional)
    if result.has_screwjack and result.f_tq_kips is not None:
        ax.plot(tq_x, result.f_tq_kips, color=color, lw=0.9, ls="-.",
                alpha=0.5, label="F_TQ screw-jack [kips] — placeholder")

    # ── Operating point
    pt_colors = {"RELIABLE": {"safe": "#2ca02c", "caution": "#ff7f0e", "unsafe": "#d62728"},
                 "PRELIMINARY": {"safe": "#ff7f0e", "caution": "#ff7f0e", "unsafe": "#d62728"}}
    if verdict_tag == "RELIABLE":
        pt_c = pt_colors["RELIABLE"]["safe"] if op.utilization <= 0.8 else (
               pt_colors["RELIABLE"]["caution"] if op.utilization <= 1.0 else pt_colors["RELIABLE"]["unsafe"])
    else:
        pt_c = pt_colors["PRELIMINARY"]["caution"] if op.safe else pt_colors["PRELIMINARY"]["unsafe"]

    ax.scatter([tq_applied/1000], [hook_load], c=pt_c, s=140, zorder=6,
               edgecolors="black", lw=0.8, marker="*",
               label=f"Punto op. ({tq_applied/1000:.1f} kft·lbf, {hook_load} kips)")
    ax.annotate(
        f"  {hook_load} kips\n  Util: {util_pct:.1f}%\n  [{verdict_tag}]",
        xy=(tq_applied/1000, hook_load), fontsize=7.5, color=pt_c, fontweight="bold",
        va="bottom",
    )

    # ── Calibration watermark in BCCS zone
    if bccs_zone.any():
        mid_x = tq_x[bccs_zone].mean()
        mid_y = (result.bccs_curve_kips[bccs_zone].mean() +
                 result.pipe_curve_kips[bccs_zone].mean()) / 2
        ax.text(mid_x, mid_y, "NO CALIBRADO", ha="center", va="center",
                fontsize=7, color="red", alpha=0.4, rotation=10, fontweight="bold")

    ax.set_xlabel("Applied Torque [kft·lbf]", fontsize=11)
    ax.set_ylabel("Applied Tension [kips]", fontsize=11)
    ax.set_title(
        f"Torque–Tension Envelope — {base_conn.name}\n"
        f"(curva BCCS: placeholder params — validacion PENDIENTE)",
        fontsize=11, fontweight="bold",
    )
    ax.set_xlim(0, tq_max / 1000)
    ax.set_ylim(0, max(800, result.pipe_body_kips * 1.2))
    ax.legend(fontsize=7.5, loc="lower left", framealpha=0.9)
    ax.grid(True, alpha=0.25)
    ax.text(
        0.99, 0.99,
        "⚠️ RESULTADO PRELIMINAR\nPendiente calibracion con\ndatos CDS + Fig.11",
        transform=ax.transAxes, fontsize=7, ha="right", va="top",
        color="red", alpha=0.5,
        bbox=dict(boxstyle="round", fc="white", ec="red", alpha=0.5),
    )

    st.pyplot(fig, use_container_width=True)
    plt.close(fig)

# ── Results table ─────────────────────────────────────────────────────────────

with col_table:
    st.subheader("Valores Calculados")
    st.caption("(⚠️) = depende de parámetros placeholder")

    a_bccs = bccs_area(patched_conn.cod, bcr_val)
    j_bccs = polar_moment_annulus(patched_conn.cod, bcr_val)
    a_pipe = math.pi / 4 * (_PIPE_OD**2 - _PIPE_ID**2)
    # Axial stress: total axial force on BCCS = F_TQ + F_hook
    sigma_axial = (op.f_tq_kips + op.hook_load_kips) * 1_000 / a_bccs if a_bccs > 0 else 0
    tau_outer = (float(tq_applied) * 12 * (patched_conn.cod / 2) / j_bccs) if j_bccs > 0 else 0
    vm_stress = math.sqrt(sigma_axial**2 + 3 * tau_outer**2)

    rows = [
        ("A_BCCS [in²] (⚠️)",         f"{a_bccs:.3f}"),
        ("J_BCCS [in⁴] (⚠️)",         f"{j_bccs:.2f}"),
        ("A_pipe [in²] ✓",            f"{a_pipe:.3f}"),
        ("",                           ""),
        ("F_TQ Eq.6 [kips] (⚠️)",     f"{op.f_tq_kips:.1f}"),
        ("P_BTC Eq.8 BCCS (⚠️) [kips]", f"{op.p_btc_kips:.1f}"),
        ("P_total Eq.9 [kips] (⚠️)",  f"{op.p_total_kips:.1f}"),
        ("F_hook [kips] ✓",           f"{hook_load:.1f}"),
        ("",                           ""),
        ("BCCS curve (⚠️) [kips]",    f"{op.bccs_applied_tension_kips:.1f}"),
        ("Pipe curve ✓ [kips]",        f"{op.pipe_applied_tension_kips:.1f}"),
        ("Envelope [kips]",            f"{op.envelope_kips:.1f}"),
        ("Allowable [kips]",           f"{op.allowable_kips:.1f}"),
        ("Utilización",                f"{util_pct:.1f}%"),
        ("",                           ""),
        ("σ_axial [psi] (⚠️)",        f"{sigma_axial:,.0f}"),
        ("τ_outer [psi] (⚠️)",        f"{tau_outer:,.0f}"),
        ("σ_VM [psi] (⚠️)",           f"{vm_stress:,.0f}"),
        ("SMYS [psi] ✓",              f"{patched_conn.grade.smys:,.0f}"),
    ]

    for label, value in rows:
        if not label:
            st.write("")
            continue
        ca, cb = st.columns([1.7, 1])
        ca.caption(label)
        cb.markdown(f"**{value}**")

# ── Expanders ─────────────────────────────────────────────────────────────────

st.divider()

with st.expander("📋 Inventario de Parámetros — Placeholder vs Confirmado", expanded=True):
    st.markdown("### Parámetros del modelo")
    placeholder_rows = [
        ("BCR",     f"{bcr_val:.3f} in",    "⚠️ PLACEHOLDER",   "Estimado de '44% area advantage'. Confirmar de CDS Fermata."),
        ("STpin",   f"{st_pin_val or 5.5:.3f} in",  "⚠️ PLACEHOLDER",   "= OD caño (cota superior). Confirmar de CDS."),
        ("LB",      f"{l_b_val or 13.0:.3f} in",    "⚠️ PLACEHOLDER",   "Estimado de API 5CT Gr. B. Confirmar de CDS."),
        ("LFL",     "0.200 in/rev",         "⚠️ PLACEHOLDER",   "5 TPI BTC, pendiente confirmar API 5B Tabla B.4."),
        ("LFArea",  f"{lf_area_val or 60.0:.1f} in²", "⚠️ PLACEHOLDER", "Estimado de geometría API 5B. TODO precisar."),
        ("ΔMU",     f"{delta_mu_val or 0.03:.3f} rev", "⚠️ PLACEHOLDER", "No dado en paper. Elegido para reproducir cruce topológico Fig.12b."),
        ("ΔOT",     f"{delta_ot_val or 0.15:.3f} rev", "⚠️ PLACEHOLDER", "No dado en paper. Escala lineal con Tq (SUPOSICIÓN)."),
        ("ΔOT(Tq) ∝ Tq", "Lineal",         "⚠️ SUPOSICIÓN",    "No en el paper. Reemplazar con datos de Fig.11 torque-turn."),
    ]
    confirmed_rows = [
        ("OD caño",          "5.500 in",      "✓ CONFIRMADO", "API 5CT (5.5-in, 20 lb/ft)"),
        ("ID caño",          "4.778 in",      "✓ CONFIRMADO", "API 5CT (5.5-in, 20 lb/ft)"),
        ("fSMYS (P110)",     "110,000 psi",   "✓ CONFIRMADO", "API 5CT / API 5C3"),
        ("COD",              f"{base_conn.cod:.2f} in", "✓ CONFIRMADO", "Tabla 1, SPE-232499-MS"),
        ("Tq operacional",   f"{base_conn.operating_torque_ft_lbf:,.0f} ft·lbf", "✓ CONFIRMADO", "Tabla 1"),
        ("Tensión cap.",     f"{base_conn.tension_capacity_kips:.0f} kips", "✓ CONFIRMADO", "Tabla 1"),
        ("has_screwjack",    "BTC=Sí / Wedge=No", "✓ CONFIRMADO", "Tipo de conexión"),
        ("Coef. 0.096167",   "API RP 7G",     "✓ CONFIRMADO", "2/(12√3) — factor de unidades Von Mises"),
        ("Eq. 4–9",          "Formas algebraicas", "✓ CONFIRMADO", "Verificadas contra imágenes PDF del paper"),
    ]

    col_ph, col_cf = st.columns(2)
    with col_ph:
        st.markdown("**Parámetros PLACEHOLDER (no en el paper)**")
        for param, val, status, note in placeholder_rows:
            st.markdown(f"- **{param}** = `{val}` — *{note}*")
    with col_cf:
        st.markdown("**Parámetros CONFIRMADOS**")
        for param, val, status, note in confirmed_rows:
            st.markdown(f"- **{param}** = `{val}` ✓ — *{note}*")

    st.info(
        "**Criterio de calibración cruzada (MODEL_NOTES §6):** Cuando se disponga de "
        "datos CDS + Fig. 11, los dos síntomas deben corregirse JUNTOS: "
        "(1) cruce BTC6.05 en ~20 kft·lbf, y (2) BTC6.30 converge hacia la curva Pipe. "
        "Si solo se corrige uno, revisar el ensamble Eq. 6/8/9 y la estimación de BCR.",
        icon="ℹ️",
    )

with st.expander("📐 Especificaciones de Conexión — Tabla 1 SPE-232499-MS"):
    c1, c2, c3 = st.columns(3)
    c1.metric("COD", f"{base_conn.cod:.2f} in")
    c1.metric("BCR (est.)", f"{bcr_val:.3f} in", help="⚠️ Placeholder")
    c2.metric("Tq operacional", f"{base_conn.operating_torque_ft_lbf:,.0f} ft·lbf")
    c2.metric("Capacidad tensil", f"{base_conn.tension_capacity_kips:.0f} kips")
    c3.metric("Clearance radial", f"{base_conn.clearance_in:.3f} in")
    c3.metric("Screw-jack", "Sí (BTC)" if base_conn.has_screwjack else "No (Wedge)")

with st.expander("📖 Notas del Modelo y Limitaciones"):
    st.markdown("""
    **Modelo analítico — SPE-232499-MS, Ott et al. (2026)**

    | Ecuación | Descripción | Estado |
    |----------|-------------|--------|
    | Eq. 1 | L_OT = (ΔMU + ΔOT) × LFL | ✓ Paper |
    | Eq. 2 | A_BCCS = π/4 × (COD² − BCR²) | ✓ Paper |
    | Eq. 3 | FA_pin = π/4 × (STpin² − ID²) | ✓ Paper |
    | Eq. 4 | εR = A_BCCS / (A_BCCS + FA_pin + LFArea) | ✓ Confirmada |
    | Eq. 5 | δ = LOT × εR | ✓ Confirmada |
    | Eq. 6 | F_TQ = δ × E × A_BCCS / L_B | ✓ Confirmada |
    | Eq. 7 | Q_T = 0.096167 × (J/D) × √(Ym²−(P/A)²) [ft·lbf] | ✓ API RP 7G |
    | Eq. 8 | P_BTC = A × (fSMYS − √(fSMYS²−(Tq·D/(0.096167·J))²)) | ✓ Confirmada |
    | Eq. 9 | P_total = F_TQ + P_BTC | ✓ Confirmada |

    **Interpretación del eje Y (MODEL_NOTES §6 — HIPÓTESIS DERIVADA):**
    - Curva Pipe: A_pipe·fSMYS − P_BTC_pipe(Tq) — **confiable** (geometría API 5CT)
    - Curva BCCS: A_BCCS·fSMYS − P_total(Tq) — **NO calibrada** (BCR, ΔMU, ΔOT placeholder)
    - Envelope: min(BCCS, Pipe) — **confiable solo en zona Pipe-limitada**

    **Limitaciones:**
    - ΔOT ∝ Tq asumido lineal (no en el paper); reemplazar con datos de Fig. 11
    - Modelo elástico (Beer, 2015); inválido más allá del límite de fluencia
    - Design Factor 1.4 citado para BTC6.30 (Liu 2021); no confirmado para las 4 conexiones
    - Cruce BTC6.05 con placeholders ocurre a ~8.9 kft·lbf (paper muestra ~20 kft·lbf)
    """)

st.caption(
    "SPE-232499-MS — Ott, Del Castillo, Broussard (Fermata Connections, 2026) | "
    "Imperial: in, lbf, psi, ft·lbf | "
    "⚠️ NO VALIDADO para uso en campo — requiere calibración con datos CDS + Fig. 11"
)
