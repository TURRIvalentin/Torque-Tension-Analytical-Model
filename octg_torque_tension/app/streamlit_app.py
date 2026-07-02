"""Torque-Tension Analytical Model.

Manual-entry tool: the user supplies their own connection geometry, pipe body
geometry, material grade, and torque-turn data. Results are only as good as
the inputs — this is an analytical model, not a certified engineering tool.

Run locally:
    streamlit run octg_torque_tension/app/streamlit_app.py

Streamlit Community Cloud:
    Push repo root. Set main file to octg_torque_tension/app/streamlit_app.py.
    All dependencies in requirements.txt.

Architecture:
    All physics in octg_torque_tension/core/. Zero calculations in this file
    beyond simple UI bookkeeping (default/example comparison, display labels).
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import streamlit as st

from octg_torque_tension.core.connections import Connection
from octg_torque_tension.core.envelope import compute_envelope, check_operating_point, OperatingPoint, EnvelopeResult
from octg_torque_tension.core.geometry import (
    bccs_area,
    pipe_id_from_wall,
    polar_moment_annulus,
    wall_from_nominal_weight,
)
from octg_torque_tension.core.materials import P110, N80, L80, Q125, SteelGrade

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Torque-Tension Analytical Model",
    page_icon="🔩",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Visual theme — light, corporate, no calculations touched below ────────────

_PRIMARY = "#2C5F7C"
_SURFACE = "#F0F2F5"
_TEXT = "#1A1A1A"
_GRID = "#E3E7EB"
_BORDER = "#D9DEE3"

plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.edgecolor": _BORDER,
    "axes.labelcolor": _TEXT,
    "text.color": _TEXT,
    "xtick.color": "#4A4A4A",
    "ytick.color": "#4A4A4A",
    "grid.color": _GRID,
    "font.family": "sans-serif",
    "legend.facecolor": "white",
    "legend.edgecolor": _BORDER,
})

st.markdown(
    f"""
    <style>
    html, body, [class^="css"], [class*=" css"] {{
        font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }}
    h1 {{ font-weight: 600 !important; }}
    h2, h3 {{ font-weight: 500 !important; }}

    /* Card containers — sidebar sections and main-area panels share the look */
    div[class*="st-key-card_"] {{
        background-color: {_SURFACE};
        border-radius: 10px;
        padding: 0.3rem 0.7rem 0.9rem 0.7rem;
        margin-bottom: 0.9rem;
    }}
    div[class*="st-key-card_"] [data-testid="stWidgetLabel"] p {{
        font-size: 0.82rem;
        color: #3A3A3A;
    }}
    .card-title {{
        font-weight: 500;
        font-size: 0.8rem;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: {_PRIMARY};
        border-bottom: 1px solid rgba(44, 95, 124, 0.25);
        padding: 0.5rem 0.1rem 0.4rem 0.1rem;
        margin-bottom: 0.6rem;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Constants ─────────────────────────────────────────────────────────────────

_GRADES: dict[str, SteelGrade] = {"P110": P110, "N80": N80, "L80": L80, "Q125": Q125}
_CONN_COLOR = _PRIMARY

# Example presets — used only for the optional "cargar ejemplo" button and to
# detect whether the user is still on out-of-the-box (uncalibrated) values.
# Sourced from MODEL_NOTES estimates (BTC6.30, BSP6.05).
_EXAMPLES = {
    "Buttress / Shouldered": dict(
        cod=6.300, bcr=5.385, st_pin=5.500, l_b=9.375, l_fl=0.200, lf_area=60.0,
        pipe_od=5.500, pipe_wall=0.361,
        delta_mu=0.030, delta_ot=0.150,
        tq_max=30_600.0, grade="P110",
    ),
    "Wedge": dict(
        cod=6.050, bcr=5.399, st_pin=5.500, l_b=9.375, l_fl=0.200, lf_area=60.0,
        pipe_od=5.500, pipe_wall=0.361,
        delta_mu=0.030, delta_ot=0.150,
        tq_max=39_800.0, grade="P110",
    ),
}

_KEYS = [
    "geo_cod", "geo_bcr", "geo_st_pin", "geo_l_b", "geo_l_fl", "geo_lf_area",
    "pipe_od", "pipe_wall", "dt_delta_mu", "dt_delta_ot",
    "tq_max", "mat_grade",
]


def _init_defaults(conn_type: str) -> None:
    ex = _EXAMPLES[conn_type]
    st.session_state["geo_cod"] = ex["cod"]
    st.session_state["geo_bcr"] = ex["bcr"]
    st.session_state["geo_st_pin"] = ex["st_pin"]
    st.session_state["geo_l_b"] = ex["l_b"]
    st.session_state["geo_l_fl"] = ex["l_fl"]
    st.session_state["geo_lf_area"] = ex["lf_area"]
    st.session_state["pipe_od"] = ex["pipe_od"]
    st.session_state["pipe_wall"] = ex["pipe_wall"]
    st.session_state["dt_delta_mu"] = ex["delta_mu"]
    st.session_state["dt_delta_ot"] = ex["delta_ot"]
    st.session_state["tq_max"] = ex["tq_max"]
    st.session_state["mat_grade"] = ex["grade"]
    st.session_state["pipe_spec_mode"] = "Wall thickness"


def sticky_number_input(label: str, key: str, fallback: float, container=None, **kwargs):
    """number_input that survives being conditionally un-rendered.

    Streamlit deletes a widget's session_state entry when the widget isn't
    instantiated on a run (e.g. screw-jack fields while Wedge is selected).
    Without this, switching Wedge -> Buttress would silently reset those
    fields to their min_value instead of the user's last entry. We cache the
    last value under a plain (non-widget) key and re-seed before remount.

    Args:
        container: where to render the widget (a column, or a container from a
            `with` block). Defaults to the ambient layout context (bare `st`),
            so calling this inside `with st.sidebar.container():` renders into
            that container automatically.
    """
    cache_key = f"_last_{key}"
    if key not in st.session_state:
        st.session_state[key] = st.session_state.get(cache_key, fallback)
    target = container if container is not None else st
    val = target.number_input(label, key=key, **kwargs)
    st.session_state[cache_key] = val
    return val


# ── Sidebar ───────────────────────────────────────────────────────────────────

st.sidebar.title("Torque-Tension Analytical Model")

# 1) Tipo de conexión — controla el screw-jack
with st.sidebar.container(border=True, key="card_conn_type"):
    st.markdown('<div class="card-title">1 · Connection Type</div>', unsafe_allow_html=True)
    conn_type = st.radio(
        "Type",
        ["Buttress / Shouldered", "Wedge"],
        key="conn_type",
    )
    has_screwjack = conn_type == "Buttress / Shouldered"

    if not any(k in st.session_state for k in _KEYS):
        _init_defaults(conn_type)

    if st.button("↺ Load Example Values"):
        _init_defaults(conn_type)
        st.rerun()

# 2) Geometría del pipe body — determina el OD/ID del caño
with st.sidebar.container(border=True, key="card_pipe_body"):
    st.markdown('<div class="card-title">2 · Pipe Body</div>', unsafe_allow_html=True)
    pipe_spec_mode = st.radio(
        "Specify by", ["Wall thickness", "Nominal weight [lb/ft]"],
        key="pipe_spec_mode", horizontal=True,
    )
    col_a, col_b = st.columns(2)
    pipe_od = col_a.number_input(
        "Pipe OD [in]", min_value=0.1, max_value=30.0, step=0.01, format="%.3f",
        key="pipe_od",
    )
    pipe_id_val = None
    pipe_id_error = None
    if pipe_spec_mode == "Wall thickness":
        pipe_wall = sticky_number_input(
            "Wall thickness [in]", "pipe_wall", _EXAMPLES[conn_type]["pipe_wall"],
            container=col_b,
            min_value=0.01, max_value=2.0, step=0.001, format="%.3f",
        )
        try:
            pipe_id_val = pipe_id_from_wall(pipe_od, pipe_wall)
        except ValueError as e:
            pipe_id_error = str(e)
    else:  # Nominal weight [lb/ft]
        pipe_weight = col_b.number_input(
            "Nominal weight [lb/ft]", min_value=1.0, max_value=200.0, step=0.5,
            format="%.1f", key="pipe_weight", value=20.0,
        )
        try:
            pipe_wall = wall_from_nominal_weight(pipe_od, pipe_weight)
            pipe_id_val = pipe_id_from_wall(pipe_od, pipe_wall)
        except ValueError as e:
            pipe_id_error = str(e)

if pipe_id_error:
    st.sidebar.error(f"Invalid pipe body geometry: {pipe_id_error}")
    st.error(f"Invalid pipe body geometry: {pipe_id_error}")
    st.stop()

# 3) Geometría de la conexión (BCCS / pin)
with st.sidebar.container(border=True, key="card_conn_geom"):
    st.markdown('<div class="card-title">3 · Connection Geometry</div>', unsafe_allow_html=True)
    col_a, col_b = st.columns(2)
    cod = col_a.number_input(
        "COD — Coupling OD [in]", min_value=0.1, max_value=30.0,
        step=0.01, format="%.3f", key="geo_cod",
    )
    bcr = col_b.number_input(
        "BCR — Box Critical Root Diameter [in]", min_value=0.1,
        max_value=30.0, step=0.005, format="%.3f", key="geo_bcr",
    )
    st_pin = st.number_input(
        "ST_pin — Pin Face OD [in]", min_value=0.1, max_value=30.0,
        step=0.005, format="%.3f", key="geo_st_pin",
    )

    if has_screwjack:
        st.markdown("**Screw-jack (Buttress)**")
        col_c, col_d = st.columns(2)
        l_b = sticky_number_input(
            "L_B — Coupling Length [in]", "geo_l_b", _EXAMPLES[conn_type]["l_b"],
            container=col_c,
            min_value=0.1, max_value=60.0, step=0.05, format="%.3f",
        )
        l_fl = sticky_number_input(
            "LFL — Thread Lead [in/rev]", "geo_l_fl", _EXAMPLES[conn_type]["l_fl"],
            container=col_d,
            min_value=0.01, max_value=2.0, step=0.005, format="%.3f",
        )
        lf_area_val = sticky_number_input(
            "LF_area — Load-Flank Area [in²]", "geo_lf_area", _EXAMPLES[conn_type]["lf_area"],
            min_value=0.1, max_value=500.0, step=1.0, format="%.1f",
        )
    else:
        l_b = l_fl = lf_area_val = None

try:
    j_btc_geom = polar_moment_annulus(cod, bcr)
except ValueError as e:
    st.sidebar.error(f"Invalid COD/BCR: {e}")
    st.error(f"Invalid geometry — COD/BCR: {e}")
    st.stop()

j_btc = j_btc_geom

# 4) Material
with st.sidebar.container(border=True, key="card_material"):
    st.markdown('<div class="card-title">4 · Material</div>', unsafe_allow_html=True)
    grade_choice = st.selectbox(
        "Steel grade", list(_GRADES.keys()) + ["Custom"], key="mat_grade",
    )
    if grade_choice == "Custom":
        col_a, col_b = st.columns(2)
        c_smys = col_a.number_input(
            "fSMYS [psi]", min_value=1000.0, max_value=300_000.0, value=110_000.0,
            step=1000.0, format="%.0f",
        )
        c_e = col_b.number_input(
            "E — Young's modulus [psi]", min_value=1_000_000.0, max_value=60_000_000.0,
            value=30_000_000.0, step=100_000.0, format="%.0f",
        )

if grade_choice == "Custom":
    try:
        grade = SteelGrade(name="Custom", smys=c_smys, E=c_e)
    except ValueError as e:
        st.sidebar.error(str(e))
        st.stop()
else:
    grade = _GRADES[grade_choice]

# 5) Delta turns — solo aplica a Buttress (screw-jack)
delta_mu_val = delta_ot_val = None
dt_mode = None
if has_screwjack:
    with st.sidebar.container(border=True, key="card_delta_turns"):
        st.markdown('<div class="card-title">5 · Delta Turns (Screw-Jack)</div>', unsafe_allow_html=True)
        dt_mode = st.radio(
            "Mode",
            ["Mode A — I have torque-turn data", "Mode B — Estimate from torque"],
            key="dt_mode",
        )
        if dt_mode.startswith("Mode A"):
            col_a, col_b = st.columns(2)
            delta_mu_val = sticky_number_input(
                "ΔMU — Make-up Delta Turns [rev]", "dt_delta_mu", _EXAMPLES[conn_type]["delta_mu"],
                container=col_a,
                min_value=0.0, max_value=5.0, step=0.005, format="%.3f",
            )
            delta_ot_val = sticky_number_input(
                "ΔOT — Operational Delta Turns @ Tq rated [rev]", "dt_delta_ot", _EXAMPLES[conn_type]["delta_ot"],
                container=col_b,
                min_value=0.0, max_value=5.0, step=0.005, format="%.3f",
            )
        else:
            # BANNER DESACTIVADO - reponer acá
            # st.warning(
            #     "⚠️ Delta turns estimados por suposición lineal no validada — modo aproximado.",
            #     icon="⚠️",
            # )
            delta_mu_val = st.session_state.get("_last_dt_delta_mu", _EXAMPLES[conn_type]["delta_mu"])
            delta_ot_val = st.session_state.get("_last_dt_delta_ot", _EXAMPLES[conn_type]["delta_ot"])
            st.caption(
                f"Uses ΔMU = {delta_mu_val:.3f} rev and ΔOT_rated = {delta_ot_val:.3f} rev "
                "(assumed constants, not measured) scaled linearly with the applied "
                "torque (Applied Torque / Maximum operating torque)."
            )
else:
    with st.sidebar.container(border=True, key="card_delta_turns"):
        st.markdown('<div class="card-title">5 · Delta Turns</div>', unsafe_allow_html=True)
        st.caption("Not applicable — Wedge connection, F_TQ = 0 by construction.")

# 6) Condiciones operativas
with st.sidebar.container(border=True, key="card_operating"):
    st.markdown('<div class="card-title">6 · Operating Conditions</div>', unsafe_allow_html=True)
    tq_max = st.number_input(
        "Maximum operating torque [ft·lbf]", min_value=100.0, max_value=200_000.0,
        step=100.0, format="%.0f", key="tq_max",
    )
    tq_applied = st.slider("Applied Torque [ft·lbf]", 0, int(tq_max), int(tq_max * 0.8), 100)
    hook_load = st.slider("Hook Load [kips]", 0, 1500, 400, 10)

# ── Build Connection ─────────────────────────────────────────────────────────

try:
    conn = Connection(
        name="Custom",
        cod=cod,
        operating_torque_ft_lbf=float(tq_max),
        tension_capacity_kips=1.0,  # not used by compute_envelope/check_operating_point
        clearance_in=0.0,
        has_screwjack=has_screwjack,
        grade=grade,
        id_=pipe_id_val,
        bcr=bcr,
        st_pin=st_pin,
        l_b=l_b,
        l_fl=l_fl,
        lf_area_in2=lf_area_val,
        delta_mu=delta_mu_val,
        delta_ot=delta_ot_val,
    )
except ValueError as e:
    st.error(f"Invalid geometry: {e}")
    st.stop()

sj_overrides: dict = {}
if has_screwjack:
    sj_overrides = dict(lf_area_in2=lf_area_val, delta_mu=delta_mu_val, delta_ot=delta_ot_val)

# ── Compute ───────────────────────────────────────────────────────────────────

try:
    result = compute_envelope(conn, n_points=300,
                               pipe_od=pipe_od, j_bccs=j_btc, **sj_overrides)
except ValueError as e:
    st.error(f"Envelope error: {e}")
    st.stop()

try:
    op = check_operating_point(conn, float(tq_applied), float(hook_load),
                                pipe_od=pipe_od,
                                j_bccs=j_btc, **sj_overrides)
except ValueError as e:
    st.error(f"Operating point error: {e}")
    st.stop()


def _bccs_governs(op: OperatingPoint) -> bool:
    return op.bccs_applied_tension_kips < op.pipe_applied_tension_kips


bccs_gov = _bccs_governs(op)

# ── Calibration state — "using defaults/example" or "Modo B estimation" ───────

_ex = _EXAMPLES[conn_type]
_cmp_pairs = [
    (cod, _ex["cod"]), (bcr, _ex["bcr"]), (st_pin, _ex["st_pin"]),
    (pipe_od, _ex["pipe_od"]), (pipe_wall, _ex["pipe_wall"]),
]
if has_screwjack:
    _cmp_pairs += [(l_b, _ex["l_b"]), (l_fl, _ex["l_fl"]), (lf_area_val, _ex["lf_area"])]
using_example_values = all(abs(a - b) < 1e-9 for a, b in _cmp_pairs)
estimating_delta_turns = has_screwjack and dt_mode is not None and dt_mode.startswith("Mode B")
uncalibrated = using_example_values or estimating_delta_turns

# ── Title ─────────────────────────────────────────────────────────────────────

st.title("Torque-Tension Analytical Model")

# BANNER DESACTIVADO - reponer acá
# Always-on general disclaimer (calm tone)
# st.info(
#     "Modelo analítico — **no es una herramienta certificada**. "
#     "Verificar contra datos CDS del fabricante y criterios de la operadora antes de "
#     "cualquier decisión de campo.",
#     icon="ℹ️",
# )

# BANNER DESACTIVADO - reponer acá
# Conditional prominent warning — only when using example/default values or Modo B
# Lógica conservada (reasons se sigue calculando) — solo se suprime el render.
if uncalibrated:
    reasons = []
    if using_example_values:
        reasons.append("the geometry still matches the **example values** (no user data loaded)")
    if estimating_delta_turns:
        reasons.append("the **delta turns are estimated** by linear assumption (Mode B), not measured")
    # st.warning(
    #     "**⚠️ RESULTADO PRELIMINAR** — " + "; y ".join(reasons) + ". "
    #     "No usar para decisiones de campo hasta reemplazar por datos reales.",
    #     icon="⚠️",
    # )

# ── KPI row ───────────────────────────────────────────────────────────────────

util_pct = op.utilization * 100

if uncalibrated:
    if op.safe:
        kpi_status, kpi_verdict = "⚠️ PRELIMINARY-SAFE", "PRELIMINARY"
    else:
        kpi_status, kpi_verdict = "⚠️ PRELIMINARY-EXCEEDED", "PRELIMINARY"
    governing_label = "BCCS" if bccs_gov else "Pipe body"
    governing_label += " — example/estimated"
else:
    if op.utilization <= 0.8:
        kpi_status, kpi_verdict = "✅ SAFE", "RELIABLE"
    elif op.utilization <= 1.0:
        kpi_status, kpi_verdict = "⚠️ CAUTION", "RELIABLE"
    else:
        kpi_status, kpi_verdict = "🚨 EXCEEDED", "RELIABLE"
    governing_label = "BCCS (connection)" if bccs_gov else "Pipe body"

# KPI DESACTIVADO - reponer acá
# c1, c2, c3, c4 = st.columns(4)
# c1.metric("Estado", kpi_status)
# c2.metric("Utilización", f"{util_pct:.1f}%", delta=f"{util_pct-100:.1f}% vs límite")
# c3.metric("Allowable [kips]", f"{op.allowable_kips:.1f}", help="Capacidad nominal del envelope")
# c4.metric("Componente limitante", governing_label)

st.divider()

# ── Plot + table ──────────────────────────────────────────────────────────────

col_plot, col_table = st.columns([3, 1])

with col_plot:
    with st.container(border=True, key="card_plot"):
        st.markdown('<div class="card-title">Torque–Tension Envelope</div>', unsafe_allow_html=True)
        tq_x = result.torques_ft_lbf / 1_000  # kft·lbf

        fig, ax = plt.subplots(figsize=(9, 5.5))
        fig.patch.set_facecolor("white")
        ax.set_facecolor("white")

        diff = result.bccs_curve_kips - result.pipe_curve_kips
        bccs_zone = diff < 0
        if bccs_zone.any() and uncalibrated:
            ax.fill_between(
                tq_x, result.bccs_curve_kips, result.pipe_curve_kips,
                where=bccs_zone, alpha=0.07, color="red", hatch="////",
                label="BCCS-limited zone (preliminary)",
            )

        # CURVA OCULTA - reponer acá
        # ax.plot(tq_x, result.pipe_curve_kips, color="black", lw=2.0, ls="-",
        #         label=f"Pipe body ({result.pipe_body_kips:.0f} kips)")

        bccs_label = "BCCS" + (" — ⚠️ example/estimated" if uncalibrated else "")
        # CURVA OCULTA - reponer acá
        # ax.plot(tq_x, result.bccs_curve_kips, color=_CONN_COLOR, lw=1.5, ls="--", alpha=0.85,
        #         label=bccs_label)

        ax.plot(tq_x, result.envelope_kips, color=_CONN_COLOR, lw=2.5, ls="-",
                label="Envelope")
        ax.fill_between(tq_x, result.envelope_kips, alpha=0.08, color=_CONN_COLOR)

        if result.has_screwjack and result.f_tq_kips is not None:
            pass
            # CURVA OCULTA - reponer acá
            # ax.plot(tq_x, result.f_tq_kips, color=_CONN_COLOR, lw=0.9, ls="-.",
            #         alpha=0.5, label="F_TQ screw-jack [kips]")

        if kpi_verdict == "RELIABLE":
            pt_c = "#2ca02c" if op.utilization <= 0.8 else ("#ff7f0e" if op.utilization <= 1.0 else "#d62728")
        else:
            pt_c = "#ff7f0e" if op.safe else "#d62728"

        ax.scatter([tq_applied / 1000], [hook_load], c=pt_c, s=140, zorder=6,
                   edgecolors="black", lw=0.8, marker="*",
                   label=f"Operating point ({tq_applied/1000:.1f} kft·lbf, {hook_load} kips)")
        ax.annotate(
            f"  {hook_load} kips\n  Util: {util_pct:.1f}%",
            xy=(tq_applied / 1000, hook_load), fontsize=7.5, color=pt_c, fontweight="bold",
            va="bottom",
        )

        if uncalibrated and bccs_zone.any():
            mid_x = tq_x[bccs_zone].mean()
            mid_y = (result.bccs_curve_kips[bccs_zone].mean() + result.pipe_curve_kips[bccs_zone].mean()) / 2
            ax.text(mid_x, mid_y, "EXAMPLE / ESTIMATED", ha="center", va="center",
                    fontsize=7, color="red", alpha=0.4, rotation=10, fontweight="bold")

        ax.set_xlabel("Applied Torque [kft·lbf]", fontsize=11)
        ax.set_ylabel("Applied Tension [kips]", fontsize=11)
        ax.set_title("Torque–Tension Envelope", fontsize=11, fontweight="bold")
        ax.set_xlim(0, tq_max / 1000)
        y_top = max(800.0, result.pipe_body_kips * 1.2, result.bccs_curve_kips.max() * 1.1, hook_load * 1.15)
        ax.set_ylim(0, y_top)
        ax.legend(fontsize=7.5, loc="lower left", framealpha=0.9)
        ax.grid(True, color=_GRID, alpha=0.8, linewidth=0.7)
        for spine in ax.spines.values():
            spine.set_color(_BORDER)

        # BANNER DESACTIVADO - reponer acá
        # if uncalibrated:
        #     ax.text(
        #         0.99, 0.99, "⚠️ RESULTADO PRELIMINAR\nGeometría de ejemplo o\ndelta turns estimados",
        #         transform=ax.transAxes, fontsize=7, ha="right", va="top",
        #         color="red", alpha=0.5,
        #         bbox=dict(boxstyle="round", fc="white", ec="red", alpha=0.5),
        #     )

        st.pyplot(fig, use_container_width=True)
        plt.close(fig)

# ── Results table ─────────────────────────────────────────────────────────────

with col_table:
    with st.container(border=True, key="card_table"):
        st.markdown('<div class="card-title">Calculated Values</div>', unsafe_allow_html=True)

        a_bccs = bccs_area(conn.cod, bcr)
        j_bccs = j_btc
        a_pipe = math.pi / 4 * (pipe_od**2 - pipe_id_val**2)
        sigma_axial = (op.f_tq_kips + op.hook_load_kips) * 1_000 / a_bccs if a_bccs > 0 else 0
        tau_outer = (float(tq_applied) * 12 * (conn.cod / 2) / j_bccs) if j_bccs > 0 else 0
        vm_stress = math.sqrt(sigma_axial**2 + 3 * tau_outer**2)

        rows = [
            ("A_BCCS [in²]", f"{a_bccs:.3f}"),
            ("J_BCCS [in⁴]", f"{j_bccs:.2f}"),
            ("A_pipe [in²]", f"{a_pipe:.3f}"),
            ("", ""),
            ("F_TQ Eq.6 [kips]", f"{op.f_tq_kips:.1f}"),
            ("P_BTC Eq.8 BCCS [kips]", f"{op.p_btc_kips:.1f}"),
            ("P_total Eq.9 [kips]", f"{op.p_total_kips:.1f}"),
            ("F_hook [kips]", f"{hook_load:.1f}"),
            ("", ""),
            ("BCCS curve [kips]", f"{op.bccs_applied_tension_kips:.1f}"),
            ("Pipe curve [kips]", f"{op.pipe_applied_tension_kips:.1f}"),
            ("Envelope [kips]", f"{op.envelope_kips:.1f}"),
            ("Allowable [kips]", f"{op.allowable_kips:.1f}"),
            ("Utilization", f"{util_pct:.1f}%"),
            ("", ""),
            ("σ_axial [psi]", f"{sigma_axial:,.0f}"),
            ("τ_outer [psi]", f"{tau_outer:,.0f}"),
            ("σ_VM [psi]", f"{vm_stress:,.0f}"),
            ("SMYS [psi]", f"{grade.smys:,.0f}"),
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

with st.expander("📖 Glossary of Acronyms and Symbols"):
    st.markdown("""
    **Glossary of Acronyms and Symbols**

    *Connection / geometry*
    - **OCTG** — Oil Country Tubular Goods: the well tubulars (casing, tubing). The product family this connection belongs to.
    - **BTC** — Buttress Thread and Coupling: the buttress thread with coupling, the API 5B standard.
    - **Box** — the female component of the connection (the coupling). **Pin** — the male component (the threaded end of the pipe).
    - **BCCS** — Box Critical Cross Section: the critical cross-section of the coupling where the last engaged pin thread meets the box thread. First point to fail under tension.
    - **COD** — Coupling Outer Diameter: outer diameter of the coupling.
    - **BCR** — Box Critical Root diameter: diameter at the root of the box thread at the critical section.
    - **ST_pin** — outer diameter of the pin's contact face.
    - **ID** — Inner Diameter: inner diameter of the pipe.
    - **L_B** — coupling length.
    - **L_FL** — thread lead: the axial advance of the thread per full turn.
    - **LF_area** — Load Flank area: active area of the thread's load flanks.

    *Loads and displacements*
    - **Δ_MU** — make-up delta turns: turns past the shoulder point during make-up at the shop/rig floor (initial preload).
    - **Δ_OT** — operating delta turns: additional turns imposed by the top drive when rotating the string downhole.
    - **L_OT** — total axial displacement induced by torque.
    - **δ** — effective elastic displacement that actually stretches the BCCS.
    - **ε_R** — relative strain fraction: fraction of the displacement that goes to the BCCS.
    - **F_TQ** — axial load (tension) that torque induces via the screw-jack mechanism.
    - **T_q** — applied torque.

    *Material and strength*
    - **E** — Young's modulus of the steel (elastic stiffness).
    - **fSMYS / Y_m** — Specified Minimum Yield Strength: the steel's specified minimum yield strength.
    - **J** — polar moment of inertia of the cross-section (torsional resistance).
    - **Q_T** — torsional yield under tension (from API RP 7G).
    - **P_BTC** — tensile capacity of the BCCS consumed by torsional shear.
    - **P_total** — total capacity of the BCCS consumed by torque.
    - **API RP 7G** — the API recommended practice that provides the torsion-under-tension formula.
    """)
