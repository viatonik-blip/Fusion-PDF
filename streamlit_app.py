import io, time
import streamlit as st
from pypdf import PdfWriter, PdfReader
import streamlit_sortables as sortables

st.set_page_config(page_title="Fusion PDF", page_icon="📎")
st.title("📎 Fusionner des PDF")

# ---- Upload ----
uploaded = st.file_uploader(
    "Glissez vos PDF (2+). Réorganisez ensuite par glisser-déposer.",
    type=["pdf"],
    accept_multiple_files=True
)

if not uploaded or len(uploaded) < 2:
    st.info("Ajoutez au moins 2 fichiers PDF pour commencer.")
    st.stop()

# ---- État initial / reset si liste change ----
names_now = [f.name for f in uploaded]
if "order_names" not in st.session_state or set(st.session_state.order_names) != set(names_now):
    # ordre par défaut : ordre d’upload
    st.session_state.order_names = names_now[:]

# ---- (Option) limite de taille totale ----
MAX_MB = 200
total_mb = sum(f.size for f in uploaded) / (1024 * 1024)
if total_mb > MAX_MB:
    st.error(f"Taille totale trop grande ({total_mb:.1f} MB > {MAX_MB} MB)")
    st.stop()

# ---- Items avec badge (HTML). Si le composant ne rend pas le HTML, on a un fallback numéroté en dessous. ----
def badge_item(idx, name):
    # petit badge rond + nom, compact
    return f"""
    <div style="display:flex;align-items:center;gap:8px;">
      <span style="
        display:inline-flex;align-items:center;justify-content:center;
        width:22px;height:22px;border-radius:9999px;
        background:#eee;font-weight:600;font-size:12px;
        border:1px solid #ddd;">
        {idx}
      </span>
      <span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:420px;">{name}</span>
    </div>
    """

# Construit la liste à partir de l'ordre courant (numéro = position courante)
items_with_badges = [badge_item(i+1, nm) for i, nm in enumerate(st.session_state.order_names)]

st.write("### 1) Réorganisez (glisser-déposer)")
# Appel au composant : si le HTML est rendu, on verra le badge directement pendant le drag.
# Sinon, ce sont de simples étiquettes — le fallback plus bas montrera les numéros.
ordered_labels = sortables.sort_items(
    items_with_badges, direction="vertical", key="sortable_list"
)

# On doit traduire les labels reçus (HTML) -> noms de fichiers.
# Ici on s’appuie sur la position renvoyée par le composant : on recalcule l’ordre des noms à partir de l’ordre des labels.
# Comme items_with_badges et st.session_state.order_names sont alignés, on peut mapper par index :
index_by_label = {lbl: i for i, lbl in enumerate(items_with_badges)}
new_order = [st.session_state.order_names[index_by_label[lbl]] for lbl in ordered_labels]

st.session_state.order_names = new_order  # maj ordre global

# Aperçu numéroté clair (fallback visuel garanti)
st.write("### 2) Aperçu de l’ordre")
for i, nm in enumerate(st.session_state.order_names, start=1):
    st.markdown(f"**{i}.** {nm}")

# ---- Fusion ----
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
