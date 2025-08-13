import io
import time
import streamlit as st
from pypdf import PdfWriter, PdfReader
import streamlit_sortables as sortables

st.set_page_config(page_title="Fusion PDF", page_icon="📎")
st.title("📎 Fusionner des PDF")

uploaded_files = st.file_uploader(
    "Glisser-déposer vos PDF ici",
    type=["pdf"],
    accept_multiple_files=True,
    help="Déposez au moins 2 fichiers PDF puis réorganisez-les ci-dessous."
)

if uploaded_files and len(uploaded_files) >= 2:
    # Liste initiale des noms
    file_names = [f.name for f in uploaded_files]

    # Drag & drop ordering
    st.write("### Réorganisez vos fichiers (glisser-déposer)")
    ordered_names = sortables.sort_items(
        file_names,
        direction="vertical",
        key="sortable_list"
    )

    if st.button("🚀 Fusionner dans cet ordre"):
        # Mapping nom -> contenu
        name_to_bytes = {f.name: f.read() for f in uploaded_files}

        writer = PdfWriter()
        for name in ordered_names:
            reader = PdfReader(io.BytesIO(name_to_bytes[name]))
            for page in reader.pages:
                writer.add_page(page)

        buf = io.BytesIO()
        writer.write(buf)
        buf.seek(0)
        ts = int(time.time())
        st.download_button(
            label="⬇️ Télécharger le PDF fusionné",
            data=buf,
            file_name=f"fusion_{ts}.pdf",
            mime="application/pdf",
        )
else:
    st.info("Ajoutez au moins deux PDF pour commencer.")
