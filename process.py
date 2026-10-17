from PIL import Image

from parse import parse_image_lines


def read_lines(image: Image.Image) -> list[dict]:
    """Turn the image into lines of LaTeX, e.g. [{"data": "x^2 = 3x"}, {"data": "x = 3"}].

    TODO: replace this placeholder with the real handwriting reader.
    When you do, bump RESULT_VERSION in static/upload.js so old saved results are redone.
    """
    return [{"data": "x^2 = 3x"}, {"data": "x = 3"}]


def process_image(image: Image.Image, question: str = "") -> dict | None:
    lines = read_lines(image)
    if not lines:
        return None
    return parse_image_lines(lines, question)
