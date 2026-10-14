"""Cryptographic Routine and Algorithm entity."""

from dataclasses import dataclass, field
from enum import Enum


class CryptoAlgorithm(str, Enum):
    AES_CBC = "AES/CBC/PKCS5Padding"
    AES_GCM = "AES/GCM/NoPadding"
    RSA = "RSA"
    HMAC_SHA256 = "HmacSHA256"
    MD5 = "MD5"
    SHA256 = "SHA256"
    CUSTOM = "CUSTOM"


@dataclass(frozen=True)
class CryptoRoutine:
    """Represents an extracted signing, hashing, or encryption routine."""

    name: str
    algorithm: CryptoAlgorithm
    source_location: str
    key_candidates: list[str] = field(default_factory=list)
    iv_candidates: list[str] = field(default_factory=list)
    input_parameters: list[str] = field(default_factory=list)
    code_snippet: str | None = None
