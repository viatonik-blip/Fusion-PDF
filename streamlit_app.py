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

# ======
# HEADER
# ======
logo_path = "assets/logo_crf.png"  # Dépose ton logo ici (facultatif)
st.markdown('<div class="ribbon">USAGE INTERNE</div>', unsafe_allow_html=True)

with st.container():
    st.markdown('<div class="crf-header">', unsafe_allow_html=True)
    col1, col2 = st.columns([0.12, 0.88])
    with col1:
        if os.path.exists(logo_path):
            st.image(logo_path, use_container_width=False, output_format="PNG", caption=None)
        else:
            st.markdown(f'<div class="crf-logo" style="display:flex;align-items:center;justify-content:center;"><span style="color:{PRIMARY};font-weight:900;font-size:20px;">✚</span></div>', unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="crf-title">Croix-Rouge française — Outil de fusion PDF</div>', unsafe_allow_html=True)
        st.markdown('<div class="crf-sub">Fusionnez plusieurs PDF, réorganisez par glisser-déposer, téléchargez le document final. Aucune conservation de fichiers.</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ==========
# PARAMS/LIMS
# ==========
MAX_MB = int(os.getenv("CRF_MAX_UPLOAD_MB", "200"))

# =============
# UPLOAD / FORM
# =============
with st.container():
    st.markdown('<div class="crf-card">', unsafe_allow_html=True)
    uploaded = st.file_uploader(
        "Glissez vos PDF (2+). Puis réorganisez ci-dessous par glisser-déposer.",
        type=["pdf"],
        accept_multiple_files=True,
        help=f"Taille totale conseillée ≤ {MAX_MB} Mo",
    )
    st.markdown('</div>', unsafe_allow_html=True)

if not uploaded or len(uploaded) < 2:
    st.info("Ajoutez au moins 2 fichiers PDF pour commencer.")
    st.stop()

# Limite de taille totale
total_mb = sum(f.size for f in uploaded) / (1024 * 1024)
if total_mb > MAX_MB:
    st.error(f"Taille totale trop grande ({total_mb:.1f} Mo > {MAX_MB} Mo). Réduisez ou compressez vos fichiers.")
    st.stop()

# Initialisation ordre (persistance sur refresh)
names_now = [f.name for f in uploaded]
if "order_names" not in st.session_state or set(st.session_state.order_names) != set(names_now):
    st.session_state.order_names = names_now[:]

# ===================
# DRAG-AND-DROP ORDER
# ===================
st.markdown("### 1) Réorganisez les fichiers (glisser-déposer)")
ordered_names = sortables.sort_items(
    st.session_state.order_names,
    direction="vertical",
    key="sortable_list"
)
st.session_state.order_names = ordered_names

# Aperçu numéroté (clair + badges)
st.markdown("### 2) Aperçu de l’ordre")
for i, nm in enumerate(st.session_state.order_names, start=1):
    st.markdown(
        f'<div class="order-row"><span class="order-badge">{i}</span> <span class="order-name">{nm}</span></div>',
        unsafe_allow_html=True,
    )

# ==================
#  BANNIÈRE PRIVACY
# ==================
st.markdown(
    """
    <div class="privacy">
      <strong>Confidentialité :</strong> les fichiers sont traités en mémoire et ne sont pas stockés côté serveur.
      Aucun contenu n’est journalisé. Usage strictement interne.
    </div>
    """,
    unsafe_allow_html=True,
)

# ======
# FUSION
# ======
def is_pdf_bytes(b: bytes) -> bool:
    return b.startswith(b"%PDF-")

if st.button("🚀 Fusionner dans cet ordre", type="primary"):
    # Lecture & validation
    name_to_bytes = {}
    for f in uploaded:
        raw = f.read()
        if not is_pdf_bytes(raw[:5]):
            st.error(f"Non-PDF ou corrompu : {f.name}")
            st.stop()
        name_to_bytes[f.name] = raw

    # Fusion
    writer = PdfWriter()
    for nm in st.session_state.order_names:
        reader = PdfReader(io.BytesIO(name_to_bytes[nm]))
        for page in reader.pages:
            writer.add_page(page)

    out = io.BytesIO()
    writer.write(out); out.seek(0)
    ts = int(time.time())

    st.success("Fusion réussie.")
    st.download_button(
        "⬇️ Télécharger le PDF fusionné",
        data=out,
        file_name=f"CRF_fusion_{ts}.pdf",
        mime="application/pdf"
    )

    # Nettoyage mémoire
    del name_to_bytes, out, writer, reader
    gc.collect()
