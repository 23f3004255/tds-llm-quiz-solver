import os
from pathlib import Path
import requests
import time
import re
from typing import List,Tuple
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright

from dotenv import load_dotenv
load_dotenv()

DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR","/temp/llm_quiz_file")

def ensure_dir(d):
    Path(d).mkdir(parents=True,exist_ok=True)

ensure_dir(DOWNLOAD_DIR)


def fetch_page_rendered_html(url: str, timeout_ms: int = 60000):
    """
    Fetch fully rendered HTML from a JS-heavy page.
    Robust version for TDS LLM Analysis Quiz.
    """

    MAX_RETRIES = 3
    wait_selector = "#result"  # used in demo pages
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                context = browser.new_context(java_script_enabled=True)
                page = context.new_page()

                # go to page
                page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")

                # wait for JS to load relevant content
                try:
                    page.wait_for_selector(wait_selector, timeout=5000)
                except Exception:
                    # fallback: wait a little extra for JS
                    time.sleep(2)

                # IMPORTANT: evaluate JS fully before extracting
                page.wait_for_load_state("networkidle", timeout=timeout_ms)

                # get FULL rendered HTML
                html = page.evaluate("() => document.documentElement.innerHTML")
                current_url = page.url

                browser.close()
                return html, current_url

        except Exception as e:
            last_error = e
            time.sleep(1)  # retry delay

    # if all retries fail
    print("HTML RENDER ERROR:", last_error)
    return "", url


def find_submit_and_question_from_html(html:str)->Tuple[str,str]:
    submit = None
    m = re.search(r"https?://[^\s'\"<>]+/submit[^\s'\"<>]*", html)
    if m:
        submit = m.group(0)

    q = ""
    m2 = re.search(r'<div[^>]*id=["\']result["\'][^>]*>(.*?)</div>', html, flags=re.DOTALL | re.IGNORECASE)
    if m2:
        q = re.sub(r"<[^>]+>", "", m2.group(1)).strip()
    if not q:
        # fallback: first <pre> contents
        m3 = re.search(r"<pre[^>]*>(.*?)</pre>", html, flags=re.DOTALL | re.IGNORECASE)
        if m3:
            q = re.sub(r"<[^>]+>", "", m3.group(1)).strip()
    return submit, q


def download_links_from_page(url:str, html:str)-> List[str]:
    matches = []
    for ext in [".csv",".pdf",".xlsx",".json",".zip"]:
        import re
        for m in re.finditer(r'href=["\']([^"\']+%s)["\']' % re.escape(ext), html, flags=re.IGNORECASE):
            matches.append(m.group(1))

        saved = []
        for link in matches:
            if link.startswith("//"):
                parsed = urlparse(url)
                link = f"{parsed.scheme}:{link}"
            if not urlparse(link).netloc:
                link = urljoin(url, link)
            try:
                local = download_file(link)
                saved.append(local)
            except Exception as e:
                print("download failed", link, e)
        return saved

def download_file(url: str) -> str:
    """
    Download a file to DOWNLOAD_DIR and return path
    """
    ensure_dir(DOWNLOAD_DIR)
    r = requests.get(url, stream=True, timeout=30)
    r.raise_for_status()
    fname = url.split("/")[-1].split("?")[0]
    if not fname:
        fname = "file.bin"
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", fname)
    path = os.path.join(DOWNLOAD_DIR, safe)
    with open(path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    return path
