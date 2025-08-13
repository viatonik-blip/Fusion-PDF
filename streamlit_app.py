import io, time
import streamlit as st
from pypdf import PdfWriter, PdfReader
import streamlit_sortables as sortables

st.set_page_config(page_title="Fusion PDF", page_icon="📎")
st.title("📎 Fusionner des PDF")

uploaded = st.file_uploader(
    "Glissez vos PDF (2+). Réorganisez ensuite par glisser-déposer.",
    type=["pdf"],
    accept_multiple_files=True
)

if not uploaded or len(uploaded) < 2:
    st.info("Ajoutez au moins 2 fichiers PDF pour commencer.")
    st.stop()

# Initialisation de l'ordre
names_now = [f.name for f in uploaded]
if "order_names" not in st.session_state or set(st.session_state.order_names) != set(names_now):
    st.session_state.order_names = names_now[:]

# Limite de taille totale
MAX_MB = 200
total_mb = sum(f.size for f in uploaded) / (1024 * 1024)
if total_mb > MAX_MB:
    st.error(f"Taille totale trop grande ({total_mb:.1f} MB > {MAX_MB} MB)")
    st.stop()

# Drag-and-drop : on passe seulement les noms simples
st.write("### 1) Réorganisez (glisser-déposer)")
ordered_names = sortables.sort_items(
    st.session_state.order_names,
    direction="vertical",
    key="sortable_list"
)
st.session_state.order_names = ordered_names

# Aperçu numéroté
st.write("### 2) Aperçu de l’ordre")
for i, nm in enumerate(st.session_state.order_names, start=1):
    st.markdown(f"**{i}.** {nm}")

# Fusion
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
