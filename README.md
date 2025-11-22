# AEM/Sling JCR Content Crawler

A high-performance Python tool for enumerating and downloading content from Adobe Experience Manager (AEM) / Apache Sling applications by exploiting the `.json` selector vulnerability.

## Features

- **Recursive Crawling**: Automatically discovers and crawls all folders in the JCR repository
- **Asset Download**: Downloads all discovered assets/files with preserved directory structure
- **High Concurrency**: Supports up to 1000+ concurrent requests with asyncio
- **Proxy Support**: Route traffic through HTTP proxies (e.g., Burp Suite, ZAP)
- **Multiple Output Formats**:
  - Real-time console output (ffuf-style)
  - JSON structure map
  - ASCII tree visualization
  - CSV results log
- **Flexible Options**: Download files or just enumerate/catalog them

## Installation

```bash
pip install -r requirements.txt
```

Or install dependencies directly:

```bash
pip install aiohttp
```

## Usage

### Basic Crawl

Enumerate the entire application structure without downloading files:

```bash
python sling_crawler.py https://example.com
```

### Crawl with Proxy (Burp Suite)

Route traffic through an HTTP proxy for inspection:

```bash
python sling_crawler.py https://example.com -p http://127.0.0.1:8080
```

### Download All Assets

Crawl and download all discovered assets to a local directory:

```bash
python sling_crawler.py https://example.com -d ./downloads
```

### High Concurrency

Increase concurrent requests for faster crawling:

```bash
python sling_crawler.py https://example.com -c 500
```

### Save Detailed Results

Save detailed results to a custom JSON file:

```bash
python sling_crawler.py https://example.com -o pentest_results.json
```

### Full Example

Complete pentest setup with all options:

```bash
python sling_crawler.py https://api.example.com \
  -p http://127.0.0.1:8080 \
  -d ./example_downloads \
  -o example_results.json \
  -c 200 \
  -t 60
```

## Command-Line Options

```
usage: sling_crawler.py [-h] [-p PROXY] [-d DOWNLOAD_DIR] [-o OUTPUT_FILE]
                        [-c CONCURRENCY] [-t TIMEOUT] [-u USER_AGENT] url

Arguments:
  url                   Base URL to crawl (e.g., https://example.com)

Options:
  -h, --help            Show help message and exit
  -p, --proxy PROXY     HTTP proxy (e.g., http://127.0.0.1:8080)
  -d, --download-dir DIR
                        Directory to download assets to (optional)
  -o, --output-file FILE
                        Output file for detailed results (optional)
  -c, --concurrency N   Max concurrent requests (default: 100)
  -t, --timeout SECONDS Request timeout in seconds (default: 30)
  -u, --user-agent UA   User-Agent header
```

## Output Files

The crawler automatically generates the following output files (timestamped):

1. **`structure_TIMESTAMP.json`** - Hierarchical JSON map of the entire structure
2. **`results_TIMESTAMP.csv`** - CSV log of all requests (URL, status, size, type)
3. **`tree_TIMESTAMP.txt`** - ASCII tree visualization of the folder structure

## Console Output

Real-time output shows discovered resources in ffuf-style format:

```
[FOLDER] 200 | Size:   4.23 KB | https://example.com/.1.json
[ASSET ] 200 | Size:  12.45 KB | https://example.com/config/settings.json
[ASSET ] 200 | Size: 156.78 KB | https://example.com/assets/logo.png | Saved to ./downloads/assets/logo.png
[ERROR ] 404 | Size:   0.00 B  | https://example.com/missing/.1.json | HTTP 404
```

## How It Works

1. Appends `.1.json` to the base URL to retrieve JCR repository metadata
2. Parses JSON response for objects with:
   - `"jcr:primaryType": "sling:Folder"` - Folders to recursively crawl
   - `"jcr:primaryType": "dam:Asset"` - Assets/files to download
3. Recursively crawls all discovered folders
4. Downloads or logs all discovered assets
5. Generates multiple output formats for analysis

## Vulnerability Details

This tool exploits the Apache Sling JSON selector feature which exposes the JCR (Java Content Repository) structure as JSON. When misconfigured, it can reveal:

- Internal application structure
- Configuration files
- Sensitive assets
- Authentication settings
- API endpoints
- Database connection strings

## Typical Targets

- Adobe Experience Manager (AEM)
- Apache Sling applications
- Day CQ5 (legacy AEM)
- Any application built on JCR

## Performance Tuning

For maximum speed on high-bandwidth connections:

```bash
# 500 concurrent connections
python sling_crawler.py https://example.com -c 500 -t 60

# 1000 concurrent connections (careful with this!)
python sling_crawler.py https://example.com -c 1000 -t 90
```

**Note**: High concurrency values may:
- Trigger rate limiting or WAF blocks
- Cause connection errors on slower networks
- Impact target server performance
- Generate significant proxy logs

Start with default values (100) and increase as needed.

## Ethical Use

This tool is designed for authorized security testing only. Ensure you have explicit permission before scanning any target. Unauthorized access to computer systems is illegal.

## License

For authorized penetration testing and security research only.
