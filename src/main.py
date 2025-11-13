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
parser.add_argument('--domain-aliases', action="append", default=[], required=False, help="Alternate domains to accept and normalize to target domain", dest='domain_aliases')
parser.add_argument('--max-url-diff-percent', type=float, action="store", default=50, required=False, help="Abort if URL count changes by more than N%% from existing sitemap (default: 50%%)", dest='max_url_diff_percent')

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
            'diff_percent': e.diff_percent,
            'threshold_percent': e.threshold_percent
        })
        print(f"SKIPPED: {e.domain} - URL count changed by {e.diff} ({e.diff_percent:.1f}%, threshold: {e.threshold_percent}%)")
    except crawler.EmptySitemapError as e:
        # Collect the empty sitemap failure
        failed_domains.append({
            'domain': e.domain,
            'old_count': 'N/A',
            'new_count': 0,
            'diff': 'N/A',
            'diff_percent': 100.0,
            'threshold_percent': 'N/A'
        })
        print(f"SKIPPED: {e.domain} - Sitemap is empty (0 URLs)")

# Report all failures at the end
if failed_domains:
    failure_summary = []
    failure_summary.append("="*80)
    failure_summary.append("SITEMAP GENERATION FAILURES:")
    failure_summary.append("="*80)
    for failure in failed_domains:
        failure_summary.append(f"\nDomain: {failure['domain']}")
        failure_summary.append(f"  Old URL count: {failure['old_count']}")
        failure_summary.append(f"  New URL count: {failure['new_count']}")
        # Handle both numeric and string values for diff_percent
        diff_percent_str = f"{failure['diff_percent']:.1f}%" if isinstance(failure['diff_percent'], (int, float)) else str(failure['diff_percent'])
        failure_summary.append(f"  Difference: {failure['diff']} ({diff_percent_str})")
        # Handle both numeric and string values for threshold_percent
        threshold_str = f"{failure['threshold_percent']}%" if failure['threshold_percent'] != 'N/A' else failure['threshold_percent']
        failure_summary.append(f"  Threshold: {threshold_str}")
    failure_summary.append("\n" + "="*80)
    failure_summary.append(f"Total failures: {len(failed_domains)}")
    failure_summary.append("="*80)

    # Print to console
    print("\n" + "\n".join(failure_summary))

    # Save to file for GitHub Actions
    with open('sitemap_failures.txt', 'w') as f:
        f.write("\n".join(failure_summary))

    exit(2)