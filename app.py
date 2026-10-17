from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageOps, UnidentifiedImageError

from process import process_image

BASE_DIR = Path(__file__).resolve().parent
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
app = FastAPI()
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.post("/upload")
async def upload_image(request: Request):
    # Read raw image bytes with a bound; multipart UploadFile can spill to disk.
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Image must be 10 MB or smaller.")
        data.extend(chunk)

    try:
        with Image.open(BytesIO(data)) as uploaded:
            if uploaded.format not in {"JPEG", "PNG", "WEBP"}:
                raise HTTPException(415, "Choose a JPEG, PNG, or WebP image.")
            uploaded.load()
            normalized = ImageOps.exif_transpose(uploaded).convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(400, "Invalid image.") from exc

    try:
        return {"result": await run_in_threadpool(process_image, normalized)}
    finally:
        normalized.close()
