import io, time, os
import streamlit as st
from pypdf import PdfWriter, PdfReader

# Essayez d'importer le composant drag-and-drop
try:
    import streamlit_sortables as sortables
    HAS_SORT = True
except Exception:
    HAS_SORT = False

st.set_page_config(page_title="Fusion PDF", page_icon="📎")
st.title("📎 Fusionner des PDF")

# ===========
# Auth au centre
# ===========
APP_PASSWORD = st.secrets.get("APP_PASSWORD", None)

if "authed" not in st.session_state:
    st.session_state.authed = False

def auth_view():
    st.write("")  # marge
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown(
            """
            <div style="
                border:1px solid #eee; border-radius:12px;
                padding:20px 18px; background:#fff;">
                <h3 style="margin-top:0">🔐 Accès interne</h3>
                <p style="margin-bottom:10px;color:#666">
                    Saisissez le mot de passe pour accéder à l’outil.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("auth_form", clear_on_submit=False):
            pw = st.text_input("Mot de passe", type="password", placeholder="Votre mot de passe")
            submitted = st.form_submit_button("Valider")
            if submitted:
                if pw == APP_PASSWORD:
                    st.session_state.authed = True
                else:
                    st.error("Mot de passe incorrect.")

if APP_PASSWORD and not st.session_state.authed:
    auth_view()
    st.stop()

# =========================
# App (une fois authentifié)
# =========================

uploaded = st.file_uploader(
    "Glissez vos PDF (2+). Réorganisez ensuite par glisser-déposer.",
    type=["pdf"],
    accept_multiple_files=True
)

if not uploaded or len(uploaded) < 2:
    st.info("Ajoutez au moins 2 fichiers PDF pour commencer.")
    st.stop()

# --- Construire des noms "affichés" uniques (gère les doublons: nom.pdf (2), nom.pdf (3), ...)
raw_names = [f.name for f in uploaded]
names_now, counts = [], {}
for n in raw_names:
    counts[n] = counts.get(n, 0) + 1
    names_now.append(n if counts[n] == 1 else f"{n} ({counts[n]})")

# --- Initialisation & gestion robuste de l'ordre (OK même si ajout 1 par 1)
if "order_names" not in st.session_state:
    st.session_state.order_names = names_now[:]
    st.session_state._prev_names = names_now[:]
    st.session_state.sort_key = 0
elif set(names_now) != set(st.session_state._prev_names):
    kept = [n for n in st.session_state.order_names if n in names_now]
    new = [n for n in names_now if n not in st.session_state.order_names]
    st.session_state.order_names = kept + new
    st.session_state.sort_key += 1     # force un re-render du composant
    st.session_state._prev_names = names_now[:]

# --- Limite de taille totale
MAX_MB = int(os.getenv("CRF_MAX_UPLOAD_MB", "200"))
total_mb = sum(f.size for f in uploaded) / (1024 * 1024)
if total_mb > MAX_MB:
    st.error(f"Taille totale trop grande ({total_mb:.1f} MB > {MAX_MB} MB)")
    st.stop()

# --- Drag-and-drop (ou fallback)
st.write("### 1) Réorganisez (glisser-déposer)")
if HAS_SORT:
    ordered_names = sortables.sort_items(
        st.session_state.order_names,
        direction="vertical",
        key=f"sortable_list_{st.session_state.sort_key}"
    )
    st.session_state.order_names = ordered_names
else:
    st.info("Drag-and-drop non disponible (module manquant). Fallback ci-dessous.")
    order = st.multiselect(
        "Cliquez les fichiers dans l'ordre souhaité",
        options=st.session_state.order_names,
        default=st.session_state.order_names
    )
    if len(order) == len(st.session_state.order_names):
        st.session_state.order_names = order

# --- Aperçu numéroté
st.write("### 2) Aperçu de l’ordre")
for i, nm in enumerate(st.session_state.order_names, start=1):
    st.markdown(f"**{i}.** {nm}")

# --- Nom du fichier de sortie
st.write("### 3) Nom du fichier de sortie")
default_name = f"fusion_{time.strftime('%Y-%m-%d_%H-%M-%S')}.pdf"
file_name = st.text_input("Nom du fichier", value=default_name)

# --- Fusion
if st.button("🚀 Fusionner dans cet ordre"):
    # Recrée le mapping display_name -> bytes en suivant la même logique de dédoublonnage
    display_to_bytes = {}
    counts2 = {}
    for f in uploaded:
        raw = f.read()
        if not raw.startswith(b"%PDF-"):
            st.error(f"Non-PDF ou corrompu : {f.name}")
            st.stop()

        n = f.name
        counts2[n] = counts2.get(n, 0) + 1
        display = n if counts2[n] == 1 else f"{n} ({counts2[n]})"
        display_to_bytes[display] = raw

    writer = PdfWriter()
    for display_name in st.session_state.order_names:
        reader = PdfReader(io.BytesIO(display_to_bytes[display_name]))
        for page in reader.pages:
            writer.add_page(page)

    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    st.success("Fusion réussie.")
    safe_name = file_name if file_name.lower().endswith(".pdf") else f"{file_name}.pdf"
    st.download_button(
        "⬇️ Télécharger le PDF fusionné",
        data=out,
        file_name=safe_name,
        mime="application/pdf"
    )

# --- EASTER EGG VISUEL (petit cœur à cliquer) ---
if "ee_clicks" not in st.session_state:
    st.session_state.ee_clicks = 0
if "ee_shown" not in st.session_state:
    st.session_state.ee_shown = False

st.markdown("<hr style='opacity:.2;'>", unsafe_allow_html=True)
c1, c2, c3 = st.columns([1,1,1])
with c2:
    st.markdown(
        "<div style='text-align:center; color:#999; font-size:12px;'",
        unsafe_allow_html=True
    )
    if st.button("❤️", help="Cliquez…"):
        st.session_state.ee_clicks += 1
        if st.session_state.ee_clicks >= 7:
            st.session_state.ee_shown = True

if st.session_state.ee_shown:
    st.balloons()
    st.markdown(
        "<div style='text-align:center; margin-top:6px; font-size:12px; color:#888;'>jtm bab</div>",
        unsafe_allow_html=True
    )
