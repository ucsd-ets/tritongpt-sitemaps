"""
Used for manual creation of sitemaps via list of urls
located in the manual_urls.txt file.
"""

OUTPUT_FILE_NAME = 'manual_sitemap.xml'
INPUT_FILE_NAME = 'manual_urls.txt'

def generate_sitemap(input_file, output_file):
    urls = []

    with open(input_file, 'r') as file:
        for line in file:
            url = line.strip()
            if url.startswith('http'):
                urls.append(url)
    
    sitemap_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
    sitemap_content += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'

    for url in urls:
        sitemap_content += '  <url>\n'
        sitemap_content += f'    <loc>{url}</loc>\n'
        sitemap_content += '  </url>\n'
    
    sitemap_content += '</urlset>'

    with open(output_file, 'w') as file:
        file.write(sitemap_content)


if __name__ == '__main__':
    # Generate the sitemap
    generate_sitemap(INPUT_FILE_NAME, OUTPUT_FILE_NAME)