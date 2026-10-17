import argparse
import csv
import re
import time
from pathlib import Path

import torch
from texteller import load_model, load_tokenizer, img2latex

TOKEN_RE = re.compile(r"\\[a-zA-Z]+|\\.|\S")
NOISE_RE = re.compile(r"\\(?:displaystyle|left|right|quad|qquad)(?![a-zA-Z])|\\[,;:! ]")


def tokenize(s: str) -> list[str]:
    return TOKEN_RE.findall(s)


def strip_delims(s: str) -> str:
    s = s.strip()
    for left, right in (("$$", "$$"), ("\\[", "\\]"), ("$", "$")):
        if s.startswith(left) and s.endswith(right) and len(s) > len(left) + len(right):
            return s[len(left):-len(right)].strip()
    return s


def normalize(s: str) -> list[str]:
    return tokenize(NOISE_RE.sub(" ", strip_delims(s)))


def edit_distance(a: list[str], b: list[str]) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default=r"data\mathwriting_test\labels.csv")
    p.add_argument("--images", default=r"data\mathwriting_test\images")
    p.add_argument("--model-dir", default=None, help="Path to fine-tuned model (default: pretrained)")
    p.add_argument("--out", default="predictions_baseline.csv")
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--limit", type=int, default=None, help="Only evaluate first N rows")
    args = p.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    model = load_model(model_dir=args.model_dir) if args.model_dir else load_model()
    tokenizer = load_tokenizer(args.model_dir) if args.model_dir else load_tokenizer()

    with open(args.csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if args.limit:
        rows = rows[: args.limit]

    img_dir = Path(args.images)
    rows = [r for r in rows if (img_dir / r["filename"]).exists() or print(f"Missing: {r['filename']}")]

    results = []
    start = time.time()
    for i in range(0, len(rows), args.batch_size):
        batch = rows[i : i + args.batch_size]
        paths = [str(img_dir / r["filename"]) for r in batch]
        try:
            preds = img2latex(model, tokenizer, paths, device=device, out_format="latex")
        except Exception as e:
            print(f"Batch failed ({e}); retrying one at a time")
            preds = []
            for path in paths:
                try:
                    preds.append(img2latex(model, tokenizer, [path], device=device, out_format="latex")[0])
                except Exception as e2:
                    print(f"  Failed {path}: {e2}")
                    preds.append("")

        for r, pred in zip(batch, preds):
            gt = r["latex"]
            gt_n, pred_n = normalize(gt), normalize(pred)
            ned = edit_distance(pred_n, gt_n) / max(len(gt_n), 1)
            results.append({
                "filename": r["filename"],
                "ground_truth": gt,
                "prediction": pred,
                "exact_raw": int("".join(gt.split()) == "".join(strip_delims(pred).split())),
                "exact_norm": int(gt_n == pred_n),
                "token_edit_dist": round(ned, 4),
            })
        print(f"{len(results)}/{len(rows)} done ({time.time() - start:.0f}s)")

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=results[0].keys())
        w.writeheader()
        w.writerows(results)

    n = len(results)
    print("\n===== Results =====")
    print(f"Images evaluated:          {n}")
    print(f"Exact match (raw):         {sum(r['exact_raw'] for r in results) / n:.2%}")
    print(f"Exact match (normalized):  {sum(r['exact_norm'] for r in results) / n:.2%}")
    print(f"Mean token edit distance:  {sum(r['token_edit_dist'] for r in results) / n:.4f}")
    print(f"Predictions saved to:      {args.out}")


if __name__ == "__main__":
    main()