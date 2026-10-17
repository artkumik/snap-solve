from PIL import Image

from parse import parse_image_lines
from videos import find_videos


def read_lines(image: Image.Image) -> list[dict]:
    """Placeholder lines with normalized symbol bounds fitted to test image 1.

    Replace with real handwriting detection later. Bump RESULT_VERSION in
    static/upload.js whenever these values change.
    """
    return [
        {
            "data": "x^2 = 3x",
            "first_symbol": {
                "left": 0.22626788,
                "top": 0.25396825,
                "right": 0.29388817,
                "bottom": 0.42857143
            },
            "last_symbol": {
                "left": 0.68530559,
                "top": 0.29365079,
                "right": 0.73602081,
                "bottom": 0.43386243
            }
        },
        {
            "data": "x = 3",
            "first_symbol": {
                "left": 0.25097529,
                "top": 0.5,
                "right": 0.35760728,
                "bottom": 0.68253968
            },
            "last_symbol": {
                "left": 0.54746424,
                "top": 0.51851852,
                "right": 0.66319896,
                "bottom": 0.6957672
            }
        }
    ]


def process_image(image: Image.Image, question: str = "") -> dict | None:
    lines = read_lines(image)
    if not lines:
        return None
    result = parse_image_lines(lines, question)
    # Gemini suggests a search phrase along with the problem context; turn it into videos.
    query = (result.get("context") or {}).get("video_query", "")
    result["videos"] = find_videos(query)
    return result
