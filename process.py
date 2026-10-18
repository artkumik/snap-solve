from PIL import Image, ImageOps

from equation_cropper.crop_equations import equation_boxes
from parse import parse_image_lines


def read_equation(line_image: Image.Image) -> str:
    """Placeholder for extracting LaTeX from a cropped line; no recognition yet."""
    return ""


def split_image_lines(
    image: Image.Image, *, threshold: int = 190, gap: int = 18, padding: int = 12
) -> list[dict]:
    """Find line rectangles, numbered top to bottom, without reading equations.

    Bounds are normalized to the upright image: left/right are fractions of its
    width, top/bottom of its height. No images are written to disk. Intended for
    dark writing on a light, single-column background; increase gap to keep
    vertically separated symbols, such as fractions, together.
    """
    if not 1 <= threshold <= 255 or gap < 1 or padding < 0:
        raise ValueError("Use threshold 1–255, gap >= 1, and padding >= 0.")
    working_image = ImageOps.exif_transpose(image).convert("RGB")
    boxes = equation_boxes(working_image, threshold=threshold, gap=gap, padding=padding)
    lines = []
    for number, (left, top, right, bottom) in enumerate(sorted(boxes, key=lambda box: box[1]), 1):
        with working_image.crop((left, top, right, bottom)) as line_image:
            equation = read_equation(line_image)
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
    result.update({
        "success": True,
        "mode": "line_detection",
        "videos": [],
    })
    return result
