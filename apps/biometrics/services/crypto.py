"""Encryption-at-rest for biometric templates (Fernet / AES-128-CBC + HMAC)."""
import base64
import hashlib
import numpy as np
from cryptography.fernet import Fernet
from django.conf import settings

_fernet = None


def _get():
    global _fernet
    if _fernet is None:
        key = settings.BIOMETRIC_ENCRYPTION_KEY
        if not key:  # dev fallback: derive from SECRET_KEY (set a real key in production!)
            key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest()).decode()
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt_bytes(b: bytes) -> bytes:
    return _get().encrypt(b)


def decrypt_bytes(b) -> bytes:
    return _get().decrypt(bytes(b))


def encrypt_vector(v: np.ndarray) -> bytes:
    return encrypt_bytes(np.asarray(v, dtype=np.float32).tobytes())


def decrypt_vector(b) -> np.ndarray:
    return np.frombuffer(decrypt_bytes(b), dtype=np.float32)


def encrypt_bits(bits: np.ndarray) -> bytes:
    return encrypt_bytes(np.packbits(bits.astype(np.uint8).ravel()).tobytes())


def decrypt_bits(b, n_bits: int) -> np.ndarray:
    return np.unpackbits(np.frombuffer(decrypt_bytes(b), dtype=np.uint8))[:n_bits].astype(np.uint8)
