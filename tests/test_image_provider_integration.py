"""Offline contract tests for Pixazo and the self-hosted Cloudflare image API."""
import json
import unittest
from unittest.mock import patch

from content_generator.creative import flux_generator as image_gen


class _FakeResponse:
    def __init__(self, body: bytes, content_type: str):
        self._body = body
        self.headers = {"Content-Type": content_type}
        self.status = 200

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ImageProviderIntegrationTests(unittest.TestCase):
    def test_aspect_ratio_mapping(self):
        self.assertEqual(image_gen._aspect_ratio(1080, 1920), "9:16")
        self.assertEqual(image_gen._aspect_ratio(1080, 1080), "1:1")
        self.assertEqual(image_gen._aspect_ratio(1920, 1080), "16:9")

    def test_extracts_pixazo_media_url_only_over_https(self):
        self.assertEqual(
            image_gen._extract_media_url({"output": {"media_url": ["https://cdn.example/image.png"]}}),
            "https://cdn.example/image.png",
        )
        self.assertIsNone(image_gen._extract_media_url({"image": "http://example.com/image.png"}))
        self.assertIsNone(image_gen._extract_media_url({"image": "file:///etc/passwd"}))

    def test_pixazo_immediate_media_response(self):
        payload = json.dumps({"image": "https://cdn.example/purity.png"}).encode()
        with patch.object(image_gen, "_PIXAZO_KEY", "pixazo-test-key"), \
             patch.object(image_gen, "_PIXAZO_ENDPOINT", "https://gateway.pixazo.ai/flux/text-to-image"), \
             patch.object(image_gen.urllib.request, "urlopen", return_value=_FakeResponse(payload, "application/json")), \
             patch.object(image_gen, "_download_image_url", return_value="output/creative/test.png") as download:
            result = image_gen._pixazo("coffee scene", 1080, 1080, "test", 7)
        self.assertEqual(result, "output/creative/test.png")
        download.assert_called_once_with("https://cdn.example/purity.png", "test")

    def test_cloudflare_worker_sends_bearer_and_prompt(self):
        image_bytes = b"\xff\xd8\xff" + b"x" * 1200
        with patch.object(image_gen, "_FREE_IMAGE_API_URL", "https://my-worker.workers.dev/"), \
             patch.object(image_gen, "_FREE_IMAGE_API_KEY", "worker-test-key"), \
             patch.object(image_gen.urllib.request, "urlopen", return_value=_FakeResponse(image_bytes, "image/jpeg")) as urlopen, \
             patch.object(image_gen, "_save_image", return_value="output/creative/test.jpg") as save:
            result = image_gen._free_image_worker("editorial coffee background", 1080, 1080, "test")
        self.assertEqual(result, "output/creative/test.jpg")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer worker-test-key")
        self.assertEqual(json.loads(request.data.decode()), {"prompt": "editorial coffee background"})
        save.assert_called_once_with(image_bytes, "test", ext="jpg")

    def test_non_image_response_is_rejected(self):
        self.assertFalse(image_gen._is_image_response(b'{"error":"bad key"}' + b" " * 1200, "application/json"))
        self.assertFalse(image_gen._is_image_response(b"small", "image/jpeg"))
        self.assertTrue(image_gen._is_image_response(b"\xff\xd8\xff" + b"x" * 1200, "image/jpeg"))


if __name__ == "__main__":
    unittest.main()
