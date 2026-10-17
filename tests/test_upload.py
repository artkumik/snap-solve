import asyncio
from io import BytesIO
import json
import unittest
from unittest.mock import patch

from PIL import Image

from app import MAX_UPLOAD_BYTES, app


async def post_image(body):
    messages = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    await app({
        "type": "http", "http_version": "1.1", "method": "POST",
        "scheme": "http", "path": "/upload", "raw_path": b"/upload",
        "root_path": "", "query_string": b"",
        "headers": [(b"content-type", b"image/png")],
        "server": ("localhost", 8000), "client": ("127.0.0.1", 1),
    }, receive, send)
    return messages[0]["status"], json.loads(b"".join(m.get("body", b"") for m in messages))


class UploadTests(unittest.TestCase):
    def test_image_is_processed_without_disk_access(self):
        data = BytesIO()
        with Image.new("RGB", (2, 2)) as image:
            image.save(data, format="PNG")

        def process(image):
            self.assertIsInstance(image, Image.Image)
            self.assertEqual(image.size, (2, 2))
            return True

        with patch("app.process_image", side_effect=process) as processor:
            with patch("builtins.open", side_effect=AssertionError("Unexpected disk access")):
                status, response = asyncio.run(post_image(data.getvalue()))
        self.assertEqual(status, 200)
        self.assertEqual(response, {"result": True})
        processor.assert_called_once()

    def test_invalid_and_oversized_images_are_rejected(self):
        for data, expected in [(b"not an image", 400), (b"x" * (MAX_UPLOAD_BYTES + 1), 413)]:
            with self.subTest(status=expected), patch("app.process_image") as processor:
                status, _ = asyncio.run(post_image(data))
                self.assertEqual(status, expected)
                processor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
