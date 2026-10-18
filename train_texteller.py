"""
train_texteller.py

Fine-tune the pretrained TexTeller model (OleehyO/TexTeller) on handwritten
math images, validating after every epoch.

Expected layout:
    data/mathwriting_train/images/<file>.jpg
    data/mathwriting_train/labels.csv        (columns: filename,latex)
    data/mathwriting_val/images/<file>.jpg
    data/mathwriting_val/labels.csv

Example (single line on Windows):
    python train_texteller.py --train_dir data/mathwriting_train --val_dir data/mathwriting_val --out_dir checkpoints/texteller_mw --epochs 15

Requires: texteller, torch, torchvision, transformers, pillow, numpy,
          editdistance, tqdm

The best checkpoint (lowest validation token error rate) is saved to
<out_dir>/best and can be reloaded with:
    from texteller import load_model, load_tokenizer
    model = load_model("<out_dir>/best")
    tokenizer = load_tokenizer("<out_dir>/best")
"""
import argparse
import csv
import json
import math
import random
import time
from pathlib import Path

import editdistance
import numpy as np
import torch
from PIL import Image, ImageOps
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms as T
from tqdm import tqdm
from transformers import GenerationConfig, get_cosine_schedule_with_warmup

from texteller import load_model, load_tokenizer
from texteller.utils import transform as texteller_transform  # TexTeller's own preprocessing

from latex_metrics import tokens  # same normalization as newEvaluate.py


# --------------------------------------------------------------------------
# Metrics (identical normalization for baseline and every checkpoint)
# --------------------------------------------------------------------------
def compute_metrics(preds, truths):
    dists, lens = [], []
    for p, t in zip(preds, truths):
        tp, tt = tokens(p), tokens(t)
        dists.append(editdistance.eval(tp, tt))
        lens.append(max(len(tt), 1))
    d, n = np.array(dists), np.array(lens)
    return {
        "ExpRate": float(np.mean(d == 0)),
        "ExpRate<=1": float(np.mean(d <= 1)),
        "ExpRate<=2": float(np.mean(d <= 2)),
        "TokenErrorRate": float(d.sum() / n.sum()),
        "MeanNormEdit": float(np.mean(d / n)),
    }, dists


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------
def load_rgb(path: Path) -> Image.Image:
    """Open as RGB, compositing any transparency onto white."""
    img = Image.open(path)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img)
    return img.convert("RGB")


def _pad_white(img: Image.Image) -> Image.Image:
    # Pad first so rotation/scaling never clips strokes; TexTeller's transform
    # trims the white border again afterwards, so the padding is free.
    pad = max(8, int(0.1 * max(img.size)))
    return ImageOps.expand(img, border=pad, fill=(255, 255, 255))


AUGMENT = T.Compose(
    [
        T.Lambda(_pad_white),
        T.RandomApply(
            [
                T.RandomAffine(
                    degrees=3,
                    translate=(0.02, 0.02),
                    scale=(0.85, 1.1),
                    shear=(-5, 5, -2, 2),
                    fill=(255, 255, 255),
                )
            ],
            p=0.7,
        ),
        T.RandomApply([T.ColorJitter(brightness=0.3, contrast=0.3)], p=0.5),
        T.RandomApply([T.GaussianBlur(kernel_size=3, sigma=(0.1, 1.2))], p=0.3),
    ]
)


class FormulaDataset(Dataset):
    def __init__(self, split_dirs, repeats=None, augment=False, name=""):
        """split_dirs: list of folders, each with images/ and labels.csv.
        repeats: how many times to include each folder (oversampling; with
        augmentation on, every repeat is augmented differently)."""
        repeats = repeats or [1] * len(split_dirs)
        self.items = []  # (image_path, latex, source_folder_name)
        for d, rep_n in zip(split_dirs, repeats):
            d = Path(d)
            img_dir, missing, rows = d / "images", 0, []
            with open(d / "labels.csv", newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    p = img_dir / row["filename"]
                    if p.exists() and row["latex"].strip():
                        rows.append((p, row["latex"], d.name))
                    else:
                        missing += 1
            if missing:
                print(f"[{name}:{d.name}] skipped {missing} rows (missing image or empty label)")
            self.items.extend(rows * rep_n)
            print(f"[{name}:{d.name}] {len(rows)} images x{rep_n}")
        self.augment = augment

    def drop_unusable(self, name=""):
        """Remove images that TexTeller's preprocessing can't handle (e.g. blank)."""
        keep, ok = [], {}
        for p, l, s in tqdm(self.items, desc=f"Checking {name} images"):
            if p not in ok:
                try:
                    texteller_transform([load_rgb(p)])
                    ok[p] = True
                except Exception:
                    ok[p] = False
            if ok[p]:
                keep.append((p, l, s))
        if len(keep) < len(self.items):
            print(f"[{name}] dropped {len(self.items) - len(keep)} unusable images")
        self.items = keep

    def drop_long(self, tokenizer, max_len, name=""):
        """Training labels longer than max_len would be truncated into wrong targets."""
        lengths = [len(x) for x in tokenizer([l for _, l, _ in self.items])["input_ids"]]
        keep = [it for it, n in zip(self.items, lengths) if n <= max_len]
        if len(keep) < len(self.items):
            print(f"[{name}] dropped {len(self.items) - len(keep)} labels longer than {max_len} tokens")
        self.items = keep

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        path, latex, _ = self.items[i]
        img = load_rgb(path)
        if self.augment:
            img = AUGMENT(img)
        pixel_values = texteller_transform([img])[0]  # (1, 448, 448) float32
        return pixel_values, latex


class Collate:
    """Batch builder. A class rather than a nested function so DataLoader workers can
    pickle it: on Windows, workers are separate processes and nested functions can't be sent."""

    def __init__(self, tokenizer, max_len):
        self.tokenizer, self.max_len = tokenizer, max_len

    def __call__(self, batch):
        tokenizer = self.tokenizer
        pixel_values = torch.stack([b[0] for b in batch])
        latex = [b[1] for b in batch]
        enc = tokenizer(
            latex, padding=True, truncation=True, max_length=self.max_len, return_tensors="pt"
        )
        ids, mask = enc["input_ids"], enc["attention_mask"]
        # Decoder input:  <s> t1 ... tn </s> <pad>...
        # Labels (shifted left by one): t1 ... tn </s> -100 ...
        labels = torch.full_like(ids, -100)
        labels[:, :-1] = ids[:, 1:]
        labels[labels == tokenizer.pad_token_id] = -100
        return {
            "pixel_values": pixel_values,
            "decoder_input_ids": ids,
            "decoder_attention_mask": mask,
            "labels": labels,
            "latex": latex,
        }


# --------------------------------------------------------------------------
# Train / eval
# --------------------------------------------------------------------------
def forward_loss(model, batch, device):
    return model(
        pixel_values=batch["pixel_values"].to(device),
        decoder_input_ids=batch["decoder_input_ids"].to(device),
        decoder_attention_mask=batch["decoder_attention_mask"].to(device),
        labels=batch["labels"].to(device),
    ).loss


@torch.no_grad()
def evaluate(model, tokenizer, loader, device, amp_ctx, max_new_tokens):
    model.eval()
    gen_cfg = GenerationConfig(
        max_new_tokens=max_new_tokens,
        num_beams=1,
        do_sample=False,
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id,
        bos_token_id=tokenizer.bos_token_id,
    )
    loss_sum, tok_count = 0.0, 0
    preds, truths = [], []
    for batch in tqdm(loader, desc="Validating", leave=False):
        with amp_ctx():
            loss = forward_loss(model, batch, device)
        n = int((batch["labels"] != -100).sum())
        loss_sum += loss.item() * n
        tok_count += n
        with amp_ctx():
            out = model.generate(batch["pixel_values"].to(device), generation_config=gen_cfg)
        preds += tokenizer.batch_decode(out, skip_special_tokens=True)
        truths += batch["latex"]
    metrics, dists = compute_metrics(preds, truths)
    metrics["val_loss"] = loss_sum / max(tok_count, 1)
    return metrics, preds, truths, dists


def save_predictions(path, items, preds, truths, dists):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source", "filename", "truth", "pred", "token_edit_dist"])
        for (p, _, src), pr, t, d in zip(items, preds, truths, dists):
            w.writerow([src, p.name, t, pr, d])


def per_source_metrics(preds, truths, items):
    """Metrics for each source folder (val items are in the same order as preds)."""
    out = {}
    for src in sorted({s for _, _, s in items}):
        idx = [i for i, (_, _, s) in enumerate(items) if s == src]
        m, _ = compute_metrics([preds[i] for i in idx], [truths[i] for i in idx])
        m["n"] = len(idx)
        out[src] = m
    return out


def print_sources(ps):
    if len(ps) < 2:
        return
    for src, m in ps.items():
        print(
            f"    {src:<24} n={m['n']:<5} ExpRate {m['ExpRate'] * 100:5.1f}% | "
            f"<=1 {m['ExpRate<=1'] * 100:5.1f}% | TER {m['TokenErrorRate'] * 100:5.1f}%"
        )

def fmt(m):
    return (
        f"loss {m['val_loss']:.4f} | ExpRate {m['ExpRate'] * 100:.1f}% | "
        f"<=1 {m['ExpRate<=1'] * 100:.1f}% | TER {m['TokenErrorRate'] * 100:.1f}%"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train_dir", nargs="+", default=["data/mathwriting_train"],
                    help="one or more training folders (each with images/ and labels.csv)")
    ap.add_argument("--train_repeat", nargs="+", type=int, default=None,
                    help="repeat count per training folder, e.g. 1 5 to oversample the second")
    ap.add_argument("--val_dir", nargs="+", default=["data/mathwriting_val"],
                    help="one or more validation folders")
    ap.add_argument("--out_dir", default="checkpoints/texteller_mathwriting")
    ap.add_argument("--epochs", type=int, default=15)
    ap.add_argument("--batch_size", type=int, default=8)
    ap.add_argument("--eval_batch_size", type=int, default=16)
    ap.add_argument("--grad_accum", type=int, default=2)
    ap.add_argument("--lr", type=float, default=5e-5)
    ap.add_argument("--weight_decay", type=float, default=0.01)
    ap.add_argument("--warmup_ratio", type=float, default=0.05)
    ap.add_argument("--max_len", type=int, default=256, help="max label tokens for training")
    ap.add_argument("--max_new_tokens", type=int, default=256, help="max tokens generated at eval")
    ap.add_argument("--patience", type=int, default=4, help="early-stop after N epochs w/o improvement (0 = off)")
    ap.add_argument("--workers", type=int, default=2, help="DataLoader workers (use 0 if you hit Windows issues)")
    ap.add_argument("--amp", choices=["auto", "bf16", "fp16", "none"], default="auto")
    ap.add_argument("--freeze_encoder", action="store_true", help="train only the decoder (less memory, faster)")
    ap.add_argument("--no_augment", action="store_true")
    ap.add_argument("--skip_baseline", action="store_true", help="skip the epoch-0 evaluation of the pretrained model")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # ---- mixed precision ----
    amp = args.amp
    if amp == "auto":
        if device.type == "cuda":
            amp = "bf16" if torch.cuda.is_bf16_supported() else "fp16"
        else:
            amp = "none"
    if device.type != "cuda":
        amp = "none"
    amp_dtype = torch.bfloat16 if amp == "bf16" else torch.float16
    amp_ctx = lambda: torch.autocast(device_type=device.type, dtype=amp_dtype, enabled=amp != "none")
    scaler = torch.amp.GradScaler("cuda", enabled=(amp == "fp16"))

    # ---- model / tokenizer ----
    print("Loading pretrained TexTeller...")
    model = load_model().to(device)
    tokenizer = load_tokenizer()

    probe = tokenizer("x")["input_ids"]
    if probe[0] != tokenizer.bos_token_id or probe[-1] != tokenizer.eos_token_id:
        raise RuntimeError("Tokenizer does not wrap sequences in <s> ... </s>; collate logic needs adjusting.")
    if model.config.decoder_start_token_id is None:
        model.config.decoder_start_token_id = tokenizer.bos_token_id
    elif model.config.decoder_start_token_id != tokenizer.bos_token_id:
        print(
            f"Warning: decoder_start_token_id ({model.config.decoder_start_token_id}) "
            f"!= tokenizer bos ({tokenizer.bos_token_id})"
        )

    if args.freeze_encoder:
        for p in model.encoder.parameters():
            p.requires_grad = False
    params = [p for p in model.parameters() if p.requires_grad]
    print(
        f"Device {device} | AMP {amp} | params {sum(p.numel() for p in model.parameters()) / 1e6:.0f}M "
        f"(trainable {sum(p.numel() for p in params) / 1e6:.0f}M)"
    )

    # ---- data ----
    if args.train_repeat and len(args.train_repeat) != len(args.train_dir):
        raise SystemExit("--train_repeat needs one number per --train_dir folder")
    train_ds = FormulaDataset(args.train_dir, args.train_repeat, augment=not args.no_augment, name="train")
    val_ds = FormulaDataset(args.val_dir, augment=False, name="val")
    train_ds.drop_unusable("train")
    val_ds.drop_unusable("val")
    train_ds.drop_long(tokenizer, args.max_len, "train")
    print(f"Train: {len(train_ds)} images | Val: {len(val_ds)} images")

    if not len(train_ds) or not len(val_ds):
        raise SystemExit("Training and validation sets both need at least one usable image.")
    collate = Collate(tokenizer, args.max_len)
    pin = device.type == "cuda"
    train_loader = DataLoader(
        train_ds, batch_size=args.batch_size, shuffle=True, num_workers=args.workers,
        collate_fn=collate, pin_memory=pin, persistent_workers=args.workers > 0,
    )
    val_loader = DataLoader(
        val_ds, batch_size=args.eval_batch_size, shuffle=False, num_workers=args.workers,
        collate_fn=Collate(tokenizer, 1024), pin_memory=pin, persistent_workers=args.workers > 0,
    )

    # ---- optimizer / schedule ----
    opt = torch.optim.AdamW(params, lr=args.lr, weight_decay=args.weight_decay)
    steps_per_epoch = math.ceil(len(train_loader) / args.grad_accum)
    total_steps = steps_per_epoch * args.epochs
    sched = get_cosine_schedule_with_warmup(opt, int(args.warmup_ratio * total_steps), total_steps)

    history = []
    best_ter, best_epoch, bad_epochs = float("inf"), 0, 0

    def save_best(epoch, metrics, preds, truths, dists):
        model.save_pretrained(out_dir / "best")
        tokenizer.save_pretrained(out_dir / "best")
        save_predictions(out_dir / "val_predictions_best.csv", val_ds.items, preds, truths, dists)
        with open(out_dir / "best_metrics.json", "w") as f:
            json.dump({"epoch": epoch, **metrics}, f, indent=2)

    # ---- epoch 0: baseline of the untouched pretrained model ----
    if not args.skip_baseline:
        m, preds, truths, dists = evaluate(model, tokenizer, val_loader, device, amp_ctx, args.max_new_tokens)
        print(f"[baseline, epoch 0] {fmt(m)}")
        ps = per_source_metrics(preds, truths, val_ds.items)
        print_sources(ps)
        history.append({"epoch": 0, "train_loss": None, **m, "per_source": ps})
        with open(out_dir / "baseline_metrics.json", "w") as f:
            json.dump(m, f, indent=2)
        save_predictions(out_dir / "val_predictions_baseline.csv", val_ds.items, preds, truths, dists)
        best_ter, best_epoch = m["TokenErrorRate"], 0
        save_best(0, m, preds, truths, dists)  # so "best" always exists

    # ---- training ----
    for epoch in range(1, args.epochs + 1):
        model.train()
        t0 = time.time()
        running, seen = 0.0, 0
        opt.zero_grad(set_to_none=True)
        pbar = tqdm(train_loader, desc=f"Epoch {epoch}/{args.epochs}")
        for step, batch in enumerate(pbar):
            with amp_ctx():
                loss = forward_loss(model, batch, device)
            scaler.scale(loss / args.grad_accum).backward()
            running += loss.item()
            seen += 1
            if (step + 1) % args.grad_accum == 0 or step + 1 == len(train_loader):
                scaler.unscale_(opt)
                torch.nn.utils.clip_grad_norm_(params, 1.0)
                scaler.step(opt)
                scaler.update()
                sched.step()
                opt.zero_grad(set_to_none=True)
            pbar.set_postfix(loss=f"{running / seen:.4f}", lr=f"{sched.get_last_lr()[0]:.2e}")

        m, preds, truths, dists = evaluate(model, tokenizer, val_loader, device, amp_ctx, args.max_new_tokens)
        train_loss = running / max(seen, 1)
        print(f"[epoch {epoch}] train loss {train_loss:.4f} | val {fmt(m)} | {time.time() - t0:.0f}s")
        ps = per_source_metrics(preds, truths, val_ds.items)
        print_sources(ps)
        history.append({"epoch": epoch, "train_loss": train_loss, **m, "per_source": ps})
        with open(out_dir / "history.json", "w") as f:
            json.dump(history, f, indent=2)

        if m["TokenErrorRate"] < best_ter:
            best_ter, best_epoch, bad_epochs = m["TokenErrorRate"], epoch, 0
            save_best(epoch, m, preds, truths, dists)
            print(f"  -> new best (TER {best_ter * 100:.1f}%), saved to {out_dir / 'best'}")
        else:
            bad_epochs += 1
            if args.patience and bad_epochs >= args.patience:
                print(f"No improvement for {args.patience} epochs; stopping early.")
                break

    # ---- summary ----
    print(f"\nBest epoch: {best_epoch}  (validation TER {best_ter * 100:.1f}%)")
    if history and history[0]["epoch"] == 0:
        b = history[0]
        best = next(h for h in history if h["epoch"] == best_epoch)
        print(f"{'':<16}{'baseline':>10}{'best':>10}")
        for k in ["ExpRate", "ExpRate<=1", "ExpRate<=2", "TokenErrorRate"]:
            print(f"{k:<16}{b[k] * 100:>9.1f}%{best[k] * 100:>9.1f}%")
    print(f"Checkpoint: {out_dir / 'best'}")
    print("Note: validation was used to pick this checkpoint, so report final numbers on the held-out test set.")


if __name__ == "__main__":
    main()