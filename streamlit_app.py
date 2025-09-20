import io, time, os, re
import streamlit as st
from pypdf import PdfWriter, PdfReader

# Drag & drop
try:
    import streamlit_sortables as sortables
    HAS_SORT = True
except Exception:
    HAS_SORT = False

# Compression (optionnelles)
try:
    import pikepdf  # compression "soft" sans perte
    HAS_PIKEPDF = True
except Exception:
    HAS_PIKEPDF = False

try:
    import fitz  # PyMuPDF : rasterisation (forte compression)
    HAS_PYMUPDF = True
except Exception:
    HAS_PYMUPDF = False


# -------- Helpers compression + DIAGNOSTIC --------
def _size_mb(b: bytes) -> float:
    return len(b) / (1024 * 1024)


def _compress_lossless_pikepdf(in_bytes: bytes):
    """Compression 'soft' (sans perte) via pikepdf. Renvoie bytes ou None."""
    if not HAS_PIKEPDF:
        return None
    try:
        bio_in = io.BytesIO(in_bytes)
        with pikepdf.open(bio_in) as pdf:
            bio_out = io.BytesIO()
            pdf.save(
                bio_out,
                linearize=True,           # web-optimize
                object_stream_mode=1,     # regroupe objets
                compress_streams=True,    # compresse les streams
            )
            return bio_out.getvalue()
    except Exception:
        return None


def _compress_rasterize_pymupdf(
    in_bytes: bytes,
    target_mb: float = 25.0,
    dpi_candidates=(150, 130, 110, 96, 85, 72, 60),
    jpeg_qualities=(75, 60, 50, 40, 35, 30),
    grayscale_first=True,
):
    """
    Compression 'forte' : rend chaque page en image JPEG,
    avec essais (DPI x qualité) et option niveau de gris.
    Renvoie (bytes, {'dpi':X, 'quality':Y, 'gray':bool}, debug_dict)
    ou (best_bytes, best_params, debug_dict) si aucune ne passe.
    ⚠️ Le texte n’est plus sélectionnable/recherchable.
    """
    dbg = {
        "applied": HAS_PYMUPDF,
        "target_mb": target_mb,
        "attempts": [],        # liste des (dpi, quality, gray, size_mb)
        "best_after_mb": None,
        "best_params": None,
    }
    if not HAS_PYMUPDF:
        return None, None, dbg
    try:
        best_bytes = None
        best_size = float("inf")
        best_params = None

        for use_gray in ([True, False] if grayscale_first else [False, True]):
            for dpi in dpi_candidates:
                src = fitz.open("pdf", in_bytes)
                zoom = dpi / 72.0
                mat = fitz.Matrix(zoom, zoom)
                # Pré-rendu des pages au DPI choisi
                pages_pix = []
                for page in src:
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    if use_gray and pix.n >= 3:  # convertir en niveaux de gris si possible
                        pix = fitz.Pixmap(pix, 0)  # canal 0 => gray
                    pages_pix.append(pix)

                for q in jpeg_qualities:
                    out = fitz.open()
                    for pix in pages_pix:
                        img_bytes = pix.tobytes("jpeg", quality=q)
                        new_page = out.new_page(width=pix.width, height=pix.height)
                        rect = fitz.Rect(0, 0, pix.width, pix.height)
                        new_page.insert_image(rect, stream=img_bytes, keep_proportion=False)
                    buf = out.tobytes()
                    sz = _size_mb(buf)
                    dbg["attempts"].append({"dpi": dpi, "quality": q, "gray": use_gray, "after_mb": round(sz, 2)})

                    if sz <= target_mb:
                        dbg["best_after_mb"] = round(sz, 2)
                        dbg["best_params"] = {"dpi": dpi, "quality": q, "gray": use_gray}
                        return buf, {"dpi": dpi, "quality": q, "gray": use_gray}, dbg

                    if sz < best_size:
                        best_size = sz
                        best_bytes = buf
                        best_params = {"dpi": dpi, "quality": q, "gray": use_gray}

        if best_bytes is not None:
            dbg["best_after_mb"] = round(best_size, 2)
            dbg["best_params"] = best_params
        return best_bytes, best_params, dbg
    except Exception:
        return None, None, dbg


def compress_to_target(
    in_bytes: bytes,
    target_mb: float = 25.0,
    force_aggressive_if_over_target: bool = True,
    dpi_candidates=(150, 130, 110, 96, 85, 72, 60),
    jpeg_qualities=(75, 60, 50, 40, 35, 30),
):
    """
    1) Soft (pikepdf). Si <= target, on s'arrête.
    2) Si > target et autorisé: forte (rasterize, gris d'abord).
       -> renvoie la 1ère <= target, sinon la plus petite atteinte.
    Retourne (final_bytes, method_label, stats_dict, debug_dict).
    """
    before = _size_mb(in_bytes)
    debug = {
        "available": {"pikepdf": HAS_PIKEPDF, "pymupdf": HAS_PYMUPDF},
        "target_mb": target_mb,
        "soft": {"applied": HAS_PIKEPDF, "after_mb": None},
        "aggressive": None,  # rempli si tenté
        "before_mb": round(before, 2),
    }

    # Soft (sans perte)
    best = in_bytes
    method = "none"
    soft = _compress_lossless_pikepdf(in_bytes)
    if soft and _size_mb(soft) < before:
        best = soft
        method = "pikepdf (soft)"
        debug["soft"]["after_mb"] = round(_size_mb(soft), 2)
    else:
        # même si soft n'apporte rien, on note la taille si soft a tourné
        if soft is not None:
            debug["soft"]["after_mb"] = round(_size_mb(soft), 2)

    if _size_mb(best) <= target_mb:
        stats = {"before_mb": before, "after_mb": _size_mb(best)}
        debug["final_method"] = method
        debug["final_after_mb"] = round(stats["after_mb"], 2)
        return best, method, stats, debug

    # Forte (rasterisation)
    if force_aggressive_if_over_target and HAS_PYMUPDF:
        hard, params, dbg_aggr = _compress_rasterize_pymupdf(
            best, target_mb=target_mb,
            dpi_candidates=dpi_candidates,
            jpeg_qualities=jpeg_qualities,
            grayscale_first=True
        )
        debug["aggressive"] = dbg_aggr
        if hard and _size_mb(hard) < _size_mb(best):
            gray_flag = params.get("gray") if params else None
            method = f"rasterize (dpi={params.get('dpi')}, q={params.get('quality')}, gray={gray_flag})" if params else "rasterize"
            stats = {"before_mb": before, "after_mb": _size_mb(hard)}
            debug["final_method"] = method
            debug["final_after_mb"] = round(stats["after_mb"], 2)
            return hard, method, stats, debug

    # Aucun gain ou dépendances absentes -> retour 'best'
    stats = {"before_mb": before, "after_mb": _size_mb(best)}
    debug["final_method"] = method
    debug["final_after_mb"] = round(stats["after_mb"], 2)
    return best, method, stats, debug


# ---------------- UI / App ----------------
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

# --- Construire des noms "affichés" uniques (gère doublons: nom.pdf (2), etc.)
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
        "Cliquez les fichiers dans l'ordre souhaité / Click files in desired order",
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
st.session_state.out_name = st.text_input(
    "Nom du fichier (sans extension ou .pdf) / File name (without extension or .pdf)",
    value=st.session_state.out_name,
    key="out_name_input"
)

def sanitize_filename(name: str) -> str:
    name = name.strip()
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)  # caractères interdits
    if not name:
        name = default_out_name()
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name

# --- Option de compression
compress_opt = st.checkbox(
    "Compresser le PDF final ≤ 25 Mo (e-mail) / Compress final PDF ≤ 25 MB (email)",
    value=True,
    help="Tente d'abord une compression sans perte, puis une compression forte (rasterisation) si nécessaire."
)

# Réglages compression (avancés)
with st.expander("⚙️ Options de compression / Compression options", expanded=False):
    target_mb = st.number_input("Taille cible (Mo) / Target size (MB)", 5.0, 100.0, 25.0, 1.0)
    force_aggr = st.checkbox("Toujours tenter la compression agressive si au-dessus de la cible / Always try aggressive compression if above target", value=True)
    dpi_candidates = st.multiselect(
        "DPI à essayer (du plus net au plus léger) / DPI candidates",
        [150, 130, 110, 96, 85, 72, 60],
        default=[150, 130, 110, 96, 85, 72, 60]
    )
    jpeg_qualities = st.multiselect(
        "Qualités JPEG à essayer / JPEG qualities",
        [75, 60, 50, 40, 35, 30],
        default=[75, 60, 50, 40, 35, 30]
    )

# Diagnostic dispo libs
st.caption(
    f"Compression disponibles → pikepdf: {'✅' if HAS_PIKEPDF else '❌'} | PyMuPDF: {'✅' if HAS_PYMUPDF else '❌'}"
)
if compress_opt and (not HAS_PIKEPDF and not HAS_PYMUPDF):
    st.warning("Compression activée mais dépendances absentes (pikepdf/pymupdf). Le PDF sera livré non compressé.")

# --- Fusion
if st.button("🚀 Fusionner dans cet ordre / Merge in this order"):
    # Recrée le mapping display_name -> bytes (dédoublonnage aligné à l'UI)
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

    # Fusion en mémoire
    writer = PdfWriter()
    for display_name in st.session_state.order_names:
        reader = PdfReader(io.BytesIO(display_to_bytes[display_name]))
        for page in reader.pages:
            writer.add_page(page)

    fused = io.BytesIO()
    writer.write(fused)
    fused.seek(0)
    fused_bytes = fused.getvalue()

    # Compression si demandée
    final_bytes, method, stats, debug = (fused_bytes, "none",
                                         {"before_mb": _size_mb(fused_bytes), "after_mb": _size_mb(fused_bytes)},
                                         {"note": "compression not attempted"})
    if compress_opt:
        with st.spinner("Compression du PDF … / Compressing PDF …"):
            final_bytes, method, stats, debug = compress_to_target(
                fused_bytes,
                target_mb=target_mb,
                force_aggressive_if_over_target=force_aggr,
                dpi_candidates=tuple(dpi_candidates) if dpi_candidates else (150,130,110,96,85,72,60),
                jpeg_qualities=tuple(jpeg_qualities) if jpeg_qualities else (75,60,50,40,35,30),
            )

    final_name = sanitize_filename(st.session_state.out_name)

    # Résumé utilisateur
    st.success(f"OK ✅  Taille: {stats['after_mb']:.2f} Mo (avant: {stats['before_mb']:.2f} Mo) — méthode: {method}")
    st.download_button(
        "⬇️ Télécharger le PDF fusionné / Download the merged PDF",
        data=final_bytes,
        file_name=final_name,
        mime="application/pdf"
    )

    # Avertissements utiles
    if compress_opt and method == "none":
        st.warning("La compression n’a produit aucun gain. Le PDF est probablement déjà optimisé. "
                   "Active/force la compression agressive et/ou baisse le DPI/qualité dans les options.")
    elif compress_opt and method.startswith("rasterize") and stats["after_mb"] > target_mb:
        st.warning("Compression agressive appliquée, mais la taille cible n’a pas été atteinte. "
                   "Réduis encore le DPI (72/60) et la qualité (35/30), ou divise le document.")

    # 🩺 Panneau DIAGNOSTIC complet
    with st.expander("🩺 Diagnostic (détails de la compression) / Compression debug", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Disponibilité des moteurs**")
            st.json(debug.get("available", {"pikepdf": HAS_PIKEPDF, "pymupdf": HAS_PYMUPDF}))
            st.write("**Soft (pikepdf)**")
            st.json(debug.get("soft", {}))
        with col2:
            st.write("**Avant / Final**")
            st.json({"before_mb": round(stats["before_mb"], 2), "final_method": debug.get("final_method", method), "final_after_mb": round(stats["after_mb"], 2)})
            st.write("**Cible**")
            st.json({"target_mb": debug.get("target_mb", None)})

        st.write("**Agressive (PyMuPDF) — tentatives**")
        ag = debug.get("aggressive")
        if not ag:
            st.info("Aucune tentative agressive (désactivée ou PyMuPDF indisponible).")
        else:
            st.write("Meilleur résultat")
            st.json({"best_after_mb": ag.get("best_after_mb"), "best_params": ag.get("best_params")})
            # Affiche seulement les 10 premières tentatives pour rester lisible
            attempts = ag.get("attempts", [])
            if attempts:
                st.write(f"Tentatives (premières {min(10, len(attempts))}/{len(attempts)})")
                st.json(attempts[:10])
            else:
                st.info("Aucune tentative enregistrée.")
