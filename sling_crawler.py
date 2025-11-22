#!/usr/bin/env python3
"""
AEM/Sling JCR Content Crawler
Recursively crawls Adobe Experience Manager / Apache Sling applications
by exploiting the .json selector to enumerate folders and download assets.
"""

import asyncio
import httpx
import argparse
import json
import csv
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime
from typing import Dict, Set, List, Optional, Tuple


class SlingCrawler:
    def __init__(
        self,
        base_url: str,
        proxy: Optional[str] = None,
        output_dir: Optional[str] = None,
        output_file: Optional[str] = None,
        max_concurrent: int = 100,
        timeout: int = 30,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    ):
        self.base_url = base_url.rstrip('/')
        self.proxy = proxy
        self.output_dir = Path(output_dir) if output_dir else None
        self.output_file = output_file
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self.user_agent = user_agent

        # State tracking
        self.visited_urls: Set[str] = set()
        self.structure: Dict = {}
        self.results: List[Dict] = []
        self.stats = {
            'folders': 0,
            'assets': 0,
            'errors': 0,
            'total_bytes': 0,
            'start_time': None,
            'end_time': None
        }

        # Create output directory if needed
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)

        # Semaphore for rate limiting
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_json(self, client: httpx.AsyncClient, url: str) -> Tuple[Optional[Dict], int, int]:
        """Fetch JSON content from URL with .1.json appended"""
        json_url = f"{url}/.1.json" if not url.endswith('.json') else url

        if json_url in self.visited_urls:
            return None, 0, 0

        self.visited_urls.add(json_url)

        async with self.semaphore:
            try:
                response = await client.get(json_url)
                status = response.status_code
                content = response.content
                size = len(content)

                if status == 200:
                    try:
                        data = json.loads(content.decode('utf-8', errors='ignore'))
                        self._log_result(json_url, status, size, 'folder')
                        return data, status, size
                    except json.JSONDecodeError:
                        self._log_result(json_url, status, size, 'error', 'Invalid JSON')
                        self.stats['errors'] += 1
                        return None, status, size
                else:
                    self._log_result(json_url, status, size, 'error', f'HTTP {status}')
                    self.stats['errors'] += 1
                    return None, status, size

            except httpx.TimeoutException:
                self._log_result(json_url, 0, 0, 'error', 'Timeout')
                self.stats['errors'] += 1
                return None, 0, 0
            except Exception as e:
                self._log_result(json_url, 0, 0, 'error', str(e))
                self.stats['errors'] += 1
                return None, 0, 0

    async def fetch_asset(self, client: httpx.AsyncClient, url: str, relative_path: str) -> None:
        """Fetch an asset/file and optionally save it"""
        if url in self.visited_urls:
            return

        self.visited_urls.add(url)

        async with self.semaphore:
            try:
                response = await client.get(url)
                status = response.status_code
                content = response.content
                size = len(content)

                self.stats['total_bytes'] += size

                if status == 200:
                    self.stats['assets'] += 1

                    # Save file if output directory specified
                    if self.output_dir:
                        file_path = self.output_dir / relative_path.lstrip('/')
                        file_path.parent.mkdir(parents=True, exist_ok=True)
                        file_path.write_bytes(content)
                        self._log_result(url, status, size, 'asset', f'Saved to {file_path}')
                    else:
                        self._log_result(url, status, size, 'asset')
                else:
                    self._log_result(url, status, size, 'error', f'HTTP {status}')
                    self.stats['errors'] += 1

            except httpx.TimeoutException:
                self._log_result(url, 0, 0, 'error', 'Timeout')
                self.stats['errors'] += 1
            except Exception as e:
                self._log_result(url, 0, 0, 'error', str(e))
                self.stats['errors'] += 1

    def _log_result(self, url: str, status: int, size: int, type: str, message: str = ''):
        """Log result to console and results list"""
        result = {
            'url': url,
            'status': status,
            'size': size,
            'type': type,
            'message': message,
            'timestamp': datetime.now().isoformat()
        }
        self.results.append(result)

        # Console output (ffuf-style)
        size_str = self._format_size(size)
        status_str = f"{status:3d}" if status > 0 else "ERR"
        type_str = f"[{type.upper():6s}]"

        if type == 'error':
            print(f"{type_str} {status_str} | Size: {size_str:>10s} | {url} | {message}")
        else:
            msg_suffix = f" | {message}" if message else ""
            print(f"{type_str} {status_str} | Size: {size_str:>10s} | {url}{msg_suffix}")

    def _format_size(self, size: int) -> str:
        """Format size in human-readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} TB"

    async def crawl_path(self, client: httpx.AsyncClient, path: str, parent_structure: Dict) -> None:
        """Recursively crawl a path and its children"""
        # Construct URL properly - use base_url for root, otherwise append path
        if not path or path == '/':
            url = self.base_url
        else:
            # Remove leading slash and append to base_url
            url = f"{self.base_url}/{path.lstrip('/')}"

        data, status, size = await self.fetch_json(client, url)

        if not data:
            return

        self.stats['folders'] += 1

        # Tasks for parallel processing
        tasks = []

        # Parse the JSON structure
        for key, value in data.items():
            # Skip JCR metadata keys
            if key.startswith('jcr:'):
                continue

            if not isinstance(value, dict):
                continue

            primary_type = value.get('jcr:primaryType', '')

            # Build child path properly
            if not path or path == '/':
                child_path = key
            else:
                child_path = f"{path.rstrip('/')}/{key}"

            # Store in structure
            if key not in parent_structure:
                parent_structure[key] = {'_type': primary_type, '_children': {}}

            if primary_type == 'sling:Folder' or primary_type == 'nt:unstructured':
                # Recursively crawl folders
                tasks.append(self.crawl_path(client, child_path, parent_structure[key]['_children']))

            elif primary_type == 'dam:Asset':
                # Fetch asset/file
                asset_url = f"{self.base_url}/{child_path.lstrip('/')}"
                tasks.append(self.fetch_asset(client, asset_url, child_path))

        # Execute all tasks concurrently
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def crawl(self) -> None:
        """Main crawl entry point"""
        self.stats['start_time'] = time.time()

        print(f"\n{'='*80}")
        print(f"Starting Sling/AEM Crawler")
        print(f"{'='*80}")
        print(f"Target: {self.base_url}")
        print(f"Proxy: {self.proxy or 'None'}")
        print(f"Max Concurrent: {self.max_concurrent}")
        print(f"Output Dir: {self.output_dir or 'None (console only)'}")
        print(f"Output File: {self.output_file or 'None'}")
        print(f"{'='*80}\n")

        # Configure httpx client with proxy support and SSL verification disabled
        async with httpx.AsyncClient(
            proxy=self.proxy,  # httpx uses 'proxy' (singular), not 'proxies'
            verify=False,  # Disable SSL verification (like curl -k)
            timeout=self.timeout,
            headers={'User-Agent': self.user_agent},
            limits=httpx.Limits(max_connections=self.max_concurrent)
        ) as client:
            await self.crawl_path(client, '/', self.structure)

        self.stats['end_time'] = time.time()
        self._print_summary()
        self._save_outputs()

    def _print_summary(self) -> None:
        """Print crawl summary statistics"""
        duration = self.stats['end_time'] - self.stats['start_time']
        req_per_sec = len(self.visited_urls) / duration if duration > 0 else 0

        print(f"\n{'='*80}")
        print(f"Crawl Complete")
        print(f"{'='*80}")
        print(f"Total URLs Visited: {len(self.visited_urls)}")
        print(f"Folders Found: {self.stats['folders']}")
        print(f"Assets Found: {self.stats['assets']}")
        print(f"Errors: {self.stats['errors']}")
        print(f"Total Data: {self._format_size(self.stats['total_bytes'])}")
        print(f"Duration: {duration:.2f}s")
        print(f"Requests/sec: {req_per_sec:.2f}")
        print(f"{'='*80}\n")

    def _save_outputs(self) -> None:
        """Save all output formats"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Save JSON structure
        json_file = f"structure_{timestamp}.json"
        with open(json_file, 'w') as f:
            json.dump(self.structure, f, indent=2)
        print(f"[+] Saved JSON structure to: {json_file}")

        # Save CSV results
        csv_file = f"results_{timestamp}.csv"
        with open(csv_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['timestamp', 'type', 'status', 'size', 'url', 'message'])
            writer.writeheader()
            writer.writerows(self.results)
        print(f"[+] Saved CSV results to: {csv_file}")

        # Save tree visualization
        tree_file = f"tree_{timestamp}.txt"
        with open(tree_file, 'w') as f:
            f.write(self._generate_tree(self.structure))
        print(f"[+] Saved tree visualization to: {tree_file}")

        # Save to custom output file if specified
        if self.output_file:
            with open(self.output_file, 'w') as f:
                json.dump({
                    'stats': self.stats,
                    'structure': self.structure,
                    'results': self.results
                }, f, indent=2)
            print(f"[+] Saved detailed output to: {self.output_file}")

    def _generate_tree(self, structure: Dict, prefix: str = '', is_last: bool = True) -> str:
        """Generate ASCII tree visualization"""
        tree = ""
        items = list(structure.items())

        for i, (key, value) in enumerate(items):
            is_last_item = (i == len(items) - 1)
            connector = "└── " if is_last_item else "├── "

            if isinstance(value, dict) and '_type' in value:
                tree += f"{prefix}{connector}{key} ({value['_type']})\n"

                if '_children' in value and value['_children']:
                    extension = "    " if is_last_item else "│   "
                    tree += self._generate_tree(value['_children'], prefix + extension, is_last_item)
            else:
                tree += f"{prefix}{connector}{key}\n"

        return tree


def main():
    parser = argparse.ArgumentParser(
        description='AEM/Sling JCR Content Crawler - Enumerate folders and download assets',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s https://example.com
  %(prog)s https://example.com -p http://127.0.0.1:8080
  %(prog)s https://example.com -d ./downloads -o results.json
  %(prog)s https://example.com -c 500 -t 60
        '''
    )

    parser.add_argument('url', help='Base URL to crawl (e.g., https://example.com)')
    parser.add_argument('-p', '--proxy', help='HTTP proxy (e.g., http://127.0.0.1:8080)')
    parser.add_argument('-d', '--download-dir', help='Directory to download assets to (optional)')
    parser.add_argument('-o', '--output-file', help='Output file for detailed results (optional)')
    parser.add_argument('-c', '--concurrency', type=int, default=100,
                        help='Max concurrent requests (default: 100)')
    parser.add_argument('-t', '--timeout', type=int, default=30,
                        help='Request timeout in seconds (default: 30)')
    parser.add_argument('-u', '--user-agent', default='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        help='User-Agent header')

    args = parser.parse_args()

    # Validate URL
    parsed = urlparse(args.url)
    if not parsed.scheme or not parsed.netloc:
        print(f"Error: Invalid URL '{args.url}'", file=sys.stderr)
        sys.exit(1)

    # Create and run crawler
    crawler = SlingCrawler(
        base_url=args.url,
        proxy=args.proxy,
        output_dir=args.download_dir,
        output_file=args.output_file,
        max_concurrent=args.concurrency,
        timeout=args.timeout,
        user_agent=args.user_agent
    )

    try:
        asyncio.run(crawler.crawl())
    except KeyboardInterrupt:
        print("\n\n[!] Crawl interrupted by user")
        sys.exit(1)


if __name__ == '__main__':
    main()
