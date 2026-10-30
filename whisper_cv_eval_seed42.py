"""Reproduce the small French ASR evaluation reported with EkaVani.

Example (PowerShell, from the EkaVani-final project root):
    python whisper_cv_eval_seed42.py --dataset-dir ..\french_dataset_50mb
"""
import argparse
import csv
import json
import random
from importlib.metadata import version
from pathlib import Path
import sys
from datetime import datetime, timezone

import numpy as np
import whisper

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
from app.learning import word_errors


def main() -> None:
    default_data_dir = Path(__file__).resolve().parent.parent / "french_dataset_50mb"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=default_data_dir)
    parser.add_argument("--sample-size", type=int, default=25)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--bootstrap-replicates", type=int, default=10_000)
    parser.add_argument(
        "--report-json",
        type=Path,
        default=Path(__file__).resolve().parent / "backend" / "app" / "data" / "asr_benchmark.json",
    )
    args = parser.parse_args()

    with (args.dataset_dir / "metadata.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if args.sample_size > len(rows):
        raise SystemExit(f"Requested {args.sample_size} clips, but metadata has {len(rows)} rows")
    sample = random.Random(args.seed).sample(rows, args.sample_size)

    model = whisper.load_model("base", device="cpu")
    errors, reference_lengths = [], []
    word_true_positives = word_false_positives = word_false_negatives = 0
    character_edits = reference_characters = 0
    for row in sample:
        audio_path = args.dataset_dir / row["filename"]
        if not audio_path.is_file():
            raise SystemExit(f"Missing audio file: {audio_path}")
        hypothesis_text = model.transcribe(
            str(audio_path),
            language="fr",
            fp16=False,
            temperature=0,
            beam_size=5,
            condition_on_previous_text=False,
            verbose=False,
        )["text"]
        metrics = word_errors(row["sentence"], hypothesis_text)
        errors.append(metrics["word_error_count"])
        reference_lengths.append(metrics["reference_words"])
        word_true_positives += metrics["word_true_positives"]
        word_false_positives += metrics["word_false_positives"]
        word_false_negatives += metrics["word_false_negatives"]
        character_edits += metrics["character_edits"]
        reference_characters += metrics["reference_characters"]

    wer = sum(errors) / sum(reference_lengths)
    precision = word_true_positives / max(word_true_positives + word_false_positives, 1)
    recall = word_true_positives / max(word_true_positives + word_false_negatives, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-12)
    cer = character_edits / max(reference_characters, 1)
    rng = np.random.default_rng(args.seed)
    bootstrap_wers = []
    for _ in range(args.bootstrap_replicates):
        indices = rng.integers(0, args.sample_size, size=args.sample_size)
        bootstrap_wers.append(
            sum(errors[i] for i in indices) / sum(reference_lengths[i] for i in indices)
        )
    low, high = np.percentile(bootstrap_wers, [2.5, 97.5])

    print(f"dataset_rows={len(rows)} sample_n={args.sample_size} speakers={len({r['client_id'] for r in sample})}")
    print(f"model=Whisper base; package_version={version('openai-whisper')}")
    print(f"sample_seed={args.seed}; bootstrap_seed={args.seed}; bootstrap_n={args.bootstrap_replicates}")
    print(f"word_errors={sum(errors)} reference_words={sum(reference_lengths)} WER={wer:.6f} bootstrap_95_CI=[{low:.6f}, {high:.6f}]")
    print(f"micro_word_precision={precision:.6f} micro_word_recall={recall:.6f} micro_word_F1={f1:.6f}")
    print(f"character_edits={character_edits} reference_characters={reference_characters} CER={cer:.6f}")
    print("sampled_files=" + ",".join(row["filename"] for row in sample))

    report = {
        "dataset": args.dataset_dir.name,
        "dataset_clips": len(rows),
        "sample_size": len(sample),
        "speaker_count": len({row["client_id"] for row in sample}),
        "model": "Whisper base",
        "package_version": version("openai-whisper"),
        "sample_seed": args.seed,
        "bootstrap_replicates": args.bootstrap_replicates,
        "word_error_rate": wer,
        "word_precision": precision,
        "word_recall": recall,
        "word_f1": f1,
        "character_error_rate": cer,
        "word_error_ci_95": [float(low), float(high)],
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "ASR transcript text comparison with corpus references; not phoneme, accent, or emotion accuracy.",
    }
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"report_json={args.report_json}")


if __name__ == "__main__":
    main()
