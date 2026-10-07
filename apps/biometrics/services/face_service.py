"""Face module: detection -> alignment -> preprocessing -> embedding -> matching.

Backends
  classical : OpenCV HOG + LBP descriptor (CPU only, zero extra install)
  torch     : FaceNet (InceptionResnetV1, facenet-pytorch) if installed and FACE_BACKEND=torch
"""
import cv2
import numpy as np

FACE_SIZE = 96
_face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
_eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")
_clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
_hog = cv2.HOGDescriptor((64, 64), (16, 16), (8, 8), (8, 8), 9)
DEFAULT_THRESHOLDS = {"classical": 0.92, "torch": 0.65}
_torch_model = None


def available_backend(requested="classical"):
    if requested == "torch":
        try:
            import torch  # noqa: F401
            from facenet_pytorch import InceptionResnetV1  # noqa: F401
            return "torch"
        except Exception:
            return "classical"
    return "classical"


# ------------------------------------------------------------------ detection
def detect_faces(bgr, allow_full_frame_fallback=False):
    """Return list of (x, y, w, h) boxes, largest first. In demo mode a frame that is
    already a face crop (synthetic sample) is accepted as a single full-frame face."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    h, w = gray.shape
    min_side = max(40, int(min(h, w) * 0.08))
    faces = _face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(min_side, min_side))
    boxes = sorted([tuple(int(v) for v in f) for f in faces], key=lambda b: -b[2] * b[3])
    if not boxes and allow_full_frame_fallback:
        boxes = [(0, 0, w, h)]
    return boxes


# ------------------------------------------------------------------ alignment
def crop_face(bgr, box):
    """Un-resized face crop (used for liveness, which needs the native resolution)."""
    x, y, w, h = box
    return bgr[max(0, y):y + h, max(0, x):x + w]


def align_face(bgr, box):
    """Crop, rotate so the eye line is horizontal (if two eyes found) and resize."""
    x, y, w, h = box
    pad = int(0.1 * w)
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(bgr.shape[1], x + w + pad), min(bgr.shape[0], y + h + pad)
    roi = bgr[y0:y1, x0:x1]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    top = gray[: int(gray.shape[0] * 0.6)]
    eyes = _eye_cascade.detectMultiScale(top, 1.1, 5, minSize=(max(10, w // 10), max(10, w // 10)))
    angle = 0.0
    if len(eyes) >= 2:
        eyes = sorted(eyes, key=lambda e: -e[2] * e[3])[:2]
        (ex1, ey1, ew1, eh1), (ex2, ey2, ew2, eh2) = sorted(eyes, key=lambda e: e[0])
        c1 = (ex1 + ew1 / 2, ey1 + eh1 / 2)
        c2 = (ex2 + ew2 / 2, ey2 + eh2 / 2)
        angle = float(np.degrees(np.arctan2(c2[1] - c1[1], c2[0] - c1[0])))
        if abs(angle) > 25:
            angle = 0.0
    if angle:
        M = cv2.getRotationMatrix2D((roi.shape[1] / 2, roi.shape[0] / 2), angle, 1.0)
        roi = cv2.warpAffine(roi, M, (roi.shape[1], roi.shape[0]), borderMode=cv2.BORDER_REPLICATE)
    return cv2.resize(roi, (FACE_SIZE, FACE_SIZE), interpolation=cv2.INTER_AREA), angle


# ------------------------------------------------------------------ preprocessing
def preprocess(face_bgr):
    gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    return _clahe.apply(gray)


def face_quality(face_bgr):
    gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
    sharp = min(1.0, cv2.Laplacian(gray, cv2.CV_64F).var() / 150.0)
    m = gray.mean()
    bright = 1.0 - min(1.0, abs(m - 120) / 120)
    return float(0.6 * sharp + 0.4 * bright)


# ------------------------------------------------------------------ embeddings
def _lbp_hist(gray, grid=4, bins=32):
    g = gray.astype(np.int16)
    c = g[1:-1, 1:-1]
    code = np.zeros_like(c, dtype=np.uint8)
    shifts = [(-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1)]
    for i, (dy, dx) in enumerate(shifts):
        nb = g[1 + dy: g.shape[0] - 1 + dy, 1 + dx: g.shape[1] - 1 + dx]
        code |= ((nb >= c).astype(np.uint8) << i)
    h, w = code.shape
    feats = []
    for gy in range(grid):
        for gx in range(grid):
            cell = code[gy * h // grid:(gy + 1) * h // grid, gx * w // grid:(gx + 1) * w // grid]
            hist, _ = np.histogram(cell, bins=bins, range=(0, 256))
            feats.append(hist / max(1, cell.size))
    return np.concatenate(feats)


def _embed_classical(gray):
    small = cv2.resize(gray, (64, 64))
    hog = _hog.compute(small).ravel()
    lbp = _lbp_hist(cv2.resize(gray, (FACE_SIZE, FACE_SIZE)))
    v = np.concatenate([hog / (np.linalg.norm(hog) + 1e-8), lbp / (np.linalg.norm(lbp) + 1e-8)])
    return v


def _embed_torch(face_bgr):
    global _torch_model
    import torch
    from facenet_pytorch import InceptionResnetV1
    if _torch_model is None:
        _torch_model = InceptionResnetV1(pretrained="vggface2").eval()
    rgb = cv2.cvtColor(cv2.resize(face_bgr, (160, 160)), cv2.COLOR_BGR2RGB)
    t = torch.from_numpy(rgb).permute(2, 0, 1).float().div(255).sub(0.5).div(0.5).unsqueeze(0)
    with torch.no_grad():
        return _torch_model(t)[0].numpy()


def extract_embedding(face_bgr, backend="classical"):
    if backend == "torch":
        v = _embed_torch(face_bgr)
    else:
        v = _embed_classical(preprocess(face_bgr))
    v = v.astype(np.float32)
    return v / (np.linalg.norm(v) + 1e-8)


# ------------------------------------------------------------------ matching
def cosine_scores(query, gallery):
    """query: (d,), gallery: (n,d) -> (n,) cosine similarities."""
    return gallery @ query


def sim_to_score(sim, threshold, k=25.0):
    """Calibrated confidence in [0,1]; equals 0.5 exactly at the decision threshold."""
    return float(1.0 / (1.0 + np.exp(-k * (sim - threshold))))


def match(query, student_ids, gallery, threshold):
    """Return (best_student_id, best_sim, score). Per-student score = max similarity over its samples."""
    if len(student_ids) == 0:
        return None, 0.0, 0.0
    sims = cosine_scores(query, gallery)
    ids = np.asarray(student_ids)
    best_per = {}
    for sid, s in zip(ids, sims):
        if s > best_per.get(int(sid), -1):
            best_per[int(sid)] = float(s)
    sid, sim = max(best_per.items(), key=lambda kv: kv[1])
    return sid, sim, sim_to_score(sim, threshold)
