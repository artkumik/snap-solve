# convert the parquet files into jpgs and create the csv to run training with
import glob, os
import pandas as pd
from PIL import Image

# Point this at your parquet file(s); the test split may be sharded into several files
files = sorted(glob.glob("data/mathwriting_val/MathVal.parquet"))
df = pd.concat(
    [pd.read_parquet(f, columns=["image", "latex", "sample_id"]) for f in files],
    ignore_index=True,
)
print(f"{len(df)} train examples found")

# Fixed seed = the exact same 1000 images every time (needed for before/after comparison)
sample = df.sample(n=400, random_state=42).reset_index(drop=True)

out = "data/mathwriting_val"
os.makedirs(f"{out}/images", exist_ok=True)

rows = []
for r in sample.itertuples():
    fn = f"{r.sample_id}.jpg"
    with open(f"{out}/images/{fn}", "wb") as fh:
        fh.write(r.image["bytes"])  # raw JPEG bytes -> .jpg file
    rows.append({"filename": fn, "latex": r.latex})

pd.DataFrame(rows).to_csv(f"{out}/labels.csv", index=False)

# Sanity check: confirm the first few images actually decode
for fn in [r["filename"] for r in rows[:5]]:
    Image.open(f"{out}/images/{fn}").verify()
print("Done. Saved", len(rows), "images.")