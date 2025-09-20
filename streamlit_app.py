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


# ===================== Constantes de compression =====================
TARGET_MB = 25.0  # objectif e-mail
# Essais (du plus net au plus léger). On couvre large pour "forcer" sous 25 Mo.
DPI_CANDIDATES = (150, 130, 110, 96, 85, 72, 60, 50)
JPEG_QUALITIES = (75, 60, 50, 40, 35, 30, 25)
GRAYSCALE_FIRST = True  # on commence en N&B (gain fort sur scans/texte)


# ===================== Helpers compression =====================
def _size_mb(b: bytes) -> float:
    return len(b) / (1024 * 1024)


def _compress_lossless_pikepdf(in_bytes: bytes) -> bytes | None:
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


# --- remplace entièrement cette fonction ---
def _compress_rasterize_pymupdf(
    in_bytes: bytes,
    target_mb: float = TARGET_MB,
    dpi_candidates=DPI_CANDIDATES,
    jpeg_qualities=JPEG_QUALITIES,
    grayscale_first: bool = GRAYSCALE_FIRST,
) -> tuple[bytes | None, dict | None]:
    """
    Compression 'forte' : rend chaque page en image JPEG.
    Essaie une grille (gris->couleur, DPI x qualité) jusqu'à passer sous target_mb.
    Renvoie (bytes, {'dpi':X, 'quality':Y, 'gray':bool}) ou (meilleur_bytes, meilleurs_params).
    ⚠️ Le texte n’est plus sélectionnable/recherchable.
    """
    if not HAS_PYMUPDF:
        return None, None
    try:
        best_bytes = None
        best_size = float("inf")
        best_params = None

        gray_order = [True, False] if grayscale_first else [False, True]
        for use_gray in gray_order:
            for dpi in dpi_candidates:
                src = fitz.open("pdf", in_bytes)
                zoom = dpi / 72.0
                mat = fitz.Matrix(zoom, zoom)

                # Pré-rendu des pages au DPI choisi
                pages_pix = []
                for page in src:
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    # 🔧 PATCH PyMuPDF >= 1.24 : conversion gris correcte
                    if use_gray:
                        try:
                            # si l'image a une colorspace multi-canaux, convertis en GRAY
                            if getattr(pix, "colorspace", None) and getattr(pix.colorspace, "n", 1) > 1:
                                pix = fitz.Pixmap(fitz.csGRAY, pix)
                        except Exception:
                            # si la conversion échoue, on reste en couleur pour cette page
                            pass
                    pages_pix.append(pix)

                for q in jpeg_qualities:
                    out = fitz.open()
                    for pix in pages_pix:
                        img_bytes = pix.tobytes("jpeg", quality=q)
                        page_w, page_h = pix.width, pix.height
                        new_page = out.new_page(width=page_w, height=page_h)
                        rect = fitz.Rect(0, 0, page_w, page_h)
                        new_page.insert_image(rect, stream=img_bytes, keep_proportion=False)
                    buf = out.tobytes()
                    sz = _size_mb(buf)

                    if sz <= target_mb:
                        return buf, {"dpi": dpi, "quality": q, "gray": use_gray}

                    if sz < best_size:
                        best_size = sz
                        best_bytes = buf
                        best_params = {"dpi": dpi, "quality": q, "gray": use_gray}

        return best_bytes, best_params
    except Exception as e:
        # surface l’erreur pour qu’elle apparaisse dans l’app
        st.error(f"PyMuPDF rasterize error: {e}")
        return None, None


# --- remplace entièrement cette fonction ---
def compress_to_target_auto(in_bytes: bytes, target_mb: float = TARGET_MB):
    """
    1) Tente pikepdf (soft). Si <= target -> retour.
    2) Sinon tente PyMuPDF (agressif, grille complète) jusqu'à passer sous target.
       -> Si aucune combinaison n'atteint la cible, renvoie la plus petite atteinte.
    """
    before = _size_mb(in_bytes)

    # 1) Soft (sans perte)
    best = in_bytes
    method = "none"
    try:
        soft = _compress_lossless_pikepdf(in_bytes)
        if soft is not None and _size_mb(soft) < before:
            best = soft
            method = "pikepdf (soft)"
    except Exception as e:
        st.warning(f"pikepdf a échoué: {e}")

    if _size_mb(best) <= target_mb:
        return best, method, {"before_mb": before, "after_mb": _size_mb(best)}

    # 2) Aggressif auto si au-dessus de la cible
    if HAS_PYMUPDF:
        hard, params = _compress_rasterize_pymupdf(
            best, target_mb=target_mb,
            dpi_candidates=DPI_CANDIDATES,
            jpeg_qualities=JPEG_QUALITIES,
            grayscale_first=GRAYSCALE_FIRST
        )
        if hard is not None and _size_mb(hard) < _size_mb(best):
            gray_flag = params.get("gray") if params else None
            method = f"rasterize (dpi={params.get('dpi')}, q={params.get('quality')}, gray={gray_flag})" if params else "rasterize"
            return hard, method, {"before_mb": before, "after_mb": _size_mb(hard)}
        else:
            st.warning("PyMuPDF (agressif) a tourné, mais n'a pas fourni de version plus petite. "
                       "On livre la meilleure version atteinte.")
            if hard is not None:
                # Même si ce n'est pas sous la cible, renvoyer la plus petite atteinte
                return hard, "rasterize (best-effort)", {"before_mb": before, "after_mb": _size_mb(hard)}

    # 3) Fallback : aucun gain (ou dépendances absentes) -> retour best
    return best, method, {"before_mb": before, "after_mb": _size_mb(best)}



# ===================== UI / App =====================
st.set_page_config(page_title="Fusion PDF / Merge PDF", page_icon="📎")
st.title("📎 Fusionner des documents / Merge documents")

# Auth centre (optionnelle via secrets)
APP_PASSWORD = st.secrets.get("APP_PASSWORD", None)
if "authed" not in st.session_state:
    st.session_state.authed = False

def auth_view():
    st.write("")
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
            pw = st.text_input("Mot de passe / Password", type="password", placeholder="Votre mot de passe / Your password")
            submitted = st.form_submit_button("Valider / Validate")
            if submitted:
                if pw == APP_PASSWORD:
                    st.session_state.authed = True
                else:
                    st.error("Mot de passe incorrect. / Wrong password.")

if APP_PASSWORD and not st.session_state.authed:
    auth_view()
    st.stop()

# Uploader
uploaded = st.file_uploader(
    "Glissez vos PDF (2+). Réorganisez ensuite par glisser-déposer. / Drag and drop your PDFs (2+). Then rearrange them using drag and drop.",
    type=["pdf"],
    accept_multiple_files=True
)

if not uploaded or len(uploaded) < 2:
    st.info("Ajoutez au moins 2 fichiers PDF pour commencer. / Add at least 2 PDF files to get started.")
    st.stop()

# Construire des noms affichés uniques (gère doublons)
raw_names = [f.name for f in uploaded]
names_now, counts = [], {}
for n in raw_names:
    counts[n] = counts.get(n, 0) + 1
    names_now.append(n if counts[n] == 1 else f"{n} ({counts[n]})")

# Gestion robuste de l'ordre (OK même ajout 1 par 1)
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

# Limite de taille totale upload
MAX_MB = int(os.getenv("CRF_MAX_UPLOAD_MB", "200"))
total_mb = sum(f.size for f in uploaded) / (1024 * 1024)
if total_mb > MAX_MB:
    st.error(f"Taille totale trop grande ({total_mb:.1f} MB > {MAX_MB} MB)")
    st.stop()

# Tri drag-and-drop (ou fallback)
st.write("### 1) Réorganisez (glisser-déposer) / Reorder (drag and drop)")
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

# Aperçu numéroté
st.write("### 2) Aperçu de l’ordre / Order overview")
for i, nm in enumerate(st.session_state.order_names, start=1):
    st.markdown(f"**{i}.** {nm}")

# Nom du fichier de sortie (persistant)
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
    name = name.strip()
    name = re.sub(r'[\\/:*?\"<>|]+', "_", name)
    if not name:
        name = default_out_name()
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name

# ✅ Une seule option utilisateur : compresser ou non
compress_opt = st.checkbox(
    "Compresser pour e-mail (≤ 25 Mo) / Compress for email (≤ 25 MB)",
    value=True
)

# Fusion
if st.button("🚀 Fusionner dans cet ordre / Merge in this order"):
    # Map display_name -> bytes (cohérent avec l'affichage)
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

    # Compression auto si demandée
    final_bytes, method, stats = (fused_bytes, "none", {"before_mb": _size_mb(fused_bytes), "after_mb": _size_mb(fused_bytes)})
    if compress_opt:
        with st.spinner("Compression du PDF… / Compressing PDF…"):
            final_bytes, method, stats = compress_to_target_auto(fused_bytes, target_mb=TARGET_MB)

    final_name = sanitize_filename(st.session_state.out_name)
    st.success(f"OK ✅  Taille: {stats['after_mb']:.2f} Mo (avant: {stats['before_mb']:.2f} Mo) — méthode: {method}")
    st.download_button(
        "⬇️ Télécharger le PDF fusionné / Download the merged PDF",
        data=final_bytes,
        file_name=final_name,
        mime="application/pdf"
    )

    # Messages utiles
    if compress_opt and method == "none":
        st.warning("La compression n’a produit aucun gain (PDF probablement déjà optimisé) "
                   "ou dépendances manquantes. Installez pikepdf/pymupdf si nécessaire.")
    elif compress_opt and stats["after_mb"] > TARGET_MB:
        st.warning("Compression agressive appliquée, mais la cible 25 Mo n’a pas pu être atteinte. "
                   "Le document est très dense. Envisagez de le scinder ou d’accepter une qualité plus faible.")
