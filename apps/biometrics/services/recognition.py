"""Recognition pipeline: frame -> faces -> liveness -> embedding match -> (iris verification) -> fused decision.

Decision logic (multimodal fusion):
  1. face_score >= face_high           -> accept on face alone                  (method "face")
  2. face_low <= face_score < high     -> iris verification of the candidate;
        fused = wf*face + wi*iris ; accept if fused >= fusion_thr and iris >= 0.5  (method "face+iris")
  3. face_score < face_low             -> Unknown person
  Liveness failure always rejects the face as a spoof attempt.
"""
import time
import numpy as np
from django.conf import settings
from django.core.cache import cache

from apps.core import conf
from apps.academics.models import Student
from apps.biometrics.models import FaceEmbedding, IrisTemplate
from . import crypto, face_service as F, iris_service as I, liveness as L, synthetic as S

_GALLERY = {}  # key -> (timestamp, payload)
GALLERY_TTL = 30


def backend():
    return F.available_backend(settings.FACE_BACKEND)


def face_threshold(be=None):
    be = be or backend()
    return conf.get("face_threshold", float) or F.DEFAULT_THRESHOLDS[be]


def invalidate_gallery():
    _GALLERY.clear()


# ------------------------------------------------------------------ galleries
def face_gallery(student_ids):
    key = ("face", backend(), tuple(sorted(student_ids)))
    hit = _GALLERY.get(key)
    if hit and time.time() - hit[0] < GALLERY_TTL:
        return hit[1]
    ids, vecs = [], []
    for fe in FaceEmbedding.objects.filter(student_id__in=student_ids, is_active=True, backend=backend()):
        ids.append(fe.student_id)
        vecs.append(crypto.decrypt_vector(fe.vector))
    payload = (ids, np.vstack(vecs) if vecs else np.zeros((0, 1), np.float32))
    _GALLERY[key] = (time.time(), payload)
    return payload


def iris_templates_for(student_id):
    out = []
    for t in IrisTemplate.objects.filter(student_id=student_id):
        n = I.N_BITS
        out.append((crypto.decrypt_bits(t.code, n).reshape(I.CODE_SHAPE),
                    crypto.decrypt_bits(t.mask, n).reshape(I.CODE_SHAPE)))
    return out


# ------------------------------------------------------------------ enrollment (templates only; no images saved)
def enroll_face(student, frames_bgr, allow_fallback=False):
    saved, rejected = 0, []
    for fr in frames_bgr:
        boxes = F.detect_faces(fr, allow_full_frame_fallback=allow_fallback)
        if not boxes:
            rejected.append("no face detected")
            continue
        face, _ = F.align_face(fr, boxes[0])
        q = F.face_quality(face)
        if q < 0.25:
            rejected.append(f"low quality ({q:.2f})")
            continue
        if conf.get("liveness_enabled", bool) and not L.check_liveness(F.crop_face(fr, boxes[0]))["is_live"]:
            rejected.append("liveness check failed")
            continue
        FaceEmbedding.objects.create(student=student, vector=crypto.encrypt_vector(F.extract_embedding(face, backend())),
                                     backend=backend(), quality=q)
        saved += 1
    invalidate_gallery()
    return saved, rejected


def enroll_iris(student, eye_images_bgr, eye="U"):
    saved, rejected = 0, []
    for img in eye_images_bgr:
        t = I.generate_template(img)
        if "code" not in t:
            rejected.append(t.get("error", "failed"))
            continue
        if t["quality"] < 0.4:
            rejected.append("low iris quality: " + ", ".join(t["reasons"] or ["poor"]))
            continue
        IrisTemplate.objects.create(student=student, eye=eye, code=crypto.encrypt_bits(t["code"]),
                                    mask=crypto.encrypt_bits(t["mask"]), shape="x".join(map(str, I.CODE_SHAPE)), quality=t["quality"])
        saved += 1
    return saved, rejected


def enroll_demo(student, n_face=4):
    """Enrol deterministic synthetic biometrics (Demo Mode)."""
    seed = student.demo_seed or student.pk + 1000
    student.demo_seed = seed
    student.save(update_fields=["demo_seed"])
    student.face_embeddings.all().delete()
    student.iris_templates.all().delete()
    f, fr = enroll_face(student, [S.synth_face(seed, v) for v in range(n_face)], allow_fallback=True)
    i, ir = enroll_iris(student, [S.synth_eye(seed, v) for v in range(2)], eye="R")
    return f, i, fr + ir


# ------------------------------------------------------------------ recognition
def recognize(frame_bgr, candidate_student_ids, eye_images=None, allow_fallback=False):
    """Return a list of per-face result dicts."""
    be = backend()
    thr = face_threshold(be)
    ids, gallery = face_gallery(candidate_student_ids)
    high = conf.get("face_high_confidence", float)
    low = conf.get("face_low_confidence", float)
    hd_thr = conf.get("iris_hd_threshold", float)
    wf, wi = conf.get("fusion_weight_face", float), conf.get("fusion_weight_iris", float)
    fthr = conf.get("fusion_threshold", float)
    live_on = conf.get("liveness_enabled", bool)
    results = []
    for box in F.detect_faces(frame_bgr, allow_full_frame_fallback=allow_fallback)[:10]:  # multi-face
        face, _ = F.align_face(frame_bgr, box)
        res = {"box": box, "status": "unknown", "student_id": None, "face_score": 0.0, "iris_score": None,
               "confidence": 0.0, "method": "", "liveness": None, "message": ""}
        if live_on:
            lv = L.check_liveness(F.crop_face(frame_bgr, box))
            res["liveness"] = lv["score"]
            if not lv["is_live"]:
                res.update(status="spoof", message="Liveness check failed (possible photo/screen replay)")
                results.append(res)
                continue
        if F.face_quality(face) < 0.15:
            res.update(status="low_quality", message="Face quality too low")
            results.append(res)
            continue
        emb = F.extract_embedding(face, be)
        sid, sim, fscore = F.match(emb, ids, gallery, thr) if len(ids) else (None, 0.0, 0.0)
        res["face_score"] = round(fscore, 3)
        if sid is None or fscore < low:
            res.update(status="unknown", message="Face not recognised")
        elif fscore >= high:
            res.update(status="matched", student_id=sid, confidence=round(fscore, 3), method="face")
        else:
            # low-confidence face -> require iris as an additional factor
            iscore = _iris_verify(sid, eye_images, frame_bgr, box, hd_thr)
            res["iris_score"] = None if iscore is None else round(iscore, 3)
            if iscore is None:
                res.update(status="needs_iris", student_id=sid,
                           message="Face confidence low - iris verification required but no usable iris sample")
            else:
                fused = wf * fscore + wi * iscore
                if fused >= fthr and iscore >= 0.5:
                    res.update(status="matched", student_id=sid, confidence=round(fused, 3), method="face+iris")
                else:
                    res.update(status="unknown", message="Face and iris could not jointly verify identity")
        results.append(res)
    return results


def _iris_verify(student_id, eye_images, frame_bgr, box, hd_thr):
    cands = list(eye_images or [])
    if not cands:
        cands = [c for c, _ in I.detect_eyes(frame_bgr, box)]
    probes = []
    for img in cands:
        t = I.generate_template(img)
        if "code" in t and t["quality"] >= 0.4:
            probes.append(t)
    if not probes:
        return None
    stored = iris_templates_for(student_id)
    if not stored:
        return None
    best = min(I.hamming_distance(p["code"], p["mask"], c, m) for p in probes for c, m in stored)
    return I.hd_to_score(best, hd_thr)


# ------------------------------------------------------------------ demo frames
def demo_probe(kind, student=None):
    """Build a synthetic (frame, eye_images) pair. kinds: student | degraded | unknown | spoof."""
    variant = int(time.time() * 1000) % 100000 + 50
    if kind == "unknown":
        seed = 900000 + variant
        return S.synth_face(seed, 1), [S.synth_eye(seed, 1)]
    seed = student.demo_seed
    face, eye = S.synth_face(seed, variant), S.synth_eye(seed, variant)
    if kind == "degraded":
        face = S.degrade_face(face)
    elif kind == "spoof":
        face = S.make_spoof(face)
    return face, [eye]
