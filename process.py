from PIL import Image, ImageOps

from equation_cropper.crop_equations import equation_boxes
from parse import parse_image_lines
from recognizer import read_equations
from videos import find_videos


def split_image_lines(
    image: Image.Image, *, threshold: int = 190, gap: int = 18, padding: int = 12
) -> list[dict]:
    """Find line rectangles, numbered top to bottom, and read each one as LaTeX.

    Bounds are normalized to the upright image: left/right are fractions of its
    width, top/bottom of its height. No images are written to disk. Intended for
    dark writing on a light, single-column background; increase gap to keep
    vertically separated symbols, such as fractions, together. The crops are read
    together by the fine-tuned TexTeller model (recognizer.py).
    """
    if not 1 <= threshold <= 255 or gap < 1 or padding < 0:
        raise ValueError("Use threshold 1–255, gap >= 1, and padding >= 0.")
    working_image = ImageOps.exif_transpose(image).convert("RGB")
    boxes = sorted(equation_boxes(working_image, threshold=threshold, gap=gap, padding=padding),
                   key=lambda box: box[1])
    crops = [working_image.crop(box) for box in boxes]
    try:
        equations = read_equations(crops)
    finally:
        for crop in crops:
            crop.close()
    lines = []
    for number, ((left, top, right, bottom), equation) in enumerate(zip(boxes, equations), 1):
        lines.append({
            "line": number,
            "data": equation,
            "bounds": {
                "left": left / working_image.width,
                "top": top / working_image.height,
                "right": right / working_image.width,
                "bottom": bottom / working_image.height,
            },
        })
    return lines


def process_image(image: Image.Image, question: str = "") -> dict:
    """Detect/crop lines, extract LaTeX, and delegate checking/context to parse.py."""
    result = parse_image_lines(split_image_lines(image), question)
    # Gemini suggests a search phrase along with the problem context; turn it into videos.
    query = (result.get("context") or {}).get("video_query") or ""
    result.update({
        "success": True,
        "mode": "line_detection",
        "videos": find_videos(query),
    })
    return result
