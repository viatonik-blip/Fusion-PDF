# streamlit_app.py
import io, time, os, re
import streamlit as st
from pypdf import PdfWriter, PdfReader
from pypdf.errors import PdfReadError
from pypdf.generic import NameObject, BooleanObject, DictionaryObject

# ========= Composant drag-and-drop (optionnel) =========
try:
    import streamlit_sortables as sortables
    HAS_SORT = True
except Exception:
    HAS_SORT = False

# Détection de l'API append (pypdf >= 5 expose PdfWriter.append)
WRITER_HAS_APPEND = hasattr(PdfWriter, "append")

# ========= Page / Titre =========
st.set_page_config(page_title="Fusion PDF / Merge PDF", page_icon="📎")
st.title("📎 Fusionner des documents / Merge documents")

# ========= Auth centrée (optionnelle via secrets) =========
APP_PASSWORD = st.secrets.get("APP_PASSWORD", None)
if "authed" not in st.session_state:
    st.session_state.authed = False

def auth_view():
    st.write("")  # marge
    _, c2, _ = st.columns([1, 2, 1])
    with c2:
        st.markdown(
            """
            <div style="
                border:1px solid #eee; border-radius:12px;
                padding:20px 18px; background:#fff;">
                <h3 style="margin-top:0">🔐 Accès interne / Internal access</h3>
                <p style="margin-bottom:10px;color:#666">
                    Saisissez le mot de passe pour accéder à l’outil. / Enter the password to access the tool.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("auth_form", clear_on_submit=False):
            pw = st.text_input("Mot de passe / Password", type="password",
                               placeholder="Votre mot de passe / Your password")
            submitted = st.form_submit_button("Valider / Validate")
            if submitted:
                if pw == APP_PASSWORD:
                    st.session_state.authed = True
                else:
                    st.error("Mot de passe incorrect. / Wrong password.")

if APP_PASSWORD and not st.session_state.authed:
    auth_view()
    st.stop()

# ========= Uploader =========
uploaded = st.file_uploader(
    "Glissez vos PDF (2+). Réorganisez ensuite par glisser-déposer. / "
    "Drag and drop your PDFs (2+). Then rearrange them using drag and drop.",
    type=["pdf"],
    accept_multiple_files=True
)

if not uploaded or len(uploaded) < 2:
    st.info("Ajoutez au moins 2 fichiers PDF pour commencer. / Add at least 2 PDF files to get started.")
    st.stop()

# ========= Noms affichés uniques (gère doublons : nom.pdf (2), etc.) =========
raw_names = [f.name for f in uploaded]
names_now, counts = [], {}
for n in raw_names:
    counts[n] = counts.get(n, 0) + 1
    names_now.append(n if counts[n] == 1 else f"{n} ({counts[n]})")

# ========= Gestion robuste de l’ordre (OK même ajout 1 par 1) =========
if "order_names" not in st.session_state:
    st.session_state.order_names = names_now[:]
    st.session_state._prev_names = names_now[:]
    st.session_state.sort_key = 0
elif set(names_now) != set(st.session_state._prev_names):
    kept = [n for n in st.session_state.order_names if n in names_now]
    new = [n for n in names_now if n not in st.session_state.order_names]
    st.session_state.order_names = kept + new
    st.session_state.sort_key += 1  # force re-render du composant sortable
    st.session_state._prev_names = names_now[:]

# ========= Limites (upload & pages) =========
MAX_MB = int(os.getenv("CRF_MAX_UPLOAD_MB", "200"))
MAX_PAGES = int(os.getenv("CRF_MAX_PAGES", "2000"))

total_mb = sum(getattr(f, "size", 0) for f in uploaded) / (1024 * 1024)
if total_mb > MAX_MB:
    st.error(f"Taille totale trop grande ({total_mb:.1f} MB > {MAX_MB} MB)")
    st.stop()

# ========= Tri drag-and-drop (ou fallback) =========
st.write("### 1) Réorganisez (glisser-déposer) / Reorder (drag & drop)")
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
        "Cliquez les fichiers dans l'ordre souhaité / Click files in desired order",
        options=st.session_state.order_names,
        default=st.session_state.order_names
    )
    if len(order) == len(st.session_state.order_names):
        st.session_state.order_names = order

# Raccourci : ordre alpha
col_a, col_b = st.columns([1, 3])
with col_a:
    if st.button("↺ Ordre alphabétique"):
        st.session_state.order_names = sorted(st.session_state.order_names, key=str.casefold)

# ========= Aperçu numéroté =========
st.write("### 2) Aperçu de l’ordre / Order overview")
for i, nm in enumerate(st.session_state.order_names, start=1):
    st.markdown(f"**{i}.** {nm}")

# ========= Nom du fichier de sortie =========
def default_out_name():
    return f"fusion_{time.strftime('%Y-%m-%d_%H-%M-%S')}"

if "out_name" not in st.session_state:
    st.session_state.out_name = default_out_name()

st.write("### 3) Nom du fichier de sortie / Output file name")
st.session_state.out_name = st.text_input(
    "Nom du fichier (sans extension ou .pdf) / File name (without extension or .pdf)",
    value=st.session_state.out_name,
    key="out_name_input"
)

def sanitize_filename(name: str) -> str:
    name = re.sub(r"\s+", " ", name.strip())
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)  # caractères interdits
    if not name or name in {".", ".."}:
        name = default_out_name()
    name = re.sub(r"\.+$", "", name)  # retire les points finaux
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name

# ========= Fusion (PdfWriter only ; append si dispo) =========
if st.button("🚀 Fusionner dans cet ordre / Merge in this order"):
    # Map display_name -> bytes (cohérent avec l'affichage)
    display_to_bytes = {}
    counts2 = {}
    for f in uploaded:
        raw = f.getvalue() if hasattr(f, "getvalue") else f.read()
        head = (raw[:1024] if raw else b"").lstrip()
        if not head.startswith(b"%PDF-"):
            st.warning(f"{f.name}: en-tête PDF non standard, tentative de lecture quand même…")
        n = f.name
        counts2[n] = counts2.get(n, 0) + 1
        display = n if counts2[n] == 1 else f"{n} ({counts2[n]})"
        display_to_bytes[display] = raw

    pages_total = 0
    out = io.BytesIO()
    writer = PdfWriter()

    prog = st.progress(0.0, text="Préparation… / Preparing…")
    total_files = len(st.session_state.order_names)

    for idx, display_name in enumerate(st.session_state.order_names, start=1):
        data = display_to_bytes[display_name]
        try:
            reader = PdfReader(io.BytesIO(data))
        except PdfReadError as e:
            st.error(f"Impossible de lire {display_name} : {e}")
            st.stop()
        except Exception as e:
            st.error(f"Erreur inattendue en lisant {display_name} : {e}")
            st.stop()

        # Gestion PDF chiffré : tentative mot de passe vide
        if getattr(reader, "is_encrypted", False):
            try:
                reader.decrypt("")
            except Exception:
                st.error(f"{display_name} est protégé par mot de passe. Retirez la protection puis réessayez.")
                st.stop()

        pages_total += len(reader.pages)
        if pages_total > MAX_PAGES:
            st.error(f"Trop de pages au total (> {MAX_PAGES}). Fusion interrompue.")
            st.stop()

        # Fusion
        if WRITER_HAS_APPEND:
            # pypdf >= 5 : fusion du document entier en une fois
            writer.append(reader)
        else:
            # Fallback universel : page par page
            for p in reader.pages:
                writer.add_page(p)

        prog.progress(idx / total_files, text=f"Ajout de {display_name} ({idx}/{total_files})…")

    # Forcer /NeedAppearances=true pour bien afficher les champs remplis
    try:
        root = writer._root_object
        acro = root.get("/AcroForm")
        if acro is None:
            acro = DictionaryObject()
            root.update({NameObject("/AcroForm"): acro})
        acro.update({NameObject("/NeedAppearances"): BooleanObject(True)})
    except Exception:
        # on ignore si la racine/acrform n'est pas modifiable ici
        pass

    # Écriture finale
    writer.write(out)
    out.seek(0)

    final_name = sanitize_filename(st.session_state.out_name)
    st.success(f"Fusion réussie ({pages_total} pages). Formulaires/annotations importés. Fichier prêt : {final_name}")
    st.download_button(
        "⬇️ Télécharger le PDF fusionné / Download the merged PDF",
        data=out,
        file_name=final_name,
        mime="application/pdf"
    )

    # ⚠️ Note signatures
    st.warning(
        "⚠️ **Signatures numériques** : après toute fusion, la **validité cryptographique est perdue** "
        "(l’aperçu visuel reste). / Digital signatures become **cryptographically invalid** after merge "
        "(visual appearance is kept)."
    )

# Petit pied de page utile au debug
st.caption(f"pypdf writer append: {WRITER_HAS_APPEND} • MAX_MB={MAX_MB} • MAX_PAGES={MAX_PAGES}")
