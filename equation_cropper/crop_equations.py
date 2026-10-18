"""Crop equations down the left column first, then down the right column."""

import argparse
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp"}


def equation_boxes(image, threshold=190, gap=18, padding=12):
    """Find dark equation rows; return padded (left, top, right, bottom) boxes."""
    gray = ImageOps.grayscale(image)
    mask = gray.point(lambda value: 255 if value < threshold else 0)
    # A fixed cutoff mistakes shaded paper and photographed screens for writing.
    photographed = mask.histogram()[255] > image.width * image.height / 4
    if photographed:
        gray.thumbnail((1600, 1600))
        gray = gray.filter(ImageFilter.GaussianBlur(1))
        background = gray.filter(ImageFilter.GaussianBlur(max(3, max(gray.size) * 15 / 1600)))
        mask = ImageChops.subtract(background, gray).point(lambda value: 255 if value > 30 else 0)
        # Remove thin notebook rules and screen moire before discarding frame edges.
        size = 5 if max(gray.size) >= 1200 else 3
        mask = mask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
        pixels = mask.load()
        edges = ([(x, y) for x in range(mask.width) for y in (0, mask.height - 1)]
                 + [(x, y) for y in range(mask.height) for x in (0, mask.width - 1)])
        for point in edges:
            if pixels[point]:
                ImageDraw.floodfill(mask, point, 0)
        if size > 3:
            mask = mask.filter(ImageFilter.MinFilter(size)).filter(ImageFilter.MaxFilter(size))
    minimum_ink = max(3, mask.width // 200) if photographed else max(2, image.width // 1000)
    scale_x, scale_y = image.width / mask.width, image.height / mask.height
    row_gap = max(18, round(gap / scale_y)) if photographed else gap
    groups = []
    for y in range(mask.height):
        row = mask.crop((0, y, mask.width, y + 1))
        if row.histogram()[255] < minimum_ink:
            continue
        if groups and y - groups[-1][1] < row_gap:
            groups[-1][1] = y + 1
        else:
            groups.append([y, y + 1])

    boxes = []
    for top, bottom in groups:
        band = mask.crop((0, top, mask.width, bottom))
        bounds = band.getbbox()
        if bounds is None:
            continue
        left, _, right, _ = bounds
        if right - left < 12 or bottom - top < 6:
            continue  # Ignore small specks.
        if photographed:
            width, height = right - left, bottom - top
            if width > height * 30 or band.histogram()[255] / (width * height) < 0.03:
                continue  # Thin rules, monitor edges, and sparse paper creases.
        left, top = int(left * scale_x), int(top * scale_y)
        right, bottom = round(right * scale_x), round(bottom * scale_y)
        boxes.append((max(0, left - padding), max(0, top - padding),
                      min(image.width, right + padding), min(image.height, bottom + padding)))
    return boxes


def worksheet_boxes(image, columns=2, **options):
    if columns == 1:
        return equation_boxes(image, **options)
    midpoint = image.width // 2
    boxes = []
    for left, right in ((0, midpoint), (midpoint, image.width)):
        column = image.crop((left, 0, right, image.height))
        boxes.extend((x1 + left, y1, x2 + left, y2)
                     for x1, y1, x2, y2 in equation_boxes(column, **options))
    return boxes


def crop_image(source, output, columns=2, **options):
    with Image.open(source) as original:
        upright = ImageOps.exif_transpose(original).convert("RGBA")
        # Transparent backgrounds should behave like white paper during detection.
        image = Image.new("RGB", upright.size, "white")
        image.paste(upright, mask=upright.getchannel("A"))
        boxes = worksheet_boxes(image, columns=columns, **options)
        if not boxes:
            return 0, None
        base = f"{source.stem}_{source.suffix[1:].lower()}"
        attempt = 1
        while True:
            destination = output / (base if attempt == 1 else f"{base}_{attempt}")
            try:
                destination.mkdir(parents=True, exist_ok=False)
                break
            except FileExistsError:
                attempt += 1
        for index, box in enumerate(boxes, 1):
            image.crop(box).save(destination / f"equation_{index:03d}.png")
        return len(boxes), destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=ROOT / "input",
                        help="An image or a folder of images (default: input/).")
    parser.add_argument("--output", type=Path, default=ROOT / "output")
    parser.add_argument("--columns", type=int, choices=(1, 2), default=2,
                        help="Two equal-width columns, left first (default), or one full-width column.")
    parser.add_argument("--gap", type=int, default=18, help="Blank rows needed to split equations (pixels).")
    parser.add_argument("--padding", type=int, default=12, help="Padding around each crop (pixels).")
    parser.add_argument("--threshold", type=int, default=190, help="Pixels darker than this count as ink (1–255).")
    args = parser.parse_args()
    if args.gap < 1 or args.padding < 0 or not 1 <= args.threshold <= 255:
        parser.error("Use gap >= 1, padding >= 0, and threshold between 1 and 255.")
    if not args.input.exists():
        parser.error(f"Input does not exist: {args.input}")
    sources = [args.input] if args.input.is_file() else sorted(
        path for path in args.input.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_TYPES)
    if not sources:
        print(f"Put PNG, JPEG, or WebP images in {args.input}")
    failed = False
    for source in sources:
        try:
            count, destination = crop_image(source, args.output, columns=args.columns, gap=args.gap,
                                           padding=args.padding, threshold=args.threshold)
            print(f"{source.name}: {count} crops" + (f" → {destination}" if destination else " (no equations detected)"))
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            failed = True
            print(f"{source.name}: could not process image: {error}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
