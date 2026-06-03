import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import crawler


class CrawlerUrlCleaningTest(unittest.TestCase):

	def make_crawler(self):
		return crawler.Crawler(
			domain="https://www.law.berkeley.edu",
			sitemap_only=True,
			max_url_diff_percent=None,
		)

	def test_clean_output_url_rejects_malformed_wrapped_url(self):
		crawl = self.make_crawler()

		self.assertIsNone(
			crawl.clean_output_url("http://%20https%3A//www.law.berkeley.edu/annual-reports/")
		)

	def test_clean_output_url_strips_fragments_and_preserves_query(self):
		crawl = self.make_crawler()

		self.assertEqual(
			crawl.clean_output_url(" https://www.law.berkeley.edu/a/../annual-reports/?x=1#overview "),
			"https://www.law.berkeley.edu/annual-reports/?x=1",
		)

	def test_add_url_to_output_dedupes_cleaned_urls(self):
		crawl = self.make_crawler()

		self.assertTrue(crawl.add_url_to_output("https://www.law.berkeley.edu/annual-reports/#overview"))
		self.assertFalse(crawl.add_url_to_output("https://www.law.berkeley.edu/annual-reports/"))
		self.assertEqual(
			crawl.url_strings_to_output,
			["<url><loc>https://www.law.berkeley.edu/annual-reports/</loc></url>"],
		)

	def test_process_xml_content_skips_malformed_and_dedupes_clean_url(self):
		crawl = self.make_crawler()
		content = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
	<url><loc>http://%20https%3A//www.law.berkeley.edu/annual-reports/</loc></url>
	<url><loc>https://www.law.berkeley.edu/annual-reports/</loc></url>
	<url><loc>https://www.law.berkeley.edu/annual-reports/#overview</loc></url>
</urlset>
"""

		self.assertTrue(crawl.process_xml_content(content, "https://www.law.berkeley.edu/multimedia-sitemap.xml"))
		self.assertEqual(
			crawl.url_strings_to_output,
			["<url><loc>https://www.law.berkeley.edu/annual-reports/</loc></url>"],
		)


if __name__ == "__main__":
	unittest.main()
