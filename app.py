from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageOps, UnidentifiedImageError

from process import process_image

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = None
app = FastAPI()
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.post("/upload")
def upload_image(request: Request, image: UploadFile):
    try:
        if image.size is not None and image.size > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Image must be 10 MB or smaller.")

        try:
            with Image.open(image.file) as uploaded:
                if uploaded.format not in {"JPEG", "PNG", "WEBP", "JPG"}:
                    raise HTTPException(415, "Choose a JPEG, PNG, or WebP image.")

                uploaded.load()
                normalized = ImageOps.exif_transpose(uploaded).convert("RGBA")

        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise HTTPException(400, "Invalid image.") from exc

        image_id = uuid4()
        image_path = UPLOAD_DIR / f"{image_id}.png"

        try:
            print("processing image")
            normalized.save(image_path, format="PNG")
            process_image(image_path)
        except Exception:
            image_path.unlink(missing_ok=True)
            raise
        finally:
            normalized.close()
        return RedirectResponse(
            request.url_for("upload_result", image_id=str(image_id)), status_code=303
        )
    finally:
        image.file.close()


@app.get("/results/{image_id}")
def upload_result(request: Request, image_id: UUID):
    filename = f"{image_id}.png"

    if not (UPLOAD_DIR / filename).is_file():
        raise HTTPException(404, "Uploaded image not found.")

    return templates.TemplateResponse(
        request=request, name="result.html", context={"filename": filename}
    )

