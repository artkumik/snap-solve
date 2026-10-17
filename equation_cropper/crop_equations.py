"""Crop equations down the left column first, then down the right column."""

import argparse
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp"}


def equation_boxes(image, threshold=190, gap=18, padding=12):
    """Find dark equation rows; return padded (left, top, right, bottom) boxes."""
    gray = ImageOps.grayscale(image)
    mask = gray.point(lambda value: 255 if value < threshold else 0)
    minimum_ink = max(2, image.width // 1000)
    groups = []
    for y in range(image.height):
        row = mask.crop((0, y, image.width, y + 1))
        if row.histogram()[255] < minimum_ink:
            continue
        if groups and y - groups[-1][1] < gap:
            groups[-1][1] = y + 1
        else:
            groups.append([y, y + 1])

    boxes = []
    for top, bottom in groups:
        bounds = mask.crop((0, top, image.width, bottom)).getbbox()
        if bounds is None:
            continue
        left, _, right, _ = bounds
        if right - left < 12 or bottom - top < 6:
            continue  # Ignore small specks.
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
