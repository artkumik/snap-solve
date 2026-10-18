"""Read handwritten math from cropped line images with the fine-tuned TexTeller model.

The model is the checkpoint train_texteller.py saves as <out_dir>/best: the epoch with the
lowest validation token error rate. Images are prepared and decoded exactly as they were
for that validation (TexTeller's own preprocessing, greedy decoding, the same token limit
and mixed precision on a GPU), so the site gets the accuracy measured during training.

Settings, read from .env or the environment:
    TEXTELLER_MODEL_DIR  folder with the fine-tuned model
                         (default: checkpoints/texteller_mixed/best)
    TEXTELLER_DEVICE     cuda or cpu (default: cuda whenever PyTorch can see a GPU)

Recognition needs the packages in requirements-training.txt. Without them, or without the
model folder, the site keeps working: it still finds the lines but can't read them.
"""
import contextlib
import logging
import os
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DEFAULT_MODEL_DIR = BASE_DIR / "checkpoints" / "texteller_mixed" / "best"
MAX_NEW_TOKENS = 256  # train_texteller.py validates with --max_new_tokens 256
BATCH_SIZE = 8        # lines read together; most photos have fewer than this

# uvicorn prints this logger's INFO messages, so the console shows where the model loaded.
log = logging.getLogger("uvicorn.error")

_lock = threading.Lock()  # one load at a time, and one batch on the model at a time
_model: dict = {}         # filled once loading succeeds
_unavailable = ""         # why recognition is off, once loading has failed


def model_dir() -> Path:
    path = Path(os.getenv("TEXTELLER_MODEL_DIR") or DEFAULT_MODEL_DIR)
    return path if path.is_absolute() else BASE_DIR / path


def load() -> bool:
    """Load the model the first time it's needed. Returns False if recognition is off."""
    global _unavailable
    with _lock:
        if _model:
            return True
        if _unavailable:
            return False
        try:
            _model.update(_load())
            return True
        except Exception as exc:  # missing packages or model, out of GPU memory, ...
            _unavailable = str(exc) or type(exc).__name__
            log.warning("Handwriting recognition is off: %s", _unavailable)
            return False


def recognition_available() -> bool:
    return load()


def _load() -> dict:
    path = model_dir()
    if not (path / "config.json").is_file():
        raise FileNotFoundError(
            f"no fine-tuned model in {path}. Train one with train_texteller.py, or point "
            "TEXTELLER_MODEL_DIR in .env at the model's folder")
    try:
        import torch
        from transformers import GenerationConfig
        from texteller import load_model, load_tokenizer
        from texteller.utils import transform
    except ImportError as exc:
        raise RuntimeError(
            f"{exc}. Install the model packages with: "
            "python -m pip install -r requirements-training.txt") from exc

    wanted = (os.getenv("TEXTELLER_DEVICE") or "").strip().lower()
    if wanted not in ("", "cuda", "cpu"):
        log.warning("Ignoring TEXTELLER_DEVICE=%s; use cuda or cpu.", wanted)
    if wanted == "cuda" and not torch.cuda.is_available():
        log.warning("TEXTELLER_DEVICE is cuda, but PyTorch can't see a GPU; using the CPU.")
    device = torch.device("cuda" if wanted != "cpu" and torch.cuda.is_available() else "cpu")

    started = time.perf_counter()
    # Loading prints both full model configs as warnings; they're expected, so hide them.
    logging.getLogger("transformers.models.vision_encoder_decoder").setLevel(logging.ERROR)
    model = load_model(str(path)).to(device).eval()
    tokenizer = load_tokenizer(str(path))
    if device.type == "cuda":
        # Same mixed precision as validation during training (bf16 where the GPU has it).
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        precision = lambda: torch.autocast(device_type="cuda", dtype=dtype)  # noqa: E731
    else:
        precision = contextlib.nullcontext
    generation = GenerationConfig(
        max_new_tokens=MAX_NEW_TOKENS,
        num_beams=1,
        do_sample=False,
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id,
        bos_token_id=tokenizer.bos_token_id,
    )
    where = torch.cuda.get_device_name(device) if device.type == "cuda" else "CPU"
    log.info("Handwriting model loaded from %s on %s in %.0f s.", path, where,
             time.perf_counter() - started)
    if device.type == "cpu":
        log.info("Reading on the CPU is slower; a CUDA build of PyTorch uses the GPU.")
    return {"torch": torch, "model": model, "tokenizer": tokenizer, "device": device,
            "transform": transform, "precision": precision, "generation": generation}


def read_equations(images: list[Image.Image]) -> list[str]:
    """LaTeX for each cropped line image, in order; "" for a line that can't be read."""
    results = [""] * len(images)
    if not images or not load():
        return results
    torch, model, tokenizer = _model["torch"], _model["model"], _model["tokenizer"]

    # TexTeller's preprocessing: trim the background border, grayscale, fit to 448 px, pad.
    prepared = []
    for index, image in enumerate(images):
        try:
            prepared.append((index, _model["transform"]([image.convert("RGB")])[0]))
        except Exception:  # e.g. a blank crop with nothing to trim down to
            log.debug("Skipping line %d: TexTeller can't prepare it.", index + 1)

    with _lock, torch.inference_mode():
        for start in range(0, len(prepared), BATCH_SIZE):
            batch = prepared[start:start + BATCH_SIZE]
            pixel_values = torch.stack([pixels for _, pixels in batch]).to(_model["device"])
            try:
                with _model["precision"]():
                    output = model.generate(pixel_values, generation_config=_model["generation"])
            except RuntimeError:  # e.g. out of GPU memory; the other batches can still be read
                log.exception("The handwriting model failed on a batch of %d lines.", len(batch))
                continue
            for (index, _), text in zip(batch, tokenizer.batch_decode(output, skip_special_tokens=True)):
                results[index] = text.strip()
    return results
