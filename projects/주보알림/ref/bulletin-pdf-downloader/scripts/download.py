#!/usr/bin/env python3
"""
Bulletin PDF Downloader

Downloads the latest church bulletin PDF from Korean Catholic websites.
Supports: bstsd.or.kr, maria.catholic.or.kr

Usage:
  python download.py [--site bstsd|maria] [--all] [--url CUSTOM_URL] [--download-dir DIR] [--format table|json] [--verbose]
"""

import os
import sys
import json
import re
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List

import requests
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Constants
DEFAULT_DOWNLOAD_DIR = "/tmp/pdf"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

class PDFExtractor:
    """Base class for PDF extraction from HTML."""

    def extract(self, html: str, base_url: str) -> List[Tuple[datetime, str, str]]:
        """Extract (date, pdf_url, title) tuples from HTML."""
        raise NotImplementedError

class BSTSDExtractor(PDFExtractor):
    """Extract PDF links from bstsd.or.kr."""

    def extract(self, html: str, base_url: str) -> List[Tuple[datetime, str, str]]:
        soup = BeautifulSoup(html, 'lxml')
        links = []

        table = soup.find('table')
        if not table:
            logger.warning("No table found on bstsd page")
            return links

        for row in table.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) < 2:
                continue

            # First cell contains date text: "2026.03.15 사순 제4주일"
            date_text = cells[0].get_text(strip=True)
            date_match = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", date_text)
            if not date_match:
                continue

            year, month, day = map(int, date_match.groups())
            date = datetime(year, month, day)

            # Second cell contains PDF links
            pdf_link = cells[1].find('a', href=re.compile(r'\.pdf$', re.IGNORECASE))
            if pdf_link and pdf_link.get('href'):
                pdf_url = requests.compat.urljoin(base_url, pdf_link['href'])
                links.append((date, pdf_url, date_text))

        return links

class MariaMainExtractor(PDFExtractor):
    """Extract from maria.catholic.or.kr/jubo/ - only Seoul main parish (gyocode=11)"""

    def extract(self, html: str, base_url: str) -> List[Tuple[datetime, str, str]]:
        soup = BeautifulSoup(html, 'lxml')
        candidates = []

        # 메인 페이지의 down.asp?gyocode=11 링크를 직접 찾기
        pdf_links = soup.find_all('a', href=re.compile(r'down\.asp\?gyocode=11'))
        logger.info(f"Found {len(pdf_links)} Seoul (gyocode=11) download links")

        for link in pdf_links:
            href = link.get('href')
            if not href:
                continue

            # 파일명 추출
            filename_match = re.search(r'filenm=([^&"]+)', href)
            if not filename_match:
                continue
            filename = filename_match.group(1)

            # URL 디코딩
            try:
                import urllib.parse
                filename_decoded = urllib.parse.unquote(filename)
            except:
                filename_decoded = filename

            # 날짜 추출
            date = self._parse_date_from_filename(filename_decoded)
            if not date:
                logger.debug(f"Skipped: cannot parse date from '{filename_decoded}'")
                continue

            # 필터: 본당 주보만 (파일명에 '주보' 포함)
            # 중등부/초등부는 '주보' 단어 없이 '주일'만 사용
            if "주보" not in filename_decoded:
                logger.debug(f"Skipped: not main parish (no '주보'): {filename_decoded}")
                continue

            # PDF URL 완성
            pdf_url = requests.compat.urljoin(base_url, href)

            # 제목: 파일명에서 확장자 제거
            title = os.path.splitext(filename_decoded)[0]

            candidates.append((date, pdf_url, title))

        if not candidates:
            logger.warning("No valid main parish bulletin entries found (only 중등/초등 or parsing failed)")
            return []

        # 중복 날짜 처리 (각 날짜당 하나의 항목)
        unique = {}
        for date, url, title in candidates:
            date_str = date.strftime('%Y-%m-%d')
            if date_str not in unique:
                unique[date_str] = (date, url, title)

        result = list(unique.values())
        logger.info(f"Extracted {len(result)} unique main parish bulletin dates")
        return result

    def _parse_date_from_filename(self, filename: str) -> Optional[datetime]:
        """Extract datetime from various filename patterns."""
        # 패턴 1: "2026년 3월22일 주보(PDF).pdf" or "2026년 4월5일 주보(PDF)[2].pdf"
        # 월과 일을 1-2 자리 숫자로 허용 (공백 선택적)
        m = re.search(r'(202[6-9])년\s*(\d{1,2})월\s*(\d{1,2})일', filename)
        if m:
            year, month, day = map(int, m.groups())
            try:
                return datetime(year, month, day)
            except ValueError:
                pass

        # 패턴 2: "2026_0322_..." (YYYY_MMDD) - 월/일 1-2 자리 허용
        m = re.search(r'(202[6-9])[_-]?(\d{1,2})[_-]?(\d{1,2})', filename)
        if m:
            year, month, day = map(int, m.groups())
            try:
                return datetime(year, month, day)
            except ValueError:
                pass

        # 패턴 3: "2026-03-22" 형식
        m = re.search(r'(202[6-9])[-\.]?(\d{1,2})[-\.]?(\d{1,2})', filename)
        if m:
            year, month, day = map(int, m.groups())
            try:
                return datetime(year, month, day)
            except ValueError:
                pass

        # 패턴 4: "2236-0322" (缩写的년도 → 2000년대)
        m = re.search(r'([23]\d{2})-?(\d{1,2})-?(\d{1,2})', filename)
        if m:
            year, month, day = map(int, m.groups())
            if year < 100:
                year += 2000
            if 2000 <= year <= 2099:
                try:
                    return datetime(year, month, day)
                except ValueError:
                    pass

        return None

# Site configurations
SITES = {
    "bstsd": {
        "name": "흑석동성당",
        "url": "https://bstsd.or.kr/a/weekly",
        "extractor_class": BSTSDExtractor
    },
    "maria": {
        "name": "가톨릭 굿뉴스 (서울대교구)",
        "url": "https://maria.catholic.or.kr/jubo/",
        "extractor_class": MariaMainExtractor
    }
}

class BulletinDownloader:
    """Main downloader class."""

    def __init__(self, site_name: str, download_dir: str, custom_url: Optional[str] = None):
        self.site_name = site_name
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)

        if site_name not in SITES:
            raise ValueError(f"Unsupported site: {site_name}. Choose from: {list(SITES.keys())}")

        self.config = SITES[site_name]
        self.base_url = custom_url or self.config['url']

        # Extractor
        extractor_cls = self.config.get('extractor_class')
        if extractor_cls:
            self.extractor = extractor_cls()
        else:
            self.extractor = BSTSDExtractor()  # default fallback

        # Session with headers
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://maria.catholic.or.kr/',
        })

    def fetch_page(self) -> str:
        """Fetch the HTML page. Use scrapling for maria to handle JS rendering and get cookies."""
        logger.info(f"Fetching: {self.base_url}")

        if self.site_name == 'maria':
            try:
                from scrapling import StealthyFetcher
                logger.info("Using scrapling for maria page fetch (real_chrome=True, wait=2000ms)")
                fetcher = StealthyFetcher(real_chrome=True)
                response = fetcher.fetch(self.base_url, wait=2000)
                html = response.html_content if hasattr(response, 'html_content') else response.text
                # Transfer cookies from scrapling to requests session
                try:
                    if hasattr(fetcher, 'context'):
                        raw_cookies = fetcher.context.cookies()
                        for cookie in raw_cookies:
                            self.session.cookies.set(
                                cookie.get('name'),
                                cookie.get('value'),
                                domain=cookie.get('domain'),
                                path=cookie.get('path', '/')
                            )
                        logger.debug(f"Transferred {len(raw_cookies)} cookies from scrapling")
                except Exception as e:
                    logger.debug(f"Cookie transfer failed: {e}")
                return html
            except ImportError:
                logger.warning("scrapling not installed, falling back to requests")
            except Exception as e:
                logger.warning(f"scrapling fetch failed: {e}, falling back to requests")

        # Fallback to requests
        logger.info("Using requests fallback for page fetch")
        response = self.session.get(self.base_url, timeout=15)
        response.raise_for_status()
        response.encoding = 'utf-8'
        return response.text

    def find_latest_pdf(self, pdf_data: List[Tuple[datetime, str, str]]) -> Optional[Tuple[datetime, str, str]]:
        """Find the most recent PDF."""
        if not pdf_data:
            return None
        return max(pdf_data, key=lambda x: x[0])

    def download_pdf(self, pdf_url: str, date: datetime, site: str, title_text: str) -> Path:
        """Download PDF to local file."""
        safe_title = re.sub(r'[^\w\s\-]', '', title_text).strip()[:50]
        filename = f"{date.strftime('%Y-%m-%d')}_{site}_{safe_title}.pdf"
        filepath = self.download_dir / filename

        logger.info(f"Downloading: {pdf_url}")
        headers = {'Referer': self.base_url}
        response = self.session.get(pdf_url, headers=headers, stream=True, timeout=30)
        response.raise_for_status()

        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        size = response.headers.get('content-length')
        size_str = f"{int(size)} bytes" if size else "unknown size"
        logger.info(f"Saved: {filepath} ({size_str})")
        return filepath

    def run(self) -> dict:
        """Execute the download process."""
        result = {
            'site': self.site_name,
            'site_name': self.config['name'],
            'url': self.base_url,
            'success': False,
            'date': None,
            'title': None,
            'pdf_url': None,
            'filepath': None,
            'error': None
        }

        try:
            # 1. Fetch page
            html = self.fetch_page()

            # 2. Extract PDF data
            pdf_data = self.extractor.extract(html, self.base_url)
            logger.info(f"Found {len(pdf_data)} PDF links")

            if not pdf_data:
                raise ValueError("No PDF links found on the page")

            # 3. Find latest
            latest = self.find_latest_pdf(pdf_data)
            if not latest:
                raise ValueError("Could not determine latest PDF")

            date, pdf_url, title_text = latest
            result.update({
                'date': date.strftime('%Y-%m-%d'),
                'title': title_text,
                'pdf_url': pdf_url
            })

            # 4. Download
            filepath = self.download_pdf(pdf_url, date, self.site_name, title_text)
            result['filepath'] = str(filepath)
            result['success'] = True

        except Exception as e:
            logger.error(f"Error: {e}")
            result['error'] = str(e)

        return result

def main():
    parser = argparse.ArgumentParser(
        description="Download latest church bulletin PDF",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --site bstsd
  %(prog)s --site maria --download-dir ~/bulletins
  %(prog)s --url https://example.com/weekly --format json
  %(prog)s --all --download-dir ~/bulletins
        """
    )

    parser.add_argument('--site', choices=['bstsd', 'maria'],
                        help='Site name (default: from BULLETIN_SITE env or bstsd)')
    parser.add_argument('--all', action='store_true',
                        help='Download from all sites (bstsd + maria)')
    parser.add_argument('--url', help='Custom URL (overrides --site, cannot be used with --all)')
    parser.add_argument('--download-dir', default=os.getenv('DOWNLOAD_DIR', DEFAULT_DOWNLOAD_DIR),
                        help=f'Download directory (default: {DEFAULT_DOWNLOAD_DIR})')
    parser.add_argument('--format', choices=['table', 'json'], default='table',
                        help='Output format (default: table)')
    parser.add_argument('--verbose', action='store_true', help='Debug logging')

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # Validate arguments
    if args.all and args.url:
        parser.error("--url cannot be used with --all")

    # Determine sites to process
    if args.all:
        sites = ['bstsd', 'maria']
    else:
        site = args.site or os.getenv('BULLETIN_SITE', 'bstsd')
        sites = [site]

    results = []
    for site in sites:
        try:
            downloader = BulletinDownloader(
                site_name=site,
                download_dir=args.download_dir,
                custom_url=args.url if not args.all else None
            )
            result = downloader.run()
            results.append(result)
        except Exception as e:
            logger.exception(f"Unexpected error for site {site}")
            results.append({
                'site': site,
                'site_name': SITES.get(site, {}).get('name', site),
                'success': False,
                'error': str(e)
            })

    # Output results
    if args.format == 'json':
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for result in results:
            print("\n" + "=" * 60)
            print(f"Site: {result.get('site_name', result.get('site'))} ({result.get('site')})")
            if result.get('success'):
                print(f"Latest bulletin: {result['date']} {result['title'][:80]}")
                print(f"PDF URL: {result['pdf_url']}")
                print(f"Download path: {result['filepath']}")
                print("Status: ✅ Downloaded successfully")
            else:
                print(f"Status: ❌ Failed - {result.get('error', 'Unknown error')}")
            print("=" * 60)
        print()  # final newline

    # Exit code: success if any download succeeded
    success = any(r.get('success', False) for r in results)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
