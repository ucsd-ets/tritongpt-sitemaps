#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
import crawler

parser = argparse.ArgumentParser(description='Python SiteMap Crawler')
parser.add_argument('--skipext', action="append", default=[], required=False, help="File extension to skip")
parser.add_argument('-n', '--num-workers', type=int, default=1, help="Number of workers if multithreading")
parser.add_argument('--parserobots', action="store_true", default=False, required=False, help="Ignore file defined in robots.txt")
parser.add_argument('--user-agent', action="store", default="*", help="Use the rules defined in robots.txt for a specific User-agent (i.e. Googlebot)")
parser.add_argument('--debug', action="store_true", default=False, help="Enable debug mode")
parser.add_argument('--auth', action="store_true", default=False, help="Enable basic authorisation while crawling")
parser.add_argument('-v', '--verbose', action="store_true", help="Enable verbose output")
parser.add_argument('--output', action="store", default=None, help="Output file")
parser.add_argument('--as-index', action="store_true", default=False, required=False, help="Outputs sitemap as index and multiple sitemap files if crawl results in more than 50,000 links (uses filename in --output as name of index file)")
parser.add_argument('--no-sort',  action="store_false", default=True, required=False, help="Disables sorting the output URLs alphabetically", dest='sort_alphabetically')
parser.add_argument('--exclude', action="append", default=[], required=False, help="Exclude Url if contain")
parser.add_argument('--drop', action="append", default=[], required=False, help="Drop a string from the url")
parser.add_argument('--report', action="store_true", default=False, required=False, help="Display a report")
parser.add_argument('--images', action="store_true", default=False, required=False, help="Add image to sitemap.xml (see https://support.google.com/webmasters/answer/178636?hl=en)")
parser.add_argument('--sitemap-url', action="store", default=None, required=False, help="Custom sitemap URL(s) to process (can be sitemap index or regular sitemap)", dest='sitemap_url')
parser.add_argument('--sitemap-only', action="store_true", default=False, required=False, help="Only process sitemaps, do not crawl HTML pages", dest='sitemap_only')
parser.add_argument('--max-url-diff', type=int, action="store", default=None, required=False, help="Abort if URL count changes by more than ±N from existing sitemap", dest='max_url_diff')

group = parser.add_mutually_exclusive_group()
group.add_argument('--config', action="store", default=None, help="Configuration file in json format")
group.add_argument('--domain', action="store", default="", help="Target domain (ex: http://blog.lesite.us)")

arg = parser.parse_args()
# Read the config file if needed
if arg.config is not None:
    try:
        config_data = open(arg.config, 'r')
        configs = json.load(config_data)
        config_data.close()
    except Exception as e:
        configs = []
else:
    # If no config file, create a single config from command-line args
    configs = [{}]

# Track failures to report at the end
failed_domains = []

# Loop through each configuration and run the crawler
for config in configs:
    dict_arg = arg.__dict__.copy()
    for argument in config:
        if argument in dict_arg:
            dict_arg[argument] = config[argument]
    # Remove 'config' argument as it's not a Crawler parameter
    if 'config' in dict_arg:
        del dict_arg['config']

    if dict_arg["domain"] == "":
        print("You must provide a domain to use the crawler.")
        continue

    try:
        crawl = crawler.Crawler(**dict_arg)
        crawl.run()

        if arg.report:
            crawl.make_report()
    except crawler.UrlDiffThresholdExceeded as e:
        # Collect the failure but continue processing other configs
        failed_domains.append({
            'domain': e.domain,
            'old_count': e.old_count,
            'new_count': e.new_count,
            'diff': e.diff,
            'threshold': e.threshold
        })
        print(f"SKIPPED: {e.domain} - URL count changed by {e.diff} (threshold: {e.threshold})")

# Report all failures at the end
if failed_domains:
    print("\n" + "="*80)
    print("SITEMAP GENERATION FAILURES:")
    print("="*80)
    for failure in failed_domains:
        print(f"\nDomain: {failure['domain']}")
        print(f"  Old URL count: {failure['old_count']}")
        print(f"  New URL count: {failure['new_count']}")
        print(f"  Difference: {failure['diff']} (threshold: {failure['threshold']})")
    print("\n" + "="*80)
    print(f"Total failures: {len(failed_domains)}")
    print("="*80)
    exit(2)