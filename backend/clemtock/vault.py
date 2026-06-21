"""clemtock secret vault — encrypted-at-rest store for API keys / passwords.

Idea borrowed from TheClawFirm/lockbox (Argon2id + ChaCha20-Poly1305). Here we use
**scrypt** (stdlib `hashlib.scrypt`, available on every cryptography version) for the KDF and
**ChaCha20-Poly1305** (AEAD) for encryption. The vault is a single JSON file holding only
salt + nonce + ciphertext; the plaintext (a name->secret map) never touches disk.

Threat model: protects secrets at rest — so they're never sitting in plaintext .env files,
git, logs, or backups. The master passphrase comes from `CLEMTOCK_VAULT_PASSPHRASE` or a
0600 key file (`~/.clemtock/passphrase`), so a headless service on floor2 can self-unlock
while casual disk/repo exposure stays useless. Decrypted values are loaded into the process
env at runtime only (see `apply_to_env`).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets as _sysrandom
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

_REPO = Path(__file__).resolve().parents[2]
DEFAULT_VAULT = Path(os.environ.get("CLEMTOCK_VAULT", str(_REPO / ".vault" / "clemtock.vault")))
DEFAULT_KEYFILE = Path(os.environ.get("CLEMTOCK_VAULT_KEYFILE", str(Path.home() / ".clemtock" / "passphrase")))
_AAD = b"clemtock-vault-v1"
_SCRYPT = {"n": 2 ** 15, "r": 8, "p": 1, "dklen": 32, "maxmem": 132 * 1024 * 1024}


class VaultError(RuntimeError):
    pass


def _b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.b64decode(s)


def ensure_passphrase(create: bool = False) -> bytes:
    """Resolve the master passphrase: env first, then key file. Optionally mint one."""
    env = os.environ.get("CLEMTOCK_VAULT_PASSPHRASE")
    if env:
        return env.encode("utf-8")
    kf = DEFAULT_KEYFILE
    if kf.exists():
        return kf.read_bytes().strip()
    if create:
        kf.parent.mkdir(parents=True, exist_ok=True)
        secret = _sysrandom.token_urlsafe(48)
        kf.write_text(secret)
        os.chmod(kf, 0o600)
        return secret.encode("utf-8")
    raise VaultError(
        f"no passphrase — set CLEMTOCK_VAULT_PASSPHRASE or create {kf} (run `clemtock vault init`)")


def _derive(passphrase: bytes, salt: bytes) -> bytes:
    return hashlib.scrypt(passphrase, salt=salt, **_SCRYPT)


class Vault:
    def __init__(self, path: Path = DEFAULT_VAULT):
        self.path = Path(path)
        self._data: dict[str, str] = {}

    # ---- lifecycle ----
    @classmethod
    def init(cls, path: Path = DEFAULT_VAULT) -> "Vault":
        ensure_passphrase(create=True)
        v = cls(path)
        if not v.path.exists():
            v.save()
        return v

    def load(self) -> "Vault":
        if not self.path.exists():
            raise VaultError(f"vault not found: {self.path} (run `clemtock vault init`)")
        blob = json.loads(self.path.read_text())
        key = _derive(ensure_passphrase(), _b64d(blob["salt"]))
        try:
            pt = ChaCha20Poly1305(key).decrypt(_b64d(blob["nonce"]), _b64d(blob["ct"]), _AAD)
        except Exception as e:  # InvalidTag etc.
            raise VaultError("decrypt failed — wrong passphrase or corrupt vault") from e
        self._data = json.loads(pt.decode("utf-8"))
        return self

    def save(self) -> "Vault":
        salt = _sysrandom.token_bytes(16)
        nonce = _sysrandom.token_bytes(12)
        key = _derive(ensure_passphrase(create=True), salt)
        ct = ChaCha20Poly1305(key).encrypt(nonce, json.dumps(self._data).encode("utf-8"), _AAD)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({
            "version": 1, "kdf": "scrypt", "aead": "chacha20poly1305",
            "salt": _b64e(salt), "nonce": _b64e(nonce), "ct": _b64e(ct),
        }))
        os.chmod(self.path, 0o600)
        return self

    # ---- accessors ----
    def set(self, name: str, value: str) -> None:
        self._data[name] = value

    def get(self, name: str) -> str | None:
        return self._data.get(name)

    def delete(self, name: str) -> bool:
        return self._data.pop(name, None) is not None

    def names(self) -> list[str]:
        return sorted(self._data)

    def apply_to_env(self, override: bool = False) -> int:
        n = 0
        for k, v in self._data.items():
            if override or k not in os.environ:
                os.environ[k] = v
                n += 1
        return n


def apply_to_env(path: Path = DEFAULT_VAULT, override: bool = False) -> int:
    """Best-effort: load the vault into process env. Silent no-op if unavailable.

    Lets `clemtock <cmd>` transparently pick up vault secrets while still falling back to a
    plain environment (e.g. on a dev box without a vault yet).
    """
    try:
        return Vault(path).load().apply_to_env(override=override)
    except (VaultError, Exception):
        return 0
