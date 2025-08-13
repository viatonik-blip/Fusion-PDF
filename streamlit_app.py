import io
import time
import streamlit as st
from pypdf import PdfWriter, PdfReader
import pandas as pd

st.set_page_config(page_title="Fusion PDF", page_icon="📎")
st.title("📎 Fusionner des PDF")

with st.form("merge_form"):
    uploaded_files = st.file_uploader(
        "Choisissez 2+ fichiers PDF (glisser-déposer)",
        type=["pdf"],
        accept_multiple_files=True,
        help="Réglez l'ordre de fusion dans le tableau qui s'affichera.",
        key="uploader",
    )
    submitted = st.form_submit_button("Préparer")

if submitted:
    if not uploaded_files or len(uploaded_files) < 2:
        st.error("Ajoutez au moins 2 PDF.")
        st.stop()

    # Sécurité: limite de taille totale (ajuste selon ton besoin)
    max_total_mb = 100
    total_size_mb = sum([uf.size for uf in uploaded_files]) / (1024 * 1024)
    if total_size_mb > max_total_mb:
        st.error(f"Taille totale trop grande ({total_size_mb:.1f} MB > {max_total_mb} MB)")
        st.stop()

    # On lit tout en RAM une fois, et on stocke un identifiant stable pour éviter
    # les collisions si des noms de fichiers sont identiques.
    files_data = []
    for idx, uf in enumerate(uploaded_files):
        raw = uf.read()
        if not raw.startswith(b"%PDF-"):
            st.error(f"Fichier non-PDF ou corrompu: {uf.name}")
            st.stop()
        files_data.append(
            {
                "id": idx,                # identifiant interne
                "name": uf.name,          # nom affiché
                "size_mb": round(len(raw) / (1024 * 1024), 2),
                "bytes": raw,             # contenu
            }
        )

    # DataFrame pour réordonner (par défaut: 1..N)
    df = pd.DataFrame(
        {
            "ID": [f["id"] for f in files_data],
            "Fichier": [f["name"] for f in files_data],
            "Taille (MB)": [f["size_mb"] for f in files_data],
            "Ordre": list(range(1, len(files_data) + 1)),
        }
    )

    st.write("### Réglez l’ordre de fusion")
    edited = st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Ordre": st.column_config.NumberColumn(
                "Ordre",
                help="1 = premier dans le PDF final",
                min_value=1,
                max_value=len(files_data),
                step=1,
                format="%d",
            ),
            "ID": st.column_config.NumberColumn("ID", disabled=True),
            "Fichier": st.column_config.TextColumn("Fichier", disabled=True),
            "Taille (MB)": st.column_config.NumberColumn("Taille (MB)", disabled=True),
        },
        key="order_editor",
    )

    # Validation : les ordres doivent être 1..N sans doublons
    ordre_values = edited["Ordre"].tolist()
    attendu = set(range(1, len(files_data) + 1))
    if set(ordre_values) != attendu or len(ordre_values) != len(set(ordre_values)):
        st.warning("⚠️ Les numéros d'ordre doivent être uniques et couvrir 1..N.")
        st.stop()

    # Tri selon l’ordre choisi
    edited_sorted = edited.sort_values("Ordre", kind="stable")
    st.success("Ordre validé. Vous pouvez lancer la fusion.")
    if st.button("🚀 Fusionner maintenant"):
        writer = PdfWriter()
        # On fusionne en parcourant les IDs dans l’ordre choisi
        id_to_blob = {f["id"]: f["bytes"] for f in files_data}
        for _id in edited_sorted["ID"].tolist():
            reader = PdfReader(io.BytesIO(id_to_blob[_id]))
            for page in reader.pages:
                writer.add_page(page)

        out = io.BytesIO()
        writer.write(out)
        out.seek(0)
        ts = int(time.time())
        st.download_button(
            label="⬇️ Télécharger le PDF fusionné",
            data=out,
            file_name=f"fusion_{ts}.pdf",
            mime="application/pdf",
        )
