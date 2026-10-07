"""Iris module: eye detection -> segmentation -> quality -> normalisation (Daugman rubber sheet)
-> Gabor encoding (binary iris code) -> Hamming-distance matching with rotation compensation."""
import cv2
import numpy as np

_eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")
ROWS, COLS = 32, 128
CODE_SHAPE = (ROWS, COLS, 2)
N_BITS = ROWS * COLS * 2
MAX_SHIFT = 8
_gabor = [cv2.getGaborKernel((11, 11), 3.0, 0, 8.0, 1.0, psi, ktype=cv2.CV_32F) for psi in (0.0, np.pi / 2)]


# ------------------------------------------------------------------ eye detection
def detect_eyes(bgr, face_box=None):
    """Return list of (crop_bgr, side) for eyes found. Looks in the upper face if a face box is given."""
    ox = oy = 0
    region = bgr
    if face_box is not None:
        x, y, w, h = face_box
        region = bgr[y: y + int(h * 0.6), x: x + w]
        ox, oy = x, y
    gray = cv2.equalizeHist(cv2.cvtColor(region, cv2.COLOR_BGR2GRAY))
    eyes = _eye_cascade.detectMultiScale(gray, 1.1, 5, minSize=(20, 20))
    out = []
    for (ex, ey, ew, eh) in sorted(eyes, key=lambda e: e[0])[:2]:
        crop = region[ey: ey + eh, ex: ex + ew]
        side = "L" if (ex + ew / 2) < region.shape[1] / 2 else "R"
        out.append((crop, side))
    return out


# ------------------------------------------------------------------ segmentation
def _circle_mean(gray, cx, cy, r, angles):
    xs = np.clip((cx + r * np.cos(angles)).astype(int), 0, gray.shape[1] - 1)
    ys = np.clip((cy + r * np.sin(angles)).astype(int), 0, gray.shape[0] - 1)
    return float(gray[ys, xs].mean())


def segment_iris(eye_bgr):
    """Return dict(gray, pupil=(x,y,r), iris=(x,y,r)) or None if segmentation fails."""
    if eye_bgr is None or eye_bgr.size == 0:
        return None
    g = cv2.cvtColor(eye_bgr, cv2.COLOR_BGR2GRAY)
    scale = 240.0 / max(g.shape)
    g = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    blur = cv2.GaussianBlur(g, (7, 7), 0)

    # pupil = darkest compact blob
    thr = min(np.percentile(blur, 8), float(blur.min()) + 28.0)
    _, bw = cv2.threshold(blur, thr, 255, cv2.THRESH_BINARY_INV)
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    cnts, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best, best_score = None, 0
    for c in cnts:
        area = cv2.contourArea(c)
        if area < 40:
            continue
        (x, y), r = cv2.minEnclosingCircle(c)
        circ = area / (np.pi * r * r + 1e-6)
        if circ > best_score and r > 4:
            best, best_score = (x, y, r), circ
    if best is None or best_score < 0.5:
        return None
    px, py, pr = best

    # refine centre by centroid of the blob, then iris radius = max radial gradient (integro-differential)
    ang = np.linspace(-np.pi / 4, np.pi / 4, 24)
    ang = np.concatenate([ang, ang + np.pi])  # left/right sectors avoid eyelids
    radii = np.arange(int(pr * 1.4), int(min(pr * 4.5, min(g.shape) / 2 - 2)))
    if len(radii) < 6:
        return None
    prof = np.array([_circle_mean(blur, px, py, r, ang) for r in radii])
    d = np.gradient(cv2.GaussianBlur(prof.reshape(-1, 1), (1, 5), 0).ravel())
    ir = float(radii[int(np.argmax(d))])
    if ir < pr * 1.5:
        ir = pr * 2.6
    return {"gray": g, "pupil": (px, py, pr), "iris": (px, py, ir)}


def quality_check(seg):
    """Quality in [0,1] from focus, pupil/iris geometry, contrast and occlusion."""
    if seg is None:
        return 0.0, ["iris not found"]
    g = seg["gray"]
    px, py, pr = seg["pupil"]
    _, _, ir = seg["iris"]
    reasons = []
    yy, xx = np.indices(g.shape)
    rr = np.hypot(xx - px, yy - py)
    ring = (rr > pr * 1.1) & (rr < ir)
    if ring.sum() < 200:
        return 0.0, ["iris region too small"]
    focus = min(1.0, cv2.Laplacian(g, cv2.CV_64F)[ring].var() / 120.0)
    contrast = min(1.0, (g[ring].mean() - g[rr < pr * 0.8].mean()) / 50.0)
    ratio = pr / ir
    geom = 1.0 if 0.2 <= ratio <= 0.65 else 0.4
    inside = (px - ir > 0) and (py - ir * 0.6 > -ir) and (px + ir < g.shape[1])
    occl = float(((g > 235) & ring).mean())
    q = 0.4 * focus + 0.25 * max(0, contrast) + 0.2 * geom + 0.15 * (1 - min(1, occl * 4))
    if not inside:
        q *= 0.6
        reasons.append("iris partially outside frame")
    if focus < 0.25:
        reasons.append("out of focus")
    if contrast < 0.2:
        reasons.append("low pupil/iris contrast")
    if geom < 1:
        reasons.append("implausible pupil/iris ratio")
    return float(np.clip(q, 0, 1)), reasons


# ------------------------------------------------------------------ normalisation & encoding
def normalize(seg):
    g = seg["gray"]
    px, py, pr = seg["pupil"]
    _, _, ir = seg["iris"]
    theta = np.linspace(0, 2 * np.pi, COLS, endpoint=False)
    rho = np.linspace(0.05, 0.95, ROWS)[:, None]
    r = pr + rho * (ir - pr)
    mx = (px + r * np.cos(theta)[None, :]).astype(np.float32)
    my = (py + r * np.sin(theta)[None, :]).astype(np.float32)
    polar = cv2.remap(g, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    valid = (mx >= 0) & (mx < g.shape[1]) & (my >= 0) & (my < g.shape[0])
    # eyelid mask: keep left/right sectors only (|sin(theta)| < 0.75), drop reflections / dark lashes
    sector = (np.abs(np.sin(theta)) < 0.75)[None, :]
    mask = valid & sector & (polar < 235) & (polar > 15)
    return polar, mask.astype(np.uint8)


def encode(polar, mask):
    img = cv2.equalizeHist(polar).astype(np.float32)
    img = (img - img.mean(axis=1, keepdims=True)) / (img.std(axis=1, keepdims=True) + 1e-6)
    pad = np.concatenate([img[:, -8:], img, img[:, :8]], axis=1)  # circular padding
    bits = np.zeros(CODE_SHAPE, np.uint8)
    for i, k in enumerate(_gabor):
        resp = cv2.filter2D(pad, cv2.CV_32F, k)[:, 8:-8]
        bits[:, :, i] = (resp > 0)
    m = np.repeat(mask[:, :, None], 2, axis=2).astype(np.uint8)
    return bits, m


def generate_template(eye_bgr):
    """Full pipeline. Returns dict(code, mask, quality, reasons) or dict(error=...)."""
    seg = segment_iris(eye_bgr)
    q, reasons = quality_check(seg)
    if seg is None:
        return {"error": "Iris segmentation failed", "quality": 0.0, "reasons": reasons}
    polar, mask = normalize(seg)
    code, m = encode(polar, mask)
    return {"code": code, "mask": m, "quality": q, "reasons": reasons}


# ------------------------------------------------------------------ matching
def hamming_distance(code_a, mask_a, code_b, mask_b):
    """Fractional HD with circular shifts to compensate head/eye rotation. Lower = more similar."""
    best = 0.5
    for s in range(-MAX_SHIFT, MAX_SHIFT + 1):
        cb, mb = np.roll(code_b, s, axis=1), np.roll(mask_b, s, axis=1)
        valid = mask_a.astype(bool) & mb.astype(bool)
        n = valid.sum()
        if n < 0.2 * code_a.size:
            continue
        hd = ((code_a != cb) & valid).sum() / n
        best = min(best, float(hd))
    return best


def hd_to_score(hd, threshold=0.35, k=30.0):
    """Calibrated confidence in [0,1]; equals 0.5 at the HD threshold."""
    return float(1.0 / (1.0 + np.exp((hd - threshold) * k)))
