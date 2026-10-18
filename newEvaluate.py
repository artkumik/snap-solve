import argparse
import csv
import time
from pathlib import Path

import torch
from texteller import load_model, load_tokenizer, img2latex

from latex_metrics import edit_distance, strip_delims, tokens


def pick_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.version.cuda is None:
        print("WARNING: this PyTorch build is CPU-only, so the GPU can't be used. Reinstall it "
              "with CUDA (see 'Training and evaluation' in README.md).")
    else:
        print("WARNING: PyTorch has CUDA support but can't see a GPU. Check `nvidia-smi` and "
              "update the NVIDIA driver.")
    return torch.device("cpu")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default="data/mathwriting_test/labels.csv")
    p.add_argument("--images", default=None, help="Image folder (default: images/ next to the CSV)")
    p.add_argument("--model-dir", default=None, help="Path to fine-tuned model (default: pretrained)")
    p.add_argument("--out", default="predictions_baseline.csv")
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--limit", type=int, default=None, help="Only evaluate first N rows")
    args = p.parse_args()

    device = pick_device()
    print(f"Device: {device}" + (f" ({torch.cuda.get_device_name(device)})" if device.type == "cuda" else ""))

    model = load_model(model_dir=args.model_dir).to(device).eval()
    tokenizer = load_tokenizer(args.model_dir)

    with open(args.csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if args.limit:
        rows = rows[: args.limit]

    img_dir = Path(args.images) if args.images else Path(args.csv).parent / "images"
    missing = [r["filename"] for r in rows if not (img_dir / r["filename"]).exists()]
    for name in missing:
        print(f"Missing: {img_dir / name}")
    rows = [r for r in rows if (img_dir / r["filename"]).exists()]
    if not rows:
        raise SystemExit(f"No images to evaluate (looked in {img_dir}).")

    results = []
    start = time.time()
    for i in range(0, len(rows), args.batch_size):
        batch = rows[i : i + args.batch_size]
        paths = [str(img_dir / r["filename"]) for r in batch]
        try:
            with torch.inference_mode():
                preds = img2latex(model, tokenizer, paths, device=device, out_format="latex")
        except Exception as e:
            print(f"Batch failed ({e}); retrying one at a time")
            preds = []
            for path in paths:
                try:
                    with torch.inference_mode():
                        preds.append(img2latex(model, tokenizer, [path], device=device, out_format="latex")[0])
                except Exception as e2:
                    print(f"  Failed {path}: {e2}")
                    preds.append("")

        for r, pred in zip(batch, preds):
            gt = r["latex"]
            gt_n, pred_n = tokens(gt), tokens(pred)
            ned = edit_distance(pred_n, gt_n) / max(len(gt_n), 1)
            results.append({
                "filename": r["filename"],
                "ground_truth": gt,
                "prediction": pred,
                "exact_raw": int("".join(strip_delims(gt).split()) == "".join(strip_delims(pred).split())),
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