"""Run with: python equation_cropper/check_cropper.py"""

from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw

from crop_equations import crop_image, equation_boxes


image = Image.new("RGB", (300, 200), "white")
draw = ImageDraw.Draw(image)
for y in (30, 110):
    for x in (40, 80, 120):
        draw.rectangle((x, y, x + 15, y + 20), fill="black")
assert equation_boxes(image, padding=5) == [(35, 25, 141, 56), (35, 105, 141, 136)]
assert equation_boxes(Image.new("RGB", (300, 200), "white")) == []
with TemporaryDirectory() as temporary:
    root = Path(temporary)
    source = root / "worksheet.png"
    image.save(source)
    original = source.read_bytes()
    count, first = crop_image(source, root / "output")
    assert count == 2 and len(list(first.glob("equation_*.png"))) == 2
    _, second = crop_image(source, root / "output")
    assert first != second and source.read_bytes() == original
    transparent = root / "transparent.png"
    Image.new("RGBA", (100, 100)).save(transparent)
    assert crop_image(transparent, root / "output") == (0, None)
print("Passed: separate rows, blank images, transparent backgrounds, safe reruns, and unchanged originals.")
