import io, time, os, gc
import streamlit as st
from pypdf import PdfWriter, PdfReader
import streamlit_sortables as sortables

# ==========
# CONFIG PAGE
# ==========
st.set_page_config(
    page_title="CRF • Fusion de PDF",
    page_icon="✚",  # ou "➕" / "🚑"
    layout="centered",
)


# ======
# STYLES
# ======
PRIMARY = "#E2001A"  # Rouge CRF (approx.)
ACCENT = "#B80010"
SOFT_BG = "#FFF5F5"

st.markdown(
    f"""
    <style>
    /* Police & couleurs globales */
    :root {{
      --primary: {PRIMARY};
      --accent: {ACCENT};
      --soft-bg: {SOFT_BG};
    }}
    .stApp {{
      background: #ffffff;
    }}

    /* Bandeau header */
    .crf-header {{
      display:flex; align-items:center; gap:16px;
      padding: 14px 18px; margin: -1rem -1rem 1rem -1rem;
      border-bottom: 1px solid #eee;
      background: linear-gradient(90deg, #fff 0%, #fff 60%, var(--soft-bg) 100%);
    }}
    .crf-logo {{
      width: 38px; height: 38px; border-radius: 8px; object-fit: contain;
      border: 1px solid #eee; background: #fff;
    }}
    .crf-title {{
      font-weight: 700; font-size: 1.15rem; line-height: 1.2;
    }}
    .crf-sub {{
      color: #555; font-size: 0.92rem;
    }}

    /* Cartes */
    .crf-card {{
      border: 1px solid #eee; border-radius: 14px; padding: 16px 16px;
      background: #fff;
      box-shadow: 0 1px 0 rgba(0,0,0,0.03);
    }}

    /* Uploader : halo rouge léger */
    div[data-testid="stFileUploader"] > div {{
      border-radius: 12px !important;
      border: 1px dashed var(--primary) !important;
      background: var(--soft-bg);
    }}

    /* Boutons */
    button[kind="primary"] {{
      background-color: var(--primary) !important;
      color: #fff !important;
      border: 0 !important;
    }}
    button[kind="primary"]:hover {{
      background-color: var(--accent) !important;
    }}

    /* Badges numérotés (aperçu d'ordre) */
    .order-row {{
      display:flex; align-items:center; gap:10px; padding:8px 10px;
      border-radius: 10px; border: 1px solid #eee; margin-bottom: 6px;
      background: #fff;
    }}
    .order-badge {{
      width: 26px; height: 26px; border-radius: 9999px;
      display:inline-flex; align-items:center; justify-content:center;
      font-weight: 700; color: #fff; background: var(--primary);
      border: 1px solid #d0d0d0;
    }}
    .order-name {{
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }}

    /* Bandeau confidentialité */
    .privacy {{
      margin-top: 6px; padding: 10px 12px; border-radius: 12px;
      border: 1px solid #eee; background: #fafafa; font-size: 0.9rem;
    }}

    /* Ruban "usage interne" */
    .ribbon {{
      position: fixed; top: 12px; right: -50px; transform: rotate(45deg);
      background: var(--primary); color:#fff; padding: 6px 60px;
      font-weight: 700; box-shadow: 0 2px 8px rgba(0,0,0,.1);
      z-index: 9999; letter-spacing: 0.5px;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# =====
