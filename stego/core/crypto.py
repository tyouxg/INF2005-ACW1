"""Hashing, Ed25519 signatures, AES-GCM and key derivation."""

import hashlib
import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

SIG_LEN = 64
# Fixed app salt for the stego key. The receiver has to derive the start
# location before reading anything, so there's nowhere to store a random salt.
STEGO_SALT = b"INF2005-ACW1/stego-key/v1"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- signing keys ---

def generate_keypair() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def save_keypair(priv: Ed25519PrivateKey, folder) -> tuple[Path, Path]:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    priv_path, pub_path = folder / "private_key.pem", folder / "public_key.pem"
    priv_path.write_bytes(priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    pub_path.write_bytes(priv.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    return priv_path, pub_path


def load_private_key(path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(Path(path).read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Expected an Ed25519 private key")
    return key


def load_public_key(path) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(Path(path).read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("Expected an Ed25519 public key")
    return key


def public_key_fingerprint(pub: Ed25519PublicKey) -> str:
    raw = pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return sha256_hex(raw)[:16]


def sign(priv: Ed25519PrivateKey, data: bytes) -> bytes:
    return priv.sign(data)


def verify(pub: Ed25519PublicKey, sig: bytes, data: bytes) -> bool:
    try:
        pub.verify(sig, data)
        return True
    except InvalidSignature:
        return False


# --- stego key derivation ---

def master_key(passphrase: str) -> bytes:
    # scrypt makes brute-forcing a weak passphrase slow
    kdf = Scrypt(salt=STEGO_SALT, length=32, n=2**14, r=8, p=1)
    return kdf.derive(passphrase.encode("utf-8"))


def subkey(master: bytes, label: str, length: int = 32, salt: bytes | None = None) -> bytes:
    hkdf = HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=label.encode())
    return hkdf.derive(master)


def derive_start(master: bytes, carrier_len: int, kind: str) -> int:
    # Tied to the carrier length, so the same key lands somewhere different in
    # each file, and a cropped/trimmed file no longer lines up.
    raw = subkey(master, f"start/{kind}/{carrier_len}", 8)
    return int.from_bytes(raw, "big") % carrier_len


# --- confidentiality for the custom payload ---

def encrypt(master: bytes, plaintext: bytes, aad: bytes = b"") -> dict:
    salt, nonce = os.urandom(16), os.urandom(12)
    key = subkey(master, "aes-gcm", 32, salt)
    ct = AESGCM(key).encrypt(nonce, plaintext, aad)
    return {"salt": salt.hex(), "nonce": nonce.hex(), "ct": ct.hex()}


def decrypt(master: bytes, blob: dict, aad: bytes = b"") -> bytes | None:
    key = subkey(master, "aes-gcm", 32, bytes.fromhex(blob["salt"]))
    try:
        return AESGCM(key).decrypt(bytes.fromhex(blob["nonce"]), bytes.fromhex(blob["ct"]), aad)
    except InvalidTag:
        return None
