import sys
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import update_ucop_policies


class UpdateUcopPoliciesTest(unittest.TestCase):

    def test_extract_policy_urls_filters_and_deduplicates_links(self):
        html = """
        <a href="/doc/4000701">View Policy</a>
        <a href="https://policy.ucop.edu/doc/2500486">View Policy</a>
        <a href="/doc/4000701">Duplicate</a>
        <a href="https://example.com/doc/1234567">Other host</a>
        <a href="/doc/not-an-id">Invalid policy</a>
        """

        self.assertEqual(
            update_ucop_policies.extract_policy_urls(html),
            [
                "https://policy.ucop.edu/doc/4000701?.pdf",
                "https://policy.ucop.edu/doc/2500486?.pdf",
            ],
        )

    def test_render_sitemap_produces_valid_xml(self):
        urls = [
            "https://policy.ucop.edu/doc/4000701?.pdf",
            "https://policy.ucop.edu/doc/2500486?.pdf",
        ]

        root = ET.fromstring(update_ucop_policies.render_sitemap(urls))
        namespace = {"sitemap": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locations = [element.text for element in root.findall("sitemap:url/sitemap:loc", namespace)]

        self.assertEqual(locations, urls)

    def test_extract_reported_total(self):
        html = '<div class="result-count">484\n of 484</div>'

        self.assertEqual(update_ucop_policies.extract_reported_total(html), 484)


if __name__ == "__main__":
    unittest.main()
