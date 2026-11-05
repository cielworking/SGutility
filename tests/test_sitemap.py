import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_renderer():
    spec = importlib.util.spec_from_file_location("render_static_pages", ROOT / "scripts" / "render-static-pages.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SitemapTests(unittest.TestCase):
    def test_every_indexable_guide_is_in_the_rendered_sitemap(self):
        renderer = load_renderer()
        xml = renderer.render_sitemap({})
        missing = []
        for path in sorted((ROOT / "guides").glob("*.html")):
            text = path.read_text(encoding="utf-8")
            if renderer.page_is_noindex(text):
                continue
            url = renderer.guide_page_url(path)
            if f"<loc>{url}</loc>" not in xml:
                missing.append(url)
        self.assertEqual(missing, [])

    def test_guide_lastmod_is_kept(self):
        renderer = load_renderer()
        url = "https://sgalerts.com/guides/northeast-monsoon-singapore-flash-floods.html"
        xml = renderer.render_sitemap({}, {url: "2026-11-06"})
        self.assertIn(f"<loc>{url}</loc>\n    <lastmod>2026-11-06</lastmod>", xml)

    def test_weather_renderer_does_not_write_a_sitemap(self):
        text = (ROOT / "scripts" / "render-weather-pages.py").read_text(encoding="utf-8")
        self.assertNotIn("sitemap.xml", text)
