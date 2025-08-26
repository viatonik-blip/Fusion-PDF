import io, time, os, re
import streamlit as st
from pypdf import PdfWriter, PdfReader

# Essayez d'importer le composant drag-and-drop
try:
    import streamlit_sortables as sortables
    HAS_SORT = True
except Exception:
    HAS_SORT = False

st.set_page_config(page_title="Fusion PDF / Merge PDF", page_icon="📎")
st.title("📎 Fusionner des documents / Merge documents")

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
                <h3 style="margin-top:0">🔐 Accès interne / Internal access </h3>
                <p style="margin-bottom:10px;color:#666">
                    Saisissez le mot de passe pour accéder à l’outil. / Enter the password to access the tool.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("auth_form", clear_on_submit=False):
            pw = st.text_input("Mot de passe / Password", type="password", placeholder="Votre mot de passe / Your password")
            submitted = st.form_submit_button("Valider / Validate")
            if submitted:
                if pw == APP_PASSWORD:
                    st.session_state.authed = True
                else:
                    st.error("Mot de passe incorrect./ Wrong password.")

if APP_PASSWORD and not st.session_state.authed:
    auth_view()
    st.stop()

# =========================
# App (une fois authentifié)
# =========================

uploaded = st.file_uploader(
    "Glissez vos PDF (2+). Réorganisez ensuite par glisser-déposer. / Drag and drop your PDFs (2+). Then rearrange them using drag and drop.",
    type=["pdf"],
    accept_multiple_files=True
)

if not uploaded or len(uploaded) < 2:
    st.info("Ajoutez au moins 2 fichiers PDF pour commencer. / Add at least 2 PDF files to get started.")
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
st.write("### 1) Réorganisez (glisser-déposer) / Reorder (drag and drop) ")
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
st.write("### 2) Aperçu de l’ordre / Order overview ")
for i, nm in enumerate(st.session_state.order_names, start=1):
    st.markdown(f"**{i}.** {nm}")

# --- Nom du fichier de sortie (persistant)
def default_out_name():
    return f"fusion_{time.strftime('%Y-%m-%d_%H-%M-%S')}"

if "out_name" not in st.session_state:
    st.session_state.out_name = default_out_name()

st.write("### 3) Nom du fichier de sortie / Output file name ")
st.session_state.out_name = st.text_input("Nom du fichier (sans extension ou .pdf) / File name (without extension or .pdf)", value=st.session_state.out_name, key="out_name_input")

def sanitize_filename(name: str) -> str:
    name = name.strip()
    # retirer caractères non valides pour noms de fichiers (Windows/Linux/Mac)
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    # éviter nom vide
    if not name:
        name = default_out_name()
    # forcer extension .pdf
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name

# --- Fusion
if st.button("🚀 Fusionner dans cet ordre / Merge in this order"):
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

    final_name = sanitize_filename(st.session_state.out_name)
    st.success(f"Fusion réussie. Fichier prêt / Succes. The file is ready : {final_name}")
    st.download_button(
        "⬇️ Télécharger le PDF fusionné / Download the merged PDF",
        data=out,
        file_name=final_name,
        mime="application/pdf"
    )
