"""Turn MathWriting parquet file(s) into an images/ folder + labels.csv for training/eval.

Example:
    python mathwriting_prep.py "data/mathwriting_val/*.parquet" data/mathwriting_val --count 400

The output folder gets images/<sample_id>.<ext> and labels.csv (columns: filename,latex),
the layout newEvaluate.py and train_texteller.py expect.
"""
import argparse
import glob
import io
from pathlib import Path

import pandas as pd
from PIL import Image

EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("parquet", help="Parquet file or glob, e.g. 'data/mathwriting_val/*.parquet' (quote it)")
    p.add_argument("out", help="Output folder")
    p.add_argument("--count", type=int, default=400, help="Random sample size; 0 = keep every row")
    p.add_argument("--seed", type=int, default=42, help="Fixed seed = the same sample every run")
    args = p.parse_args()

    files = sorted(glob.glob(args.parquet))
    if not files:
        raise SystemExit(f"No parquet files match {args.parquet}")
    df = pd.concat(
        [pd.read_parquet(f, columns=["image", "latex", "sample_id"]) for f in files],
        ignore_index=True,
    )
    print(f"{len(df)} examples found in {len(files)} file(s)")

    # Same seed = the exact same images every time (needed for before/after comparisons).
    if args.count and args.count < len(df):
        df = df.sample(n=args.count, random_state=args.seed)
    df = df.reset_index(drop=True)

    out = Path(args.out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    rows = []
    for r in df.itertuples():
        data = r.image["bytes"]
        with Image.open(io.BytesIO(data)) as img:  # also checks the bytes decode
            img.verify()
            ext = EXTENSIONS.get(img.format, ".png")
        filename = f"{r.sample_id}{ext}"
        (out / "images" / filename).write_bytes(data)
        rows.append({"filename": filename, "latex": r.latex})

    pd.DataFrame(rows).to_csv(out / "labels.csv", index=False)
    print(f"Done. Saved {len(rows)} images to {out / 'images'} and labels to {out / 'labels.csv'}.")


if __name__ == "__main__":
    main()
