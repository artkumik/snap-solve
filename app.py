import asyncio
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageOps, UnidentifiedImageError

from process import process_image

BASE_DIR = Path(__file__).resolve().parent
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
# Checked before decoding, so a small file that would decode to a huge image is refused cheaply.
MAX_PIXELS = 20_000_000  # ~5000 x 4000; the site shrinks photos before sending anyway
# Images are shrunk to this longest side before processing; plenty for reading handwriting.
WORK_SIDE = 2048
# How many images may be decoded/processed at once. Each one holds an image in RAM and may
# wait on Gemini, so this keeps memory bounded on a small host. Extra uploads wait their turn.
MAX_CONCURRENT = 4

app = FastAPI()
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
processing_slots = asyncio.Semaphore(MAX_CONCURRENT)


@app.get("/")
def index(request: Request):
    asset_version = max((BASE_DIR / "static" / name).stat().st_mtime_ns
                        for name in ("style.css", "upload.js", "backdrop.js", "resize.js"))
    return templates.TemplateResponse(request=request, name="index.html",
                                      context={"asset_version": asset_version})


def load_image(data: bytes) -> Image.Image:
    """Decode the upload into an upright image no larger than WORK_SIDE on its longest side."""
    try:
        with Image.open(BytesIO(data)) as uploaded:
            if uploaded.format not in {"JPEG", "PNG", "WEBP"}:
                raise HTTPException(415, "Choose a JPEG, PNG, or WebP image.")
            if uploaded.width * uploaded.height > MAX_PIXELS:
                raise HTTPException(413, "Image dimensions are too large.")
            uploaded.draft("RGB", (WORK_SIDE, WORK_SIDE))  # JPEG only: decode at reduced size
            uploaded.load()
            image = ImageOps.exif_transpose(uploaded)
            image.thumbnail((WORK_SIDE, WORK_SIDE))
            return image.convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(400, "Invalid image.") from exc


def handle_upload(data: bytes, question: str):
    image = load_image(data)
    try:
        return process_image(image, question)
    finally:
        image.close()


@app.post("/upload")
async def upload_image(request: Request, question: str = Query(default="", max_length=2000)):
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Image must be 10 MB or smaller.")

    # Read raw image bytes with a bound; multipart UploadFile can spill to disk.
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Image must be 10 MB or smaller.")
        data.extend(chunk)

    # Decoding and processing are slow, blocking work: run them off the event loop so other
    # visitors aren't stuck waiting, and only a few at a time so memory stays bounded.
    async with processing_slots:
        return {"result": await run_in_threadpool(handle_upload, bytes(data), question)}
