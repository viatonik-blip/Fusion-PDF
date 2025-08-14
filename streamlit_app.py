import io, time
import streamlit as st
from pypdf import PdfWriter, PdfReader
import streamlit_sortables as sortables

st.set_page_config(page_title="Fusion PDF", page_icon="📎")
st.title("📎 Fusionner des PDF")

# ===========
# Auth centre
# ===========
APP_PASSWORD = st.secrets.get("APP_PASSWORD", None)

# Flag de session: utilisateur déjà authentifié
if "authed" not in st.session_state:
    st.session_state.authed = False

def auth_view():
    # Mise en page centrée
    st.write("")  # petite marge
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown(
            """
            <div style="
                border:1px solid #eee; border-radius:12px;
                padding:20px 18px; background:#fff;">
                <h3 style="margin-top:0">🔐 Accès interne GED</h3>
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

# Si mot de passe défini, on affiche l'écran d'auth tant que non validé
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

# --- Liste des noms actuellement uploadés
names_now = [f.name for f in uploaded]

# --- Initialisation et gestion robuste de l'ordre (fonctionne même si on ajoute 1 par 1)
if "order_names" not in st.session_state:
    st.session_state.order_names = names_now[:]
    st.session_state._prev_names = names_now[:]
    st.session_state.sort_key = 0
elif set(names_now) != set(st.session_state._prev_names):
    kept = [n for n in st.session_state.order_names if n in names_now]
    new = [n for n in names_now if n not in st.session_state.order_names]
    st.session_state.order_names = kept + new
    st.session_state.sort_key += 1
    st.session_state._prev_names = names_now[:]

# --- Limite de taille totale
MAX_MB = 200
total_mb = sum(f.size for f in uploaded) / (1024 * 1024)
if total_mb > MAX_MB:
    st.error(f"Taille totale trop grande ({total_mb:.1f} MB > {MAX_MB} MB)")
    st.stop()

# --- Drag-and-drop
st.write("### 1) Réorganisez (glisser-déposer)")
ordered_names = sortables.sort_items(
    st.session_state.order_names,
    direction="vertical",
    key=f"sortable_list_{st.session_state.sort_key}"
)
st.session_state.order_names = ordered_names

# --- Aperçu numéroté
st.write("### 2) Aperçu de l’ordre")
for i, nm in enumerate(st.session_state.order_names, start=1):
    st.markdown(f"**{i}.** {nm}")

# --- Fusion
if st.button("🚀 Fusionner dans cet ordre"):
    name_to_bytes = {}
    for f in uploaded:
        raw = f.read()
        if not raw.startswith(b"%PDF-"):
            st.error(f"Non-PDF ou corrompu : {f.name}")
            st.stop()
        name_to_bytes[f.name] = raw

    writer = PdfWriter()
    for nm in st.session_state.order_names:
        reader = PdfReader(io.BytesIO(name_to_bytes[nm]))
        for page in reader.pages:
            writer.add_page(page)

    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    ts = int(time.time())
    st.success("Fusion réussie.")
    st.download_button(
        "⬇️ Télécharger le PDF fusionné",
        data=out,
        file_name=f"fusion_{ts}.pdf",
        mime="application/pdf"
    )
