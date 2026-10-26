"""Reproduce the small French ASR evaluation reported with EkaVani.

Example (PowerShell, from the EkaVani-final project root):
    python whisper_cv_eval_seed42.py --dataset-dir ..\french_dataset_50mb
"""
import argparse
import csv
import random
import re
import unicodedata
from importlib.metadata import version
from pathlib import Path

import numpy as np
import whisper


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for i, ref_token in enumerate(reference, 1):
        current = [i]
        for j, hyp_token in enumerate(hypothesis, 1):
            current.append(min(
                current[-1] + 1,
                previous[j] + 1,
                previous[j - 1] + (ref_token != hyp_token),
            ))
        previous = current
    return previous[-1]


def main() -> None:
    default_data_dir = Path(__file__).resolve().parent.parent / "french_dataset_50mb"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=default_data_dir)
    parser.add_argument("--sample-size", type=int, default=25)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--bootstrap-replicates", type=int, default=10_000)
    args = parser.parse_args()

    with (args.dataset_dir / "metadata.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if args.sample_size > len(rows):
        raise SystemExit(f"Requested {args.sample_size} clips, but metadata has {len(rows)} rows")
    sample = random.Random(args.seed).sample(rows, args.sample_size)

    model = whisper.load_model("base", device="cpu")
    errors, reference_lengths = [], []
    for row in sample:
        audio_path = args.dataset_dir / row["filename"]
        if not audio_path.is_file():
            raise SystemExit(f"Missing audio file: {audio_path}")
        reference = normalize(row["sentence"]).split()
        hypothesis_text = model.transcribe(
            str(audio_path),
            language="fr",
            fp16=False,
            temperature=0,
            beam_size=5,
            condition_on_previous_text=False,
            verbose=False,
        )["text"]
        hypothesis = normalize(hypothesis_text).split()
        errors.append(edit_distance(reference, hypothesis))
        reference_lengths.append(len(reference))

    wer = sum(errors) / sum(reference_lengths)
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
    print("sampled_files=" + ",".join(row["filename"] for row in sample))


if __name__ == "__main__":
    main()
