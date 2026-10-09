import os
import tempfile
import unittest

from PIL import Image

from content_generator.creative.rendered_asset_qa import audit_rendered_images


class RenderedAssetQATests(unittest.TestCase):
    def test_rejects_empty_asset_list(self):
        self.assertFalse(audit_rendered_images([])["ok"])

    def test_rejects_corrupt_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "broken.png")
            with open(path, "wb") as handle:
                handle.write(b"not an image")
            result = audit_rendered_images([path])
            self.assertFalse(result["ok"])
            self.assertTrue(any("unreadable_image" in issue for issue in result["issues"]))

    def test_rejects_flat_image(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "flat.png")
            Image.new("RGB", (1080, 1080), (30, 30, 30)).save(path)
            result = audit_rendered_images([path])
            self.assertFalse(result["ok"])
            self.assertTrue(any("flat_image" in issue for issue in result["issues"]))

    def test_accepts_nonblank_render(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "render.png")
            image = Image.new("RGB", (1080, 1080), (25, 20, 15))
            for x in range(200, 880):
                for y in range(200, 880):
                    image.putpixel((x, y), ((x + y) % 255, x % 255, y % 255))
            image.save(path)
            result = audit_rendered_images([path])
            self.assertTrue(result["ok"], result["issues"])


if __name__ == "__main__":
    unittest.main()
