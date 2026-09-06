"""Tokenizer wrapper for ParsBERT ONNX inference — skeleton."""

from __future__ import annotations


class Tokenizer:
    """Loads tokenizer files from AI_MODEL_DIR. Implementation comes in Phase 7.4."""

    def encode(self, text: str) -> dict:
        raise NotImplementedError(
            "Tokenizer.encode will be implemented in Phase 7.4"
        )
