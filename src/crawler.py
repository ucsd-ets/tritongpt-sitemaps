import asyncio
import base64
import concurrent.futures
import logging
import math
import mimetypes
import os
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from copy import copy
from datetime import datetime
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

import config


class IllegalArgumentError(ValueError):
	pass

class UrlDiffThresholdExceeded(Exception):
	def __init__(self, domain, old_count, new_count, threshold):
		self.domain = domain
		self.old_count = old_count
		self.new_count = new_count
		self.threshold = threshold
		self.diff = abs(new_count - old_count)
		super().__init__(f"URL count difference ({self.diff}) exceeds threshold ({threshold}) for {domain}")

class Crawler:

	MAX_URLS_PER_SITEMAP = 50000

	# Variables
	parserobots = False
	output 	= None
	report 	= False

	config 	= None
	domain	= ""

	exclude = []
	skipext = []
	drop    = []

	debug	= False
	auth = False

	urls_to_crawl = set([])
	url_strings_to_output = []
	crawled_or_crawling = set([])
	excluded = set([])

	marked = defaultdict(list)

	not_parseable_resources = (".epub", ".mobi", ".xlsx", ".docx", ".doc", ".opf", ".7z", ".ibooks", ".cbr", ".avi", ".mkv", ".mp4", ".jpg", ".jpeg", ".png", ".gif", ".iso", ".rar", ".tar", ".tgz", ".zip", ".dmg", ".exe", ".pdf")

	# TODO also search for window.location={.*?}
	linkregex = re.compile(b'<a [^>]*href=[\'|"](.*?)[\'"][^>]*?>')
	imageregex = re.compile (b'<img [^>]*src=[\'|"](.*?)[\'"].*?>')

	rp = None
	response_code=defaultdict(int)
	nb_url=1 # Number of url.
	nb_rp=0 # Number of url blocked by the robots.txt
	nb_exclude=0 # Number of url excluded by extension or word

	output_file = None

	target_domain = ""
	scheme		  = ""

	def __init__(self, num_workers=1, parserobots=False, output=None,
				 report=False ,domain="", exclude=[], skipext=[], drop=[],
				 debug=False, verbose=False, images=False, auth=False, as_index=False,
				 sort_alphabetically=True, user_agent='*', sitemap_url=None, sitemap_only=False,
				 max_url_diff=None):
		self.num_workers = num_workers
		self.parserobots = parserobots
		self.user_agent = user_agent
		self.output 	= output
		self.report 	= report
		self.domain 	= domain
		self.exclude 	= exclude
		self.skipext 	= skipext
		self.drop		= drop
		self.debug		= debug
		self.verbose    = verbose
		self.images     = images
		self.auth       = auth
		self.as_index   = as_index
		self.sort_alphabetically = sort_alphabetically
		self.sitemap_url = sitemap_url
		self.sitemap_only = sitemap_only
		self.max_url_diff = max_url_diff

		if self.debug:
			log_level = logging.DEBUG
		elif self.verbose:
			log_level = logging.INFO
		else:
			log_level = logging.ERROR

		logging.basicConfig(level=log_level)

		# Initialize urls_to_crawl based on sitemap configuration
		self.urls_to_crawl = set()

		# Add sitemap URLs first if provided
		if self.sitemap_url:
			# Handle both single URL and list of URLs
			sitemap_urls = self.sitemap_url if isinstance(self.sitemap_url, list) else [self.sitemap_url]
			for sitemap_url in sitemap_urls:
				self.urls_to_crawl.add(self.clean_link(sitemap_url))
				logging.info(f"Added sitemap URL to crawl queue: {sitemap_url}")

		# Add domain URL only if not in sitemap-only mode
		if not self.sitemap_only:
			self.urls_to_crawl.add(self.clean_link(domain))
		elif not self.sitemap_url:
			# If sitemap_only=True but no sitemap_url provided, fall back to domain
			logging.warning("sitemap_only=True but no sitemap_url provided, falling back to domain")
			self.urls_to_crawl.add(self.clean_link(domain))

		self.url_strings_to_output = []
		self.num_crawled = 0

		if num_workers <= 0:
			raise IllegalArgumentError("Number or workers must be positive")

		try:
			url_parsed = urlparse(domain)
			self.target_domain = url_parsed.netloc
			self.scheme = url_parsed.scheme
		except:
			logging.error("Invalid domain")
			raise IllegalArgumentError("Invalid domain")

		# Validate output file path but don't open it yet (we need to check URL diff first)
		if self.as_index and not self.output:
			logging.error("When specifying an index file as an output option, you must include an output file name")
			exit(255)

	def run(self):
		if self.parserobots:
			self.check_robots()

		logging.info("Start the crawling process")

		if self.num_workers == 1:
			while len(self.urls_to_crawl) != 0:
				current_url = self.urls_to_crawl.pop()
				self.crawled_or_crawling.add(current_url)
				self.__crawl(current_url)
		else:
			event_loop = asyncio.get_event_loop()
			try:
				while len(self.urls_to_crawl) != 0:
					executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.num_workers)
					event_loop.run_until_complete(self.crawl_all_pending_urls(executor))
			finally:
				event_loop.close()

		logging.info("Crawling has reached end of all found links")

		if self.sort_alphabetically:
			self.url_strings_to_output.sort()

		try:
			self.write_sitemap_output()
		finally:
			if self.output_file:
				self.output_file.close()



	async def crawl_all_pending_urls(self, executor):
		event_loop = asyncio.get_event_loop()

		crawl_tasks = []
		# Since the tasks created by `run_in_executor` begin executing immediately,
		# `self.urls_to_crawl` will start to get updated, potentially before the below
		# for loop finishes.  This creates a race condition and if `self.urls_to_crawl`
		# is updated (by `self.__crawl`) before the for loop finishes, it'll raise an
		# error
		urls_to_crawl = copy(self.urls_to_crawl)
		self.urls_to_crawl.clear()
		for url in urls_to_crawl:
			self.crawled_or_crawling.add(url)
			task = event_loop.run_in_executor(executor, self.__crawl, url)
			crawl_tasks.append(task)

		logging.debug('waiting on all crawl tasks to complete')
		await asyncio.wait(crawl_tasks)
		logging.debug('all crawl tasks have completed nicely')
		return



	def __crawl(self, current_url):
		url = urlparse(current_url)
		logging.info(f"Crawling #{self.num_crawled}: {url.geturl()}")
		self.num_crawled += 1

		request = Request(current_url, headers={"User-Agent": config.crawler_user_agent})

		if self.auth:
			base64string = base64.b64encode(bytes(f'{config.username}:{config.password}', 'ascii'))
			request.add_header("Authorization", "Basic %s" % base64string.decode('utf-8'))

		# Ignore resources listed in the not_parseable_resources
		# Its avoid dowloading file like pdf… etc
		if not url.path.endswith(self.not_parseable_resources):
			try:
				response = urlopen(request)
			except Exception as e:
				if hasattr(e,'code'):
					self.response_code[e.code] += 1

					# Gestion des urls marked pour le reporting
					if self.report:
						self.marked[e.code].append(current_url)

				logging.debug (f"{e} ==> {current_url}")
				return
		else:
			logging.debug(f"Ignore {current_url} content might be not parseable.")
			response = None

		# Read the response
		if response is not None:
			try:
				msg = response.read()
				self.response_code[response.getcode()] += 1

				# Check for "anubis" in the response content
				if b"anubis" in msg.lower():
					logging.warning(f"WARNING: 'anubis' detected in response from {current_url}")

				response.close()

				# Check if this is XML content (sitemap or sitemap index)
				content_type = response.headers.get('Content-Type', '')
				if 'xml' in content_type.lower() or current_url.endswith('.xml') or self.is_sitemap_url(current_url):
					# Try to process as XML/sitemap
					# Check if this sitemap was redirected to the target domain
					final_url = response.geturl()
					final_domain = urlparse(final_url).netloc
					redirected_to_target = (current_url != final_url and final_domain == self.target_domain)

					if self.process_xml_content(msg, current_url, redirected_to_target):
						# Successfully processed as sitemap, no need to continue with HTML processing
						return

				# Get the last modify date
				if 'last-modified' in response.headers:
					date = response.headers['Last-Modified']
				else:
					date = response.headers['Date']

				date = datetime.strptime(date, '%a, %d %b %Y %H:%M:%S %Z')

			except Exception as e:
				logging.debug (f"{e} ===> {current_url}")
				return
		else:
			# Response is None, content not downloaded, just continu and add
			# the link to the sitemap
			msg = "".encode( )
			date = None

		# Image sitemap enabled ?
		image_list = ""
		if self.images:
			# Search for images in the current page.
			images = self.imageregex.findall(msg)
			for image_link in list(set(images)):
				image_link = image_link.decode("utf-8", errors="ignore")

				# Ignore link starting with data:
				if image_link.startswith("data:"):
					continue

				# If path start with // get the current url scheme
				if image_link.startswith("//"):
					image_link = url.scheme + ":" + image_link
				# Append domain if not present
				elif not image_link.startswith(("http", "https")):
					if not image_link.startswith("/"):
						image_link = f"/{image_link}"
					image_link = f'{self.domain.strip("/")}{image_link.replace("./", "/")}'

				# Ignore image if path is in the exclude_url list
				if not self.exclude_url(image_link):
					continue

				# Ignore other domain images
				image_link_parsed = urlparse(image_link)
				if image_link_parsed.netloc != self.target_domain:
					continue


				# Test if images as been already seen and not present in the
				# robot file
				if self.can_fetch(image_link):
					logging.debug(f"Found image : {image_link}")
					image_list = f"{image_list}<image:image><image:loc>{self.htmlspecialchars(image_link)}</image:loc></image:image>"

		# Last mod fetched ?
		lastmod = ""
		if date:
			lastmod = "<lastmod>"+date.strftime('%Y-%m-%dT%H:%M:%S+00:00')+"</lastmod>"
		# Note: that if there was a redirect, `final_url` may be different than
		#       `current_url`, and avoid not parseable content
		final_url = response.geturl() if response is not None else current_url
		
		# Check if the final URL's domain matches the target domain
		# Skip URLs that redirect to a different domain
		if response is not None:
			final_domain = urlparse(final_url).netloc
			if final_domain != self.target_domain:
				logging.info(f"Skipping {final_url} - redirected to different domain ({final_domain} != {self.target_domain})")
				return
			
			# Skip URLs with non-2XX status codes
			status_code = response.getcode()
			if not (200 <= status_code < 300):
				logging.info(f"Skipping {final_url} - non-2XX status code: {status_code}")
				return
				
		url_string = "<url><loc>"+self.htmlspecialchars(final_url)+"</loc>" + lastmod + image_list + "</url>"
		self.url_strings_to_output.append(url_string)

		# Found links
		links = self.linkregex.findall(msg)
		for link in links:
			link = link.decode("utf-8", errors="ignore")
			logging.debug(f"Found : {link}")

			if link.startswith('/'):
				link = url.scheme + '://' + url.netloc + link
			elif link.startswith('#'):
				link = url.scheme + '://' + url.netloc + url.path + link
			elif link.startswith(("mailto", "tel")):
				continue
			elif not link.startswith(('http', "https")):
				link = self.clean_link(urljoin(current_url, link))

			# Remove the anchor part if needed
			if "#" in link:
				link = link[:link.index('#')]

			# Drop attributes if needed
			for toDrop in self.drop:
				link=re.sub(toDrop,'',link)

			# Parse the url to get domain and file extension
			parsed_link = urlparse(link)
			domain_link = parsed_link.netloc
			target_extension = os.path.splitext(parsed_link.path)[1][1:]

			if link in self.crawled_or_crawling:
				continue
			if link in self.urls_to_crawl:
				continue
			if link in self.excluded:
				continue
			if domain_link != self.target_domain:
				continue
			if parsed_link.path in ["", "/"] and parsed_link.query == '':
				continue
			if "javascript" in link:
				continue
			if self.is_image(parsed_link.path):
				continue
			if parsed_link.path.startswith("data:"):
				continue

			# Count one more URL
			self.nb_url+=1

			# Check if the navigation is allowed by the robots.txt
			if not self.can_fetch(link):
				self.exclude_link(link)
				self.nb_rp+=1
				continue

			# Check if the current file extension is allowed or not.
			if target_extension in self.skipext:
				self.exclude_link(link)
				self.nb_exclude+=1
				continue

			# Check if the current url doesn't contain an excluded word
			if not self.exclude_url(link):
				self.exclude_link(link)
				self.nb_exclude+=1
				continue

			self.urls_to_crawl.add(link)

	def write_sitemap_output(self):
		are_multiple_sitemap_files_required = \
			len(self.url_strings_to_output) > self.MAX_URLS_PER_SITEMAP

		# Check URL count difference if max_url_diff is configured
		if self.max_url_diff is not None and self.output:
			old_count = self.count_urls_in_sitemap(self.output)
			new_count = len(self.url_strings_to_output)

			# Only check if there's an existing sitemap file
			if old_count is not None:
				diff = abs(new_count - old_count)
				logging.info(f"URL count comparison - Old: {old_count}, New: {new_count}, Diff: {diff}, Threshold: {self.max_url_diff}")

				if diff > self.max_url_diff:
					logging.error(f"ERROR: URL count difference ({diff}) exceeds threshold ({self.max_url_diff}). Skipping update for {self.domain}.")
					logging.error(f"Old sitemap had {old_count} URLs, new would have {new_count} URLs.")
					raise UrlDiffThresholdExceeded(self.domain, old_count, new_count, self.max_url_diff)
				else:
					logging.info(f"URL count difference check passed ({diff} <= {self.max_url_diff})")

		# Open output file now that threshold check has passed
		if self.output:
			try:
				self.output_file = open(self.output, 'w')
			except:
				logging.error("Output file not available.")
				exit(255)

		# When there are more than 50,000 URLs, the sitemap specification says we have
		# to split the sitemap into multiple files using an index file that points to the
		# location of each sitemap file.  For now, we require the caller to explicitly
		# specify they want to create an index, even if there are more than 50,000 URLs,
		# to maintain backward compatibility.
		#
		# See specification here:
		# https://support.google.com/webmasters/answer/183668?hl=en
		if are_multiple_sitemap_files_required and self.as_index:
			self.write_index_and_sitemap_files()
		else:
			self.write_single_sitemap()

	def write_single_sitemap(self):
		self.write_sitemap_file(self.output_file, self.url_strings_to_output)

	def write_index_and_sitemap_files(self):
		sitemap_index_filename, sitemap_index_extension = os.path.splitext(self.output)

		num_sitemap_files = math.ceil(len(self.url_strings_to_output) / self.MAX_URLS_PER_SITEMAP)
		sitemap_filenames = []
		for i in range(0, num_sitemap_files):
			# name the individual sitemap files based on the name of the index file
			sitemap_filename = sitemap_index_filename + '-' + str(i) + sitemap_index_extension
			sitemap_filenames.append(sitemap_filename)

		self.write_sitemap_index(sitemap_filenames)

		for i, sitemap_filename in enumerate(sitemap_filenames):
			self.write_subset_of_urls_to_sitemap(sitemap_filename, i * self.MAX_URLS_PER_SITEMAP)

	def write_sitemap_index(self, sitemap_filenames):
		sitemap_index_file = self.output_file
		print(config.sitemapindex_header, file=sitemap_index_file)
		for sitemap_filename in sitemap_filenames:
			sitemap_url = urlunsplit([self.scheme, self.target_domain, sitemap_filename, '', ''])
			print("<sitemap><loc>" + sitemap_url + "</loc>""</sitemap>", file=sitemap_index_file)
		print(config.sitemapindex_footer, file=sitemap_index_file)

	def write_subset_of_urls_to_sitemap(self, filename, index):
		# Writes a maximum of self.MAX_URLS_PER_SITEMAP urls to a sitemap file
		#
		# filename: name of the file to write the sitemap to
		# index:    zero-based index from which to start writing url strings contained in
		#           self.url_strings_to_output
		try:
			with open(filename, 'w') as sitemap_file:
				start_index = index
				end_index = (index + self.MAX_URLS_PER_SITEMAP)
				sitemap_url_strings = self.url_strings_to_output[start_index:end_index]
				self.write_sitemap_file(sitemap_file, sitemap_url_strings)
		except:
			logging.error("Could not open sitemap file that is part of index.")
			exit(255)

	@staticmethod
	def write_sitemap_file(file, url_strings):
		print(config.xml_header, file=file)

		for url_string in url_strings:
			print (url_string, file=file)

		print (config.xml_footer, file=file)

	@staticmethod
	def count_urls_in_sitemap(filepath):
		"""
		Count the number of URLs in an existing sitemap file.
		For regular sitemaps: returns the count of <url> entries.
		For sitemap indexes: returns the combined count of all URLs across all referenced sitemap files.
		Returns None if the file doesn't exist.
		"""
		if not os.path.exists(filepath):
			return None

		try:
			tree = ET.parse(filepath)
			root = tree.getroot()

			# Remove namespace from tag for easier comparison
			# Sitemaps use xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
			tag = root.tag.replace('{http://www.sitemaps.org/schemas/sitemap/0.9}', '')

			if tag == 'urlset':
				# Regular sitemap - count <url> entries
				url_elements = root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}url')
				return len(url_elements)
			elif tag == 'sitemapindex':
				# Sitemap index - count combined URLs from all referenced sitemaps
				sitemap_elements = root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap')
				total_count = 0

				base_dir = os.path.dirname(filepath)

				for sitemap_elem in sitemap_elements:
					loc_elem = sitemap_elem.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
					if loc_elem is not None and loc_elem.text:
						# Extract the filename from the URL
						# URLs are like: https://domain.com/path/to/sitemap-0.xml
						# We need the local file path
						parsed_url = urlparse(loc_elem.text)
						sitemap_filename = os.path.basename(parsed_url.path)
						sitemap_filepath = os.path.join(base_dir, sitemap_filename)

						# Recursively count URLs in this sitemap file
						count = Crawler.count_urls_in_sitemap(sitemap_filepath)
						if count is not None:
							total_count += count
						else:
							logging.warning(f"Could not count URLs in referenced sitemap: {sitemap_filepath}")

				return total_count
			else:
				logging.warning(f"Unknown sitemap root tag: {tag}")
				return None
		except Exception as e:
			logging.error(f"Error parsing sitemap file {filepath}: {e}")
			return None

	def clean_link(self, link):
		parts = list(urlsplit(link))
		parts[2] = self.resolve_url_path(parts[2])
		return urlunsplit(parts)

	def resolve_url_path(self, path):
		# From https://stackoverflow.com/questions/4317242/python-how-to-resolve-urls-containing/40536115#40536115
		segments = path.split('/')
		segments = [segment + '/' for segment in segments[:-1]] + [segments[-1]]
		resolved = []
		for segment in segments:
			if segment in ('../', '..'):
				if len(resolved) > 0:
					resolved.pop()
			elif segment not in ('./', '.'):
				resolved.append(segment)
		return ''.join(resolved)

	@staticmethod
	def is_image(path):
		mt, me = mimetypes.guess_type(path)
		return mt is not None and mt.startswith("image/")

	def exclude_link(self,link):
		if link not in self.excluded:
			self.excluded.add(link)

	def check_robots(self):
		robots_url = urljoin(self.domain, "robots.txt")
		self.rp = RobotFileParser()
		self.rp.set_url(robots_url)
		self.rp.read()

	def can_fetch(self, link):
		try:
			if self.parserobots:
				if self.rp.can_fetch(self.user_agent, link):
					return True
				else:
					logging.debug(f"Crawling of {link} disabled by robots.txt")
					return False
			else:
				return True
		except:
			# On error continue!
			logging.debug("Error during parsing robots.txt")
			return True

	def is_sitemap_url(self, url):
		"""Check if a URL looks like a sitemap"""
		return url.endswith('.xml') or 'sitemap' in url.lower()

	def parse_sitemap_index(self, content, base_url):
		"""Parse a sitemap index and extract sitemap URLs"""
		sitemap_urls = []
		try:
			root = ET.fromstring(content)
			# Handle namespace
			ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
			# Look for sitemap entries
			for sitemap in root.findall('.//sm:sitemap', ns):
				loc = sitemap.find('sm:loc', ns)
				if loc is not None and loc.text:
					sitemap_urls.append(loc.text.strip())
			# Also try without namespace for compatibility
			if not sitemap_urls:
				for sitemap in root.findall('.//sitemap'):
					loc = sitemap.find('loc')
					if loc is not None and loc.text:
						sitemap_urls.append(loc.text.strip())
		except ET.ParseError as e:
			logging.debug(f"Failed to parse sitemap index: {e}")
		return sitemap_urls

	def parse_sitemap(self, content, base_url, redirected_to_target=False):
		"""Parse a sitemap and extract page URLs

		Args:
			content: XML content as string
			base_url: The URL of the sitemap (unused but kept for compatibility)
			redirected_to_target: True if this sitemap was redirected to target domain

		Returns:
			List of page URLs, normalized to target domain if sitemap was redirected
		"""
		page_urls = []
		try:
			root = ET.fromstring(content)
			# Handle namespace
			ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
			# Look for url entries
			for url in root.findall('.//sm:url', ns):
				loc = url.find('sm:loc', ns)
				if loc is not None and loc.text:
					page_urls.append(loc.text.strip())
			# Also try without namespace for compatibility
			if not page_urls:
				for url in root.findall('.//url'):
					loc = url.find('loc')
					if loc is not None and loc.text:
						page_urls.append(loc.text.strip())

			# If sitemap was redirected to target domain, normalize all URLs
			if redirected_to_target and page_urls:
				normalized_urls = []
				for page_url in page_urls:
					parsed = urlparse(page_url)
					# Replace domain with target domain if different
					if parsed.netloc != self.target_domain:
						# Reconstruct URL with target domain
						normalized_url = f"{self.scheme}://{self.target_domain}{parsed.path}"
						if parsed.query:
							normalized_url += f"?{parsed.query}"
						if parsed.fragment:
							normalized_url += f"#{parsed.fragment}"
						logging.debug(f"Normalized {page_url} -> {normalized_url}")
						normalized_urls.append(normalized_url)
					else:
						normalized_urls.append(page_url)
				return normalized_urls

		except ET.ParseError as e:
			logging.debug(f"Failed to parse sitemap: {e}")
		return page_urls

	def process_xml_content(self, content, current_url, redirected_to_target=False):
		"""Process XML content (sitemap or sitemap index)

		Args:
			content: XML content as bytes
			current_url: The original URL that was requested
			redirected_to_target: True if this URL redirected (301) to the target domain
		"""
		try:
			# Try to decode if it's bytes
			if isinstance(content, bytes):
				content = content.decode('utf-8', errors='ignore')

			# Check if it's a sitemap index
			if '<sitemapindex' in content:
				logging.info(f"Found sitemap index at {current_url}")
				sitemap_urls = self.parse_sitemap_index(content, current_url)
				# Add sitemap URLs to crawl queue WITHOUT exclusion check
				# (we want to process sitemaps even if they're in excluded paths)
				for sitemap_url in sitemap_urls:
					if sitemap_url not in self.crawled_or_crawling:
						self.urls_to_crawl.add(sitemap_url)
						logging.debug(f"Added sitemap to crawl: {sitemap_url}")
				return True
			# Check if it's a regular sitemap
			elif '<urlset' in content:
				logging.info(f"Found sitemap at {current_url}")
				page_urls = self.parse_sitemap(content, current_url, redirected_to_target)
				# Process page URLs from sitemap
				for page_url in page_urls:
					# Only process URLs from the same domain
					if self.target_domain in page_url:
						# Apply exclusion rules
						if not self.exclude_url(page_url):
							logging.debug(f"Excluded URL from sitemap: {page_url}")
							self.nb_exclude += 1
							continue

						# Check if URL was already processed
						if page_url not in self.crawled_or_crawling:
							# Mark as crawled
							self.crawled_or_crawling.add(page_url)

							# Add directly to output (sitemap URLs are already validated)
							url_string = "<url><loc>" + self.htmlspecialchars(page_url) + "</loc></url>"
							self.url_strings_to_output.append(url_string)
							self.nb_url += 1

							logging.debug(f"Added URL from sitemap to output: {page_url}")
				return True
		except Exception as e:
			logging.debug(f"Error processing XML content: {e}")
		return False

	def exclude_url(self, link):
		for ex in self.exclude:
			if ex in link:
				return False
		return True

	@staticmethod
	def htmlspecialchars(text):
		return text.replace(" ", "%20").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")

	def make_report(self):
		print ("Number of found URL : {0}".format(self.nb_url))
		print ("Number of links crawled : {0}".format(self.num_crawled))
		if self.parserobots:
			print ("Number of link block by robots.txt : {0}".format(self.nb_rp))
		if self.skipext or self.exclude:
			print ("Number of link exclude : {0}".format(self.nb_exclude))

		for code in self.response_code:
			print ("Nb Code HTTP {0} : {1}".format(code, self.response_code[code]))

		for code in self.marked:
			print ("Link with status {0}:".format(code))
			for uri in self.marked[code]:
				print ("\t- {0}".format(uri))
