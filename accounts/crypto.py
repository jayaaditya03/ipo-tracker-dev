"""
Symmetric encryption for PAN numbers.

A PAN is personally identifiable information. Storing it in plaintext in a
project you push to a public repo is the kind of thing a reviewer notices,
so it is encrypted at rest with Fernet (AES-128-CBC + HMAC authentication,
from the `cryptography` library).

Encryption alone would make lookups impossible — Fernet output is
randomised, so the same PAN encrypts to different bytes every time and you
cannot query by it. So we store two columns:

    pan_encrypted : the reversible ciphertext (for jobs that need the PAN)
    pan_hash      : a deterministic SHA-256 digest (for uniqueness + lookup)

The hash is salted with SECRET_KEY so a stolen database can't be matched
against a precomputed table of all possible PANs — the format only has
about 2.8 billion combinations, which is brute-forceable in minutes.
"""

import hashlib
import hmac

from cryptography.fernet import Fernet
from django.conf import settings


def _fernet() -> Fernet:
    return Fernet(settings.FIELD_ENCRYPTION_KEY.encode())


def encrypt_pan(pan: str) -> bytes:
    """Encrypt a PAN for storage. Returns ciphertext bytes."""
    return _fernet().encrypt(pan.strip().upper().encode())


def decrypt_pan(token: bytes) -> str:
    """Recover the plaintext PAN from stored ciphertext."""
    if isinstance(token, memoryview):      # psycopg returns memoryview
        token = token.tobytes()
    return _fernet().decrypt(token).decode()


def hash_pan(pan: str) -> str:
    """
    Deterministic keyed digest of a PAN, for uniqueness constraints and
    lookups. HMAC rather than a bare sha256 so the digest cannot be
    reproduced without SECRET_KEY.
    """
    normalised = pan.strip().upper().encode()
    return hmac.new(
        settings.SECRET_KEY.encode(),
        normalised,
        hashlib.sha256,
    ).hexdigest()


def mask_pan(pan: str) -> str:
    """ABCDE1234F -> XXXXX1234F. What the API returns to the client."""
    pan = pan.strip().upper()
    return "X" * 5 + pan[5:] if len(pan) == 10 else "X" * len(pan)