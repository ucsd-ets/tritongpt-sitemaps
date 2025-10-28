# Python-Sitemap

Simple script to crawl websites and create a sitemap.xml of all public link in it.

Warning : This script only works with ***Python3***

## Simple usage

	>>> python main.py --domain http://blog.lesite.us --output sitemap.xml

## Advanced usage

Read a config file to set parameters:
***You can overide (or add for list) any parameters define in the config.json***

	>>> python main.py --config config/config.json

#### Enable debug:

  ```
	$ python main.py --domain https://blog.lesite.us --output sitemap.xml --debug
  ```

#### Enable verbose output:

  ```
  $ python main.py --domain https://blog.lesite.us --output sitemap.xml --verbose
  ```

#### Disable sorting output:

  ```
  $ python main.py --domain https://blog.lesite.us --output sitemap.xml --no-sort
  ```


#### Enable Image Sitemap

More informations here https://support.google.com/webmasters/answer/178636?hl=en

  ```
  $ python main.py --domain https://blog.lesite.us --output sitemap.xml --images
  ```

#### Enable report for print summary of the crawl:

  ```
  $ python main.py --domain https://blog.lesite.us --output sitemap.xml --report
  ```

#### Skip url (by extension) (skip pdf AND xml url):

  ```
  $ python main.py --domain https://blog.lesite.us --output sitemap.xml --skipext pdf --skipext xml
  ```

#### Drop a part of an url via regexp :

  ```
  $ python main.py --domain https://blog.lesite.us --output sitemap.xml --drop "id=[0-9]{5}"
  ```

#### Exclude url by filter a part of it :

  ```
  $ python main.py --domain https://blog.lesite.us --output sitemap.xml --exclude "action=edit"
  ```

#### Read the robots.txt to ignore some url:

  ```
  $ python main.py --domain https://blog.lesite.us --output sitemap.xml --parserobots
  ```

#### Use specific user-agent for robots.txt:

  ```
  $ python main.py --domain https://blog.lesite.us --output sitemap.xml --parserobots --user-agent Googlebot
  ```

#### Human readable XML

```
$ python3 main.py --domain https://blog.lesite.us --images --parserobots | xmllint --format -
```

#### Multithreaded

```
$ python3 main.py --domain https://blog.lesite.us --num-workers 4
```

#### with basic auth
***You need to configure `username` and `password` in your `config.py` before***
```
$ python3 main.py --domain https://blog.lesite.us --auth
```

#### Output sitemap index file
***Sitemaps with over 50,000 URLs should be split into an index file that points to sitemap files that each contain 50,000 URLs or fewer.  Outputting as an index requires specifying an output file.  An index will only be output if a crawl has more than 50,000 URLs:***
```
$ python3 main.py --domain https://blog.lesite.us --as-index --output sitemap.xml
```

## Sitemap-specific features

#### Process existing sitemaps

Instead of crawling HTML pages, you can process existing sitemaps or sitemap indexes:

```
$ python main.py --domain https://example.com --sitemap-url https://example.com/sitemap.xml --sitemap-only --output sitemap.xml
```

#### Process sitemap indexes (parent sitemaps)

The crawler automatically detects and recursively processes sitemap indexes. When it encounters a sitemap index (containing `<sitemapindex>` tags), it will:
1. Extract all child sitemap URLs from the index
2. Fetch each child sitemap
3. Extract all page URLs from the child sitemaps
4. Output all discovered URLs to your output file

Example with Berkeley Law's sitemap index:
```
$ python main.py --domain https://www.law.berkeley.edu --sitemap-url https://www.law.berkeley.edu/sitemap_index.xml --sitemap-only --output berkeley_law.xml
```

#### Command-line options for sitemaps

- `--sitemap-url URL`: Specify a custom sitemap URL to process (can be a regular sitemap or sitemap index)
- `--sitemap-only`: Only process the specified sitemap(s), don't crawl HTML pages

#### Config file example for sitemap processing

You can also configure sitemap processing in the config.json file:

```json
{
  "domain": "https://www.law.berkeley.edu",
  "sitemap_url": "https://www.law.berkeley.edu/sitemap_index.xml",
  "sitemap_only": true,
  "output": "berkeley_law.xml",
  "exclude": [],
  "skipext": []
}
```

Then run:
```
$ python main.py --config config/config.json
```

This is particularly useful when you want to:
- Only extract URLs from existing sitemaps without crawling the website
- Process large websites that already have comprehensive sitemaps
- Work with sitemap indexes that contain multiple child sitemaps

#### Manual sitemap with file download
***For static files hosted externally, you can download and generate a sitemap pointing to your repository's hosted version. The `--url-prefix` parameter is optional and defaults to the directory name:***
```
$ python3 manual.py --download-url https://example.com/file.xls --download-dest local-dir/file.xls --directory local-dir --base-url https://raw.githubusercontent.com/user/repo/main --url-prefix local-dir --output sitemap.xml
```

#### Convert Excel files to CSV
***Add `--convert-to-csv` to convert downloaded Excel files to CSV UTF-8 format (one file per worksheet). Requires pandas and openpyxl:***
```
$ python3 manual.py --download-url https://example.com/file.xls --download-dest local-dir/file.xls --convert-to-csv --directory local-dir --base-url https://raw.githubusercontent.com/user/repo/main --url-prefix local-dir --output sitemap.xml
```

## Docker usage

#### Build the Docker image:

  ```
  $ docker build -t python-sitemap:latest .
  ```

#### Run with default domain :

  ```
  $ docker run -it python-sitemap
  ```

#### Run with custom domain :

  ```
  $ docker run -it python-sitemap --domain https://www.graylog.fr
  ```

#### Run with config file and output :
***You need to configure config.json file before***

  ```
  $ docker run -it -v `pwd`/config/:/config/ -v `pwd`:/home/python-sitemap/ python-sitemap --config config/config.json
  ```
