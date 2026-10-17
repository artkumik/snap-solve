from PIL import Image, ImageOps

from equation_cropper.crop_equations import equation_boxes


def read_equation(line_image: Image.Image) -> str:
    """Placeholder for reading one cropped equation. No recognition yet."""
    return ""


def check_equation(equation: str) -> bool | None:
    """Placeholder for checking an equation. None means not checked."""
    return None


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
    upright = ImageOps.exif_transpose(image).convert("RGBA")
    paper = Image.new("RGB", upright.size, "white")
    paper.paste(upright, mask=upright.getchannel("A"))
    boxes = equation_boxes(paper, threshold=threshold, gap=gap, padding=padding)
    lines = []
    for number, (left, top, right, bottom) in enumerate(sorted(boxes, key=lambda box: box[1]), 1):
        with paper.crop((left, top, right, bottom)) as line_image:
            equation = read_equation(line_image)
        lines.append({
            "line": number,
            "latex": equation,
            "valid": check_equation(equation),
            "error": None,
            "follows_from_previous": None,
            "bounds": {
                "left": left / paper.width,
                "top": top / paper.height,
                "right": right / paper.width,
                "bottom": bottom / paper.height,
            },
        })
    return lines


def process_image(image: Image.Image, question: str = "") -> dict:
    """Detect actual image lines only; recognition and math checking are disabled."""
    return {
        "success": True,
        "mode": "line_detection",
        "context": None,
        "lines": split_image_lines(image),
        "final_correct": None,
        "videos": [],
    }
