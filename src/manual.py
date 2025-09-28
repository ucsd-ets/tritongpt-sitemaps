"""
Used for manual creation of sitemaps via list of urls
located in the manual_urls.txt file.
"""

import xml.etree.ElementTree as ET
from urllib.request import Request, urlopen
import logging

OUTPUT_FILE_NAME = 'TEST_manual_sitemap.xml'
INPUT_FILE_NAME = 'manual_urls.txt'

logging.basicConfig(level=logging.INFO)

def fetch_url(url):
    """Fetch content from a URL"""
    try:
        request = Request(url, headers={"User-Agent": "Sitemap crawler"})
        response = urlopen(request)
        content = response.read()
        response.close()
        return content
    except Exception as e:
        logging.error(f"Failed to fetch {url}: {e}")
        return None

def parse_sitemap_urls(content):
    """Extract URLs from a sitemap or sitemap index"""
    urls = []
    try:
        if isinstance(content, bytes):
            content = content.decode('utf-8', errors='ignore')

        root = ET.fromstring(content)
        ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

        # Check if it's a sitemap index
        if '<sitemapindex' in content:
            # Extract sitemap URLs from index
            for sitemap in root.findall('.//sm:sitemap', ns):
                loc = sitemap.find('sm:loc', ns)
                if loc is not None and loc.text:
                    sitemap_url = loc.text.strip()
                    # Recursively fetch and parse each sitemap
                    sitemap_content = fetch_url(sitemap_url)
                    if sitemap_content:
                        urls.extend(parse_sitemap_urls(sitemap_content))

            # Also try without namespace
            if not urls:
                for sitemap in root.findall('.//sitemap'):
                    loc = sitemap.find('loc')
                    if loc is not None and loc.text:
                        sitemap_url = loc.text.strip()
                        sitemap_content = fetch_url(sitemap_url)
                        if sitemap_content:
                            urls.extend(parse_sitemap_urls(sitemap_content))

        # Check if it's a regular sitemap
        elif '<urlset' in content:
            # Extract page URLs from sitemap
            for url in root.findall('.//sm:url', ns):
                loc = url.find('sm:loc', ns)
                if loc is not None and loc.text:
                    urls.append(loc.text.strip())

            # Also try without namespace
            if not urls:
                for url in root.findall('.//url'):
                    loc = url.find('loc')
                    if loc is not None and loc.text:
                        urls.append(loc.text.strip())
    except ET.ParseError as e:
        logging.error(f"Failed to parse XML: {e}")

    return urls

def generate_sitemap(input_file, output_file):
    urls = []

    with open(input_file, 'r') as file:
        for line in file:
            url = line.strip()
            if url.startswith('http'):
                # Check if URL looks like a sitemap
                if url.endswith('.xml') or 'sitemap' in url.lower():
                    logging.info(f"Detected sitemap URL: {url}")
                    # Fetch and parse the sitemap
                    content = fetch_url(url)
                    if content:
                        sitemap_urls = parse_sitemap_urls(content)
                        if sitemap_urls:
                            logging.info(f"Extracted {len(sitemap_urls)} URLs from {url}")
                            urls.extend(sitemap_urls)
                        else:
                            # If parsing failed, treat as regular URL
                            urls.append(url)
                    else:
                        # If fetch failed, treat as regular URL
                        urls.append(url)
                else:
                    # Regular URL
                    urls.append(url)

    # Remove duplicates while preserving order
    seen = set()
    unique_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)

    sitemap_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
    sitemap_content += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'

    for url in unique_urls:
        sitemap_content += '  <url>\n'
        sitemap_content += f'    <loc>{url}</loc>\n'
        sitemap_content += '  </url>\n'

    sitemap_content += '</urlset>'

    with open(output_file, 'w') as file:
        file.write(sitemap_content)

    logging.info(f"Generated sitemap with {len(unique_urls)} unique URLs")


if __name__ == '__main__':
    # Generate the sitemap
    generate_sitemap(INPUT_FILE_NAME, OUTPUT_FILE_NAME)