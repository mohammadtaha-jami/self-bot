"""Benchmark ParsBERT ONNX inference latency, throughput, and peak RAM."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.ai_engine import IntentClassifier, get_classifier  # noqa: E402

DATASET_PATH = ROOT / "doc" / "telegram_persian_dataset.jsonl"
SAMPLE_COUNT = 500
WARMUP_COUNT = 20
TARGET_P95_MS = 30.0
TARGET_PEAK_MB = 500.0

FALLBACK_TEXTS = [
    "استخدام ادمین حرفه‌ای اینستاگرام، تمام‌وقت، حقوق توافقی + بیمه.",
    "برنامه‌نویس بک‌اند هستم با ۲ سال تجربه. آماده همکاری پروژه‌ای هستم.",
    "سلام بچه‌ها کسی میدونه بهترین لپ‌تاپ برای ادیت ویدیو چیه؟",
    "نیازمند یک متخصص سئو برای بهبود رتبه سایت فروشگاهی هستیم.",
    "فروش ویژه فالوور اینستاگرام + لایک ایرانی، تحویل فوری.",
]


def _load_texts(limit: int) -> list[str]:
    texts: list[str] = []
    if DATASET_PATH.is_file():
        with DATASET_PATH.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = (payload.get("text") or "").strip()
                if text:
                    texts.append(text)
                if len(texts) >= limit:
                    break
    if not texts:
        texts = list(FALLBACK_TEXTS)
    if len(texts) < limit:
        repeats, remainder = divmod(limit, len(texts))
        texts = texts * repeats + texts[:remainder]
    return texts[:limit]


def _rss_mb(process: psutil.Process) -> float:
    return process.memory_info().rss / (1024 * 1024)


def main() -> int:
    texts = _load_texts(SAMPLE_COUNT)
    process = psutil.Process()
    baseline_mb = _rss_mb(process)
    peak_mb = baseline_mb

    classifier = get_classifier()
    if classifier is not IntentClassifier():
        raise RuntimeError("IntentClassifier singleton was not reused")

    print(f"Warming up ({WARMUP_COUNT} runs)...")
    for text in texts[:WARMUP_COUNT]:
        classifier.predict(text)
        peak_mb = max(peak_mb, _rss_mb(process))

    print(f"Benchmarking {SAMPLE_COUNT} sequential messages...")
    latencies: list[float] = []
    started = time.perf_counter()
    for text in texts:
        result = classifier.predict(text)
        latencies.append(float(result.latency_ms))
        peak_mb = max(peak_mb, _rss_mb(process))
    elapsed_s = time.perf_counter() - started
    peak_mb = max(peak_mb, _rss_mb(process))

    values = np.asarray(latencies, dtype=np.float64)
    mean_ms = float(values.mean())
    min_ms = float(values.min())
    p95_ms = float(np.percentile(values, 95))
    rps = SAMPLE_COUNT / elapsed_s if elapsed_s else 0.0
    after_mb = _rss_mb(process)

    print()
    print("=== ONNX IntentClassifier benchmark ===")
    print(f"messages          : {SAMPLE_COUNT}")
    print(f"mean latency      : {mean_ms:.2f} ms")
    print(f"min latency       : {min_ms:.2f} ms")
    print(f"p95 latency       : {p95_ms:.2f} ms  (target < {TARGET_P95_MS:.0f} ms)")
    print(f"throughput        : {rps:.1f} msg/s")
    print(f"RAM baseline      : {baseline_mb:.1f} MB")
    print(f"RAM after run     : {after_mb:.1f} MB")
    print(f"RAM peak          : {peak_mb:.1f} MB  (target < {TARGET_PEAK_MB:.0f} MB)")
    print(
        f"p95 target        : {'PASS' if p95_ms < TARGET_P95_MS else 'MISS'}"
    )
    print(
        f"memory target     : {'PASS' if peak_mb < TARGET_PEAK_MB else 'MISS'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
