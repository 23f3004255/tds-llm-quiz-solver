import os
from pathlib import Path
import requests
import tempfile
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


def fetch_page_rendered_html(url:str,timeout_ms: int=60000)->Tuple[str,str]:
    """
    Use playwright to open the page and return the rendered HTML and current URL.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto(url,timeout=timeout_ms)
        page.wait_for_load_state("networkidle",timeout=timeout_ms)
        html = page.content()
        current_url = page.url
        browser.close()
    return html,current_url


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
