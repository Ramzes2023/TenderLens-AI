"""Dependency-free deterministic text vectors for the local RAG MVP.

This is a lightweight hashing embedder, not a semantic foundation model. The
RAG interfaces deliberately keep it replaceable by GigaChat/Yandex/other
embedding providers later without changing Telegram or storage code.
"""
from __future__ import annotations

import hashlib
import math
import re

_TOKEN = re.compile(r"[\w]+", re.UNICODE)


class HashEmbeddingProvider:
    def __init__(self, dimensions: int = 512):
        if dimensions < 64:
            raise ValueError("dimensions must be >= 64")
        self.dimensions = dimensions

    @staticmethod
    def _features(text: str) -> list[str]:
        lowered = text.casefold()
        tokens = _TOKEN.findall(lowered)
        features: list[str] = []
        for token in tokens:
            features.append("w:" + token)
            # Prefix and character n-grams make Russian inflection and related forms
            # more likely to meet in the same vector bucket.
            if len(token) >= 5:
                features.append("p:" + token[:5])
            padded = f"^{token}$"
            if len(padded) >= 4:
                features.extend("c:" + padded[i:i + 4] for i in range(len(padded) - 3))
        return features

    def embed(self, text: str) -> tuple[float, ...]:
        vector = [0.0] * self.dimensions
        for feature in self._features(text):
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            number = int.from_bytes(digest, "big")
            index = number % self.dimensions
            sign = -1.0 if number & (1 << 63) else 1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return tuple(vector)
