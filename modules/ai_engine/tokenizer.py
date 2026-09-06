"""Tokenizer wrapper for ParsBERT ONNX inference."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

import numpy as np
from tokenizers import Tokenizer as HFTokenizer

DEFAULT_MAX_LENGTH = 128


class EncodedBatch(TypedDict):
    input_ids: np.ndarray
    attention_mask: np.ndarray


def _read_max_length(model_dir: Path) -> int:
    config_path = model_dir / "tokenizer_config.json"
    if not config_path.is_file():
        return DEFAULT_MAX_LENGTH
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_MAX_LENGTH
    value = data.get("max_length")
    if isinstance(value, int) and 0 < value < 10_000:
        return value
    return DEFAULT_MAX_LENGTH


class Tokenizer:
    """Loads tokenizer.json and encodes text for the ONNX session."""

    def __init__(self, model_dir: str | Path) -> None:
        model_dir = Path(model_dir)
        tokenizer_path = model_dir / "tokenizer.json"
        if not tokenizer_path.is_file():
            raise FileNotFoundError(f"tokenizer.json not found in {model_dir}")

        self.max_length = _read_max_length(model_dir)
        self._tokenizer = HFTokenizer.from_file(str(tokenizer_path))
        self._tokenizer.enable_truncation(max_length=self.max_length)
        self._tokenizer.enable_padding(
            length=self.max_length,
            pad_id=0,
            pad_token="[PAD]",
        )

    def encode(self, text: str) -> EncodedBatch:
        encoding = self._tokenizer.encode(text or "")
        return {
            "input_ids": np.asarray([encoding.ids], dtype=np.int64),
            "attention_mask": np.asarray([encoding.attention_mask], dtype=np.int64),
        }
