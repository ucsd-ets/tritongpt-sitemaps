"""
Used for manual creation of sitemaps via list of urls
located in the manual_urls.txt file or by scanning directories
for static files.
"""

import os
import argparse
from urllib.parse import urljoin
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
import re

OUTPUT_FILE_NAME = 'TEST_manual_sitemap.xml'
INPUT_FILE_NAME = 'manual_urls.txt'

def convert_xls_to_csv(xls_path):
    """Convert Excel file to CSV files (one per worksheet).

    Args:
        xls_path: Path to the Excel file

    Returns:
        List of paths to generated CSV files, or empty list on error
    """
    try:
        import xml.etree.ElementTree as ET
        import csv

        # Check if it's XML-based Excel format
        with open(xls_path, 'rb') as f:
            header = f.read(100)

        # XML-based Excel format (SpreadsheetML)
        if b'<?xml' in header or b'<Workbook' in header:
            # Parse using lxml for better malformed XML handling
            try:
                from lxml import etree as lxml_etree
                parser = lxml_etree.XMLParser(recover=True)
                tree = lxml_etree.parse(xls_path, parser)
                root = tree.getroot()
            except ImportError:
                # Fallback to ElementTree
                tree = ET.parse(xls_path)
                root = tree.getroot()

            # Define namespaces for SpreadsheetML
            ns = {
                'ss': 'urn:schemas-microsoft-com:office:spreadsheet',
                'o': 'urn:schemas-microsoft-com:office:office',
                'x': 'urn:schemas-microsoft-com:office:excel',
                'html': 'http://www.w3.org/TR/REC-html40'
            }

            csv_files = []
            base_name = os.path.splitext(xls_path)[0]

            # Find all worksheets
            worksheets = root.findall('.//ss:Worksheet', ns)
            print(f"Converting {len(worksheets)} worksheet(s) to CSV...")

            for worksheet in worksheets:
                sheet_name = worksheet.get('{urn:schemas-microsoft-com:office:spreadsheet}Name', 'Sheet')

                # Create a clean filename from sheet name
                clean_sheet_name = re.sub(r'[^\w\s-]', '', sheet_name).strip()
                clean_sheet_name = re.sub(r'[-\s]+', '_', clean_sheet_name)

                # Generate CSV filename
                csv_path = f"{base_name}-{clean_sheet_name}.csv"

                # Extract data from worksheet
                rows_data = []
                table = worksheet.find('.//ss:Table', ns)
                if table is not None:
                    rows = table.findall('.//ss:Row', ns)
                    for row in rows:
                        row_data = []
                        cells = row.findall('.//ss:Cell', ns)
                        for cell in cells:
                            data_elem = cell.find('.//ss:Data', ns)
                            if data_elem is not None:
                                row_data.append(data_elem.text if data_elem.text else '')
                            else:
                                row_data.append('')
                        rows_data.append(row_data)

                # Write to CSV
                with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerows(rows_data)

                csv_files.append(csv_path)
                print(f"  Created: {csv_path}")

            # Remove the original .xls file
            os.remove(xls_path)
            print(f"Removed original file: {xls_path}")

            return csv_files

        else:
            # Binary Excel format - use pandas
            try:
                import pandas as pd
                excel_dict = pd.read_excel(xls_path, sheet_name=None, engine='openpyxl')

                csv_files = []
                base_name = os.path.splitext(xls_path)[0]

                print(f"Converting {len(excel_dict)} worksheet(s) to CSV...")

                for sheet_name, df in excel_dict.items():
                    # Create a clean filename from sheet name
                    clean_sheet_name = re.sub(r'[^\w\s-]', '', sheet_name).strip()
                    clean_sheet_name = re.sub(r'[-\s]+', '_', clean_sheet_name)

                    # Generate CSV filename
                    csv_path = f"{base_name}-{clean_sheet_name}.csv"

                    # Save as CSV with UTF-8 encoding
                    df.to_csv(csv_path, index=False, encoding='utf-8')
                    csv_files.append(csv_path)
                    print(f"  Created: {csv_path}")

                # Remove the original .xls file
                os.remove(xls_path)
                print(f"Removed original file: {xls_path}")

                return csv_files

            except ImportError:
                print("Error: pandas and openpyxl are required for binary Excel conversion.")
                print("Install with: pip install pandas openpyxl")
                return []

    except Exception as e:
        print(f"Error converting to CSV: {e}")
        import traceback
        traceback.print_exc()
        return []

def download_file(source_url, destination_path):
    """Download a file from a URL and save it locally.

    Args:
        source_url: URL to download from
        destination_path: Local file path to save to

    Returns:
        True if successful, False otherwise
    """
    try:
        # Create directory if it doesn't exist
        dest_dir = os.path.dirname(destination_path)
        if dest_dir and not os.path.exists(dest_dir):
            os.makedirs(dest_dir)

        print(f"Downloading from {source_url}...")
        request = Request(source_url, headers={'User-Agent': 'Mozilla/5.0'})

        with urlopen(request) as response:
            content = response.read()

        with open(destination_path, 'wb') as f:
            f.write(content)

        print(f"Successfully downloaded to {destination_path}")
        return True

    except HTTPError as e:
        print(f"HTTP Error {e.code}: {e.reason}")
        return False
    except URLError as e:
        print(f"URL Error: {e.reason}")
        return False
    except Exception as e:
        print(f"Error downloading file: {e}")
        return False

def generate_sitemap_from_file(input_file, output_file):
    """Generate sitemap from a text file containing URLs."""
    urls = []

    with open(input_file, 'r') as file:
        for line in file:
            url = line.strip()
            if url.startswith('http'):
                urls.append(url)

    write_sitemap(urls, output_file)


def generate_sitemap_from_directory(directory, base_url, output_file, extensions=None, url_prefix=None):
    """Generate sitemap by scanning a directory for static files.

    Args:
        directory: Path to the directory to scan
        base_url: Base URL for the site (e.g., 'https://example.com')
        output_file: Output sitemap file path
        extensions: List of file extensions to include (default: common static files)
        url_prefix: Optional prefix to prepend to file paths in URLs. If None, uses directory basename.
    """
    if extensions is None:
        extensions = ['.html', '.htm', '.pdf', '.txt', '.xml', '.json', '.css', '.js',
                     '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico',
                     '.woff', '.woff2', '.ttf', '.eot', '.mp4', '.webm', '.mp3',
                     '.xls', '.xlsx', '.doc', '.docx', '.ppt', '.pptx', '.csv']

    urls = []

    # Normalize base_url
    if not base_url.endswith('/'):
        base_url += '/'

    # Determine URL prefix: use provided prefix or directory basename
    if url_prefix is None:
        url_prefix = os.path.basename(os.path.abspath(directory))

    # Walk through directory
    for root, dirs, files in os.walk(directory):
        for file in files:
            # Check if file has one of the allowed extensions
            _, ext = os.path.splitext(file)
            if ext.lower() in extensions:
                # Get relative path from the base directory
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, directory)

                # Convert to URL path (use forward slashes)
                url_path = rel_path.replace(os.sep, '/')

                # Prepend the URL prefix
                full_path = f"{url_prefix}/{url_path}"

                # Create full URL
                full_url = urljoin(base_url, full_path)
                urls.append(full_url)

    # Sort URLs for consistency
    urls.sort()

    write_sitemap(urls, output_file)
    print(f"Generated sitemap with {len(urls)} URLs from directory: {directory}")


def write_sitemap(urls, output_file):
    """Write URLs to a sitemap XML file."""
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
    parser = argparse.ArgumentParser(description='Manual Sitemap Generator')
    parser.add_argument('--input-file', default=INPUT_FILE_NAME,
                       help='Input file containing URLs (one per line)')
    parser.add_argument('--output', default=OUTPUT_FILE_NAME,
                       help='Output sitemap file')
    parser.add_argument('--directory', help='Directory to scan for static files')
    parser.add_argument('--base-url', help='Base URL for the site (required with --directory)')
    parser.add_argument('--extensions', nargs='+',
                       help='File extensions to include (e.g., .html .pdf .css)')
    parser.add_argument('--download-url', help='URL to download file from before generating sitemap')
    parser.add_argument('--download-dest', help='Local path to save downloaded file (required with --download-url)')
    parser.add_argument('--url-prefix', help='URL prefix to prepend to file paths (defaults to directory basename)')
    parser.add_argument('--convert-to-csv', action='store_true', default=False,
                       help='Convert downloaded Excel file to CSV UTF-8 (one file per worksheet)')

    args = parser.parse_args()

    # Handle download if requested
    if args.download_url:
        if not args.download_dest:
            print("Error: --download-dest is required when using --download-url")
            exit(1)

        success = download_file(args.download_url, args.download_dest)
        if not success:
            print("Download failed. Exiting.")
            exit(1)

        # Convert to CSV if requested
        if args.convert_to_csv:
            csv_files = convert_xls_to_csv(args.download_dest)
            if not csv_files:
                print("CSV conversion failed. Exiting.")
                exit(1)

    if args.directory:
        if not args.base_url:
            print("Error: --base-url is required when using --directory")
            exit(1)

        if not os.path.isdir(args.directory):
            print(f"Error: Directory not found: {args.directory}")
            exit(1)

        # Convert extensions to list with dots
        extensions = None
        if args.extensions:
            extensions = [ext if ext.startswith('.') else f'.{ext}' for ext in args.extensions]

        generate_sitemap_from_directory(args.directory, args.base_url, args.output, extensions, args.url_prefix)
    else:
        # Generate from file
        generate_sitemap_from_file(args.input_file, args.output)
        print(f"Generated sitemap from file: {args.input_file}")