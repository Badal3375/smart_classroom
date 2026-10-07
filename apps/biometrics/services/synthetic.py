"""Deterministic synthetic faces / eyes used by Demo Mode (no camera or datasets needed).
Each identity (seed) has stable structure; each `variant` adds sensor noise + small pose/lighting change."""
import cv2
import numpy as np


def _rng(x):
    return np.random.RandomState(int(x) % (2**32 - 1))


def synth_face(seed, variant=0, size=160):
    rs = _rng(seed * 7919 + 13)
    img = np.full((size, size, 3), rs.randint(60, 120), np.uint8)
    skin = tuple(int(c) for c in rs.randint(120, 220, 3))
    cx, cy = size // 2, size // 2
    cv2.ellipse(img, (cx, cy), (rs.randint(48, 62), rs.randint(60, 72)), 0, 0, 360, skin, -1)
    for _ in range(14):  # identity-specific blotches / features
        x, y = rs.randint(25, size - 25, 2)
        a, b = rs.randint(4, 18, 2)
        col = tuple(int(c) for c in rs.randint(30, 240, 3))
        cv2.ellipse(img, (int(x), int(y)), (int(a), int(b)), int(rs.randint(0, 180)), 0, 360, col, -1)
    ey, ed = rs.randint(55, 70), rs.randint(22, 34)
    for sx in (-1, 1):
        cv2.circle(img, (cx + sx * ed, ey), int(rs.randint(5, 9)), (20, 20, 20), -1)
    cv2.line(img, (cx, ey + 8), (cx + int(rs.randint(-6, 6)), ey + 30), (60, 60, 60), 2)
    cv2.ellipse(img, (cx, ey + 45), (int(rs.randint(10, 24)), int(rs.randint(4, 10))), 0, 0, 180, (40, 40, 160), 2)
    vr = _rng(seed * 104729 + variant * 31 + 5)
    M = np.float32([[1, 0, vr.uniform(-2, 2)], [0, 1, vr.uniform(-2, 2)]])
    img = cv2.warpAffine(img, M, (size, size), borderMode=cv2.BORDER_REPLICATE)
    img = np.clip(img.astype(np.float32) * vr.uniform(0.93, 1.07) + vr.normal(0, 4.0, img.shape), 0, 255).astype(np.uint8)
    return img


def synth_eye(seed, variant=0, size=240):
    rs = _rng(seed * 6007 + 3)
    img = np.full((size, size, 3), 225, np.uint8)  # sclera
    c = size // 2
    ir = rs.randint(62, 74)
    pr = int(ir * rs.uniform(0.3, 0.42))
    base = rs.randint(95, 150)
    yy, xx = np.indices((size, size))
    rr, th = np.hypot(xx - c, yy - c), np.arctan2(yy - c, xx - c)
    tex = np.zeros((size, size), np.float32)
    for k in range(1, 9):  # identity-specific radial / angular texture ("crypts, furrows")
        ph, am, fr = rs.uniform(0, 6.28), rs.uniform(8, 22), rs.randint(3, 18)
        tex += am * np.sin(fr * th + ph + rs.uniform(0, 3) * rr / ir)
    tex += rs.uniform(10, 25) * np.sin(rs.randint(2, 6) * rr / 5.0)
    field = cv2.GaussianBlur(rs.normal(0, 1, (24, 192)).astype(np.float32), (0, 0), 0.8) * 70  # identity-specific "crypt" pattern
    ci = ((th + np.pi) / (2 * np.pi) * 191).astype(int).clip(0, 191)
    ri = (rr / ir * 23).astype(int).clip(0, 23)
    tex += field[ri, ci]
    iris = np.clip(base + tex, 55, 230)
    gray = np.full((size, size), 225, np.float32)
    ring = (rr <= ir) & (rr > pr)
    gray[ring] = iris[ring]
    gray[rr <= pr] = 12
    gray = cv2.GaussianBlur(gray, (0, 0), 0.9)
    vr = _rng(seed * 15485863 + variant * 17 + 1)
    gray = np.clip(gray + vr.normal(0, 2.5, gray.shape), 0, 255)
    # eyelid shadows (top/bottom), small specular highlight
    gray[: c - int(ir * 1.05)] = np.minimum(gray[: c - int(ir * 1.05)], 140)
    gray[c + int(ir * 1.05):] = np.minimum(gray[c + int(ir * 1.05):], 140)
    cv2.circle(gray, (c - int(pr * 0.5), c - int(pr * 0.5)), 3, 250, -1)
    out = cv2.cvtColor(gray.astype(np.uint8), cv2.COLOR_GRAY2BGR)
    M = cv2.getRotationMatrix2D((c, c), vr.uniform(-1, 1), 1.0)  # slight head tilt
    return cv2.warpAffine(out, M, (size, size), borderMode=cv2.BORDER_REPLICATE)


def degrade_face(img, level=1.0):
    """Simulate low-confidence face capture (partial occlusion e.g. mask / hand) so iris fallback is exercised."""
    out = img.copy()
    h, w = out.shape[:2]
    cv2.rectangle(out, (0, int(h * (0.82 - 0.03 * level))), (w, h), (128, 128, 128), -1)
    return out


def make_spoof(img):
    """Simulate a replay attack: low-res re-capture of a screen => blur + regular pixel-grid pattern."""
    h, w = img.shape[:2]
    small = cv2.resize(img, (w // 3, h // 3))
    out = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR).astype(np.float32)
    grid = 14 * np.sin(np.arange(w) * 2 * np.pi / 4.0)[None, :, None] * np.sin(np.arange(h) * 2 * np.pi / 4.0)[:, None, None]
    return np.clip(out + grid + 25, 0, 255).astype(np.uint8)
