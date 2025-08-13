import io
import time
import streamlit as st
from pypdf import PdfWriter, PdfReader

st.set_page_config(page_title="Fusion PDF", page_icon="📎")
st.title("📎 Fusionner des PDF")

with st.form("merge_form"):
    uploaded_files = st.file_uploader(
        "Choisissez 2+ fichiers PDF (glisser-déposer)",
        type=["pdf"],
        accept_multiple_files=True,
        help="Les fichiers seront fusionnés dans l'ordre affiché."
    )
    submitted = st.form_submit_button("Fusionner")

if submitted:
    if not uploaded_files or len(uploaded_files) < 2:
        st.error("Ajoutez au moins 2 PDF.")
    else:
        # Petite limite de sécurité (tu peux ajuster)
        max_total_mb = 100
        total_size = sum([uf.size for uf in uploaded_files]) / (1024*1024)
        if total_size > max_total_mb:
            st.error(f"Taille totale trop grande ({total_size:.1f} MB > {max_total_mb} MB)")
        else:
            writer = PdfWriter()
            for uf in uploaded_files:
                reader = PdfReader(io.BytesIO(uf.read()))
                for page in reader.pages:
                    writer.add_page(page)
            buf = io.BytesIO()
            writer.write(buf)
            buf.seek(0)
            ts = int(time.time())
            st.success("Fusion réussie !")
            st.download_button(
                label="⬇️ Télécharger le PDF fusionné",
                data=buf,
                file_name=f"fusion_{ts}.pdf",
                mime="application/pdf",
            )
