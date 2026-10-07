"""Basic passive anti-spoofing (print / screen replay) checks on a single frame.

Signals (each scaled to [0,1], 1 = looks live):
  sharpness : photos of photos / low-res replays are blurry
  moire     : screens & printed halftones produce strong periodic peaks in the FFT spectrum
  glare     : screen replays often show large saturated regions
  texture   : natural skin has fine high-frequency texture; flat prints/screens lack it
Not a replacement for hardware PAD (IR / depth) but a sound academic baseline.
"""
import cv2
import numpy as np


def check_liveness(face_bgr):
    gray = cv2.cvtColor(cv2.resize(face_bgr, (128, 128)), cv2.COLOR_BGR2GRAY).astype(np.float32)
    lap = cv2.Laplacian(gray, cv2.CV_32F).var()
    sharp = float(np.clip(lap / 80.0, 0, 1))

    win = np.hanning(128)[:, None] * np.hanning(128)[None, :]
    spec = np.abs(np.fft.fftshift(np.fft.fft2((gray - gray.mean()) * win)))
    yy, xx = np.indices(spec.shape)
    r = np.hypot(yy - 64, xx - 64)
    band = spec[(r > 12) & (r < 60)]
    peak_ratio = float(band.max() / (np.median(band) + 1e-6))
    moire = float(np.clip(1.0 - (peak_ratio - 25) / 60.0, 0, 1))

    glare = float(np.clip(1.0 - (gray > 245).mean() / 0.05, 0, 1))

    hf = gray - cv2.GaussianBlur(gray, (0, 0), 1.5)
    tex = float(np.clip(hf.std() / 3.0, 0, 1))

    score = 0.3 * sharp + 0.3 * moire + 0.15 * glare + 0.25 * tex
    is_live = bool(score >= 0.55 and moire >= 0.4)
    return {"is_live": is_live, "score": round(float(score), 3),
            "sharpness": round(sharp, 3), "moire": round(moire, 3),
            "glare": round(glare, 3), "texture": round(tex, 3)}
