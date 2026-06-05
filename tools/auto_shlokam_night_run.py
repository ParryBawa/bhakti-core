import json
import re
import time
import html
import subprocess
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]

RAW_FOLDER = ROOT / "source_data" / "raw" / "shlokam_org"
CLEANED_FOLDER = ROOT / "source_data" / "cleaned" / "shlokam_org"
REVIEWED_FOLDER = ROOT / "source_data" / "reviewed" / "shlokam_org"
DATABASE_FOLDER = ROOT / "database"
DOCS_FOLDER = ROOT / "docs"
AUDIO_FOLDER = ROOT / "audio"

BASE_URL = "https://shlokam.org"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/ParryBawa/bhakti-core/main"

REQUEST_DELAY_SECONDS = 0.75
MAX_DETAIL_PAGES = 1000

USER_AGENT = "BhaktiSangrahDatabaseBuilder/1.0"

KEEP_FIELDS = {
    "sanskrit": "original",
    "roman": "transliteration",
    "translation": "translation",
    "word_meaning": "meanings",
    "verse_notes": "notes"
}

LABELS_TO_REMOVE = [
    "Sanskrit",
    "Transliteration",
    "Translation",
    "Word-meanings",
    "Word meanings",
    "Notes"
]

SKIP_DATABASE_FILES = {
    "registry.json"
}

DEITY_SEEDS = [
    "Annapurna",
    "Ayyappa",
    "Dakshinamurthy",
    "Deepam",
    "Devi",
    "Durga",
    "Ganesha",
    "Ganga",
    "Govinda",
    "Guru",
    "Hanuman",
    "Kamadhenu",
    "Krishna",
    "Lakshmi",
    "Lalitha",
    "Meenakshi",
    "Muruga",
    "Narasimha",
    "Navagraha",
    "Om",
    "Pancha Bhuta",
    "Parvati",
    "Rama",
    "Rishis",
    "Sankara",
    "Shankara",
    "Saraswati",
    "Sarvam",
    "Shani",
    "Shanti",
    "Sharada",
    "Shiva",
    "Surya",
    "Tulasi",
    "Vishnu"
]

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.parts.append("\n")

    def get_text(self):
        text = "".join(self.parts)
        text = html.unescape(text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

class DetailSectionParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sections = []
        self.in_section = False
        self.current_field = None
        self.current_parts = []
        self.depth = 0
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        class_name = attrs_dict.get("class", "")

        if tag == "div" and "detail-section" in class_name and attrs_dict.get("data-field"):
            self.in_section = True
            self.current_field = attrs_dict.get("data-field")
            self.current_parts = []
            self.depth = 1
            self.skip_depth = 0
            return

        if self.in_section:
            if tag == "div":
                self.depth += 1
                if "detail-section-title" in class_name:
                    self.skip_depth = self.depth
            elif tag == "br" and self.skip_depth == 0:
                self.current_parts.append("\n")

    def handle_endtag(self, tag):
        if self.in_section and tag == "div":
            if self.skip_depth == self.depth:
                self.skip_depth = 0

            self.depth -= 1

            if self.depth == 0:
                text = self.clean_text("".join(self.current_parts))
                text = self.remove_leading_labels(text)

                self.sections.append({
                    "field": self.current_field,
                    "text": text
                })

                self.in_section = False
                self.current_field = None
                self.current_parts = []
                self.skip_depth = 0

    def handle_data(self, data):
        if self.in_section and self.skip_depth == 0:
            self.current_parts.append(data)

    def clean_text(self, text):
        text = html.unescape(text)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n[ \t]+", "\n", text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def remove_leading_labels(self, text):
        for label in LABELS_TO_REMOVE:
            if text.startswith(label):
                text = text[len(label):].strip()
        return text

def fetch_url(url):
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT
        }
    )

    with urlopen(request, timeout=45) as response:
        raw = response.read()

    return raw.decode("utf-8", errors="replace")

def normalize_url(url):
    url = url.strip()
    url = url.replace("\\/", "/")
    url = html.unescape(url)
    url, _fragment = urldefrag(url)
    if url.startswith("//"):
        url = "https:" + url
    if url.startswith("/"):
        url = urljoin(BASE_URL, url)
    return url

def is_shloka_detail_url(url):
    parsed = urlparse(url)
    if parsed.netloc.replace("www.", "") != "shlokam.org":
        return False

    if not parsed.path.startswith("/shloka/"):
        return False

    if not parsed.path.endswith(".htm"):
        return False

    filename = Path(parsed.path).name.lower()

    if filename in [
        "deities.htm",
        "types.htm",
        "search.htm",
        "index.htm"
    ]:
        return False

    return True

def extract_links_from_text(text):
    found = set()

    patterns = [
        r'https?://(?:www\.)?shlokam\.org/shloka/[^"\'<>\s#]+?\.htm',
        r'["\'](/shloka/[^"\'<#]+?\.htm)["\']',
        r'["\'](https?://(?:www\.)?shlokam\.org/shloka/[^"\'<#]+?\.htm)["\']'
    ]

    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            if isinstance(match, tuple):
                match = match[0]
            url = normalize_url(match)
            if is_shloka_detail_url(url):
                found.add(url)

    return found

def discover_from_sitemaps():
    discovered = set()
    sitemap_candidates = [
        "https://shlokam.org/sitemap.xml",
        "https://shlokam.org/sitemap-index.xml",
        "https://shlokam.org/sitemap_index.xml",
        "https://shlokam.org/sitemap.txt"
    ]

    to_try = list(sitemap_candidates)
    tried = set()

    while to_try:
        url = to_try.pop(0)
        if url in tried:
            continue

        tried.add(url)

        try:
            text = fetch_url(url)
        except Exception:
            continue

        locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", text, flags=re.IGNORECASE | re.DOTALL)

        if not locs and "\n" in text:
            locs = [line.strip() for line in text.splitlines() if line.strip().startswith("http")]

        for loc in locs:
            loc = normalize_url(loc)

            if "sitemap" in loc.lower() and loc not in tried:
                to_try.append(loc)
                continue

            if is_shloka_detail_url(loc):
                discovered.add(loc)

    return discovered

def discover_from_seed_pages():
    discovered = set()

    seed_urls = [
        "https://shlokam.org/",
        "https://shlokam.org/shloka/deities.htm",
        "https://shlokam.org/shloka/types.htm"
    ]

    for deity in DEITY_SEEDS:
        seed_urls.append("https://shlokam.org/shloka/deities.htm?deity=" + deity.replace(" ", "%20"))

    for seed_url in seed_urls:
        try:
            text = fetch_url(seed_url)
            discovered.update(extract_links_from_text(text))
            time.sleep(REQUEST_DELAY_SECONDS)
        except Exception:
            continue

    return discovered

def load_existing_database_ids():
    existing = set()

    for path in DATABASE_FOLDER.glob("*.json"):
        if path.name in SKIP_DATABASE_FILES:
            continue

        if path.name.startswith("registry."):
            continue

        existing.add(path.stem)

    return existing

def id_from_url(url):
    filename = Path(urlparse(url).path).stem
    shloka_id = filename.lower().replace("-", "_")
    shloka_id = re.sub(r"[^a-z0-9_]+", "_", shloka_id)
    shloka_id = re.sub(r"_+", "_", shloka_id).strip("_")
    return shloka_id

def strip_tags(fragment):
    parser = TextExtractor()
    parser.feed(fragment)
    return parser.get_text()

def title_from_html(html_text, fallback_id):
    title = ""

    match = re.search(
        r'<h2[^>]*class="[^"]*detail-description-title[^"]*"[^>]*>(.*?)</h2>',
        html_text,
        flags=re.IGNORECASE | re.DOTALL
    )

    if match:
        title = strip_tags(match.group(1))

    if not title:
        match = re.search(r"<title>(.*?)</title>", html_text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            title = strip_tags(match.group(1))

    title = title.replace(" - In Sanskrit, English with meaning, explanation", "")
    title = title.replace(" - In Sanskrit, English with meaning", "")
    title = title.replace(" - In Sanskrit, English and other languages", "")
    title = title.strip(" -\n\t")

    if not title:
        title = fallback_id.replace("_", " ").title()

    return title

def build_blocks(sections):
    blocks = []
    current_block = None

    for section in sections:
        source_field = section["field"]
        text = section["text"]

        if source_field not in KEEP_FIELDS:
            continue

        target_field = KEEP_FIELDS[source_field]

        if source_field == "sanskrit":
            current_block = {
                "stanzaNumber": len(blocks) + 1,
                "original": text,
                "transliteration": "",
                "translation": "",
                "meanings": "",
                "notes": ""
            }
            blocks.append(current_block)
            continue

        if current_block is not None:
            current_block[target_field] = text

    return blocks

def clean_html_to_reviewed(shloka_id, title, source_url, html_text):
    parser = DetailSectionParser()
    parser.feed(html_text)

    content_blocks = build_blocks(parser.sections)

    cleaned_data = {
        "id": shloka_id,
        "title": title,
        "source": {
            "sourceId": "shlokam_org",
            "sourceUrl": source_url
        },
        "contentBlocks": content_blocks
    }

    return cleaned_data

def is_good_enough_for_database(data):
    blocks = data.get("contentBlocks", [])

    if not blocks:
        return False, "no content blocks"

    missing_required = []

    for block in blocks:
        stanza = block.get("stanzaNumber", "")
        if not str(block.get("original", "")).strip():
            missing_required.append(f"stanza {stanza}: missing original")
        if not str(block.get("transliteration", "")).strip():
            missing_required.append(f"stanza {stanza}: missing transliteration")
        if not str(block.get("translation", "")).strip():
            missing_required.append(f"stanza {stanza}: missing translation")

    if missing_required:
        return False, "; ".join(missing_required[:5])

    return True, ""

def make_app_ready_data(reviewed_data):
    shloka_id = reviewed_data["id"]
    title = reviewed_data["title"]

    audio_file = AUDIO_FOLDER / f"{shloka_id}.mp3"

    if audio_file.exists():
        audio_name = f"{shloka_id}.mp3"
        audio_stream = f"{GITHUB_RAW_BASE}/audio/{audio_name}"
    else:
        audio_name = ""
        audio_stream = ""

    app_blocks = []

    for block in reviewed_data.get("contentBlocks", []):
        app_blocks.append({
            "stanzaNumber": block.get("stanzaNumber", ""),
            "original": block.get("original", ""),
            "transliteration": block.get("transliteration", ""),
            "translation": block.get("translation", ""),
            "meanings": block.get("meanings", "")
        })

    return {
        "title": title,
        "audioStream": audio_stream,
        "audioName": audio_name,
        "contentBlocks": app_blocks
    }

def export_to_database(reviewed_data):
    shloka_id = reviewed_data["id"]
    output_file = DATABASE_FOLDER / f"{shloka_id}.json"

    app_ready = make_app_ready_data(reviewed_data)

    output_file.write_text(
        json.dumps(app_ready, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

def rebuild_registry():
    entries = []

    for json_file in sorted(DATABASE_FOLDER.glob("*.json")):
        if json_file.name == "registry.json":
            continue

        if json_file.name.startswith("registry."):
            continue

        try:
            data = json.loads(json_file.read_text(encoding="utf-8-sig"))
        except Exception:
            continue

        title = str(data.get("title", "")).strip()

        if not title:
            continue

        entries.append({
            "id": json_file.stem,
            "title": title,
            "fetchUrl": f"{GITHUB_RAW_BASE}/database/{json_file.name}"
        })

    registry_file = DATABASE_FOLDER / "registry.json"

    registry_file.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    return entries

def update_backlog(imported):
    backlog_file = DOCS_FOLDER / "content_backlog.md"

    if backlog_file.exists():
        backlog_text = backlog_file.read_text(encoding="utf-8-sig")
    else:
        backlog_text = "# Bhakti Sangrah Content Backlog\n\n"

    additions = []

    for item in imported:
        shloka_id = item["id"]
        title = item["title"]
        database_file = DATABASE_FOLDER / f"{shloka_id}.json"
        audio_file = AUDIO_FOLDER / f"{shloka_id}.mp3"

        data = json.loads(database_file.read_text(encoding="utf-8-sig"))

        missing_meanings = [
            block.get("stanzaNumber", "")
            for block in data.get("contentBlocks", [])
            if not str(block.get("meanings", "")).strip()
        ]

        if missing_meanings and f"| {shloka_id} |" not in backlog_text:
            additions.append(
                f"| {shloka_id} | {title} | Missing Word Meanings | {len(missing_meanings)} stanza(s) missing word meanings. |"
            )

        if not audio_file.exists() and f"| {shloka_id} | {title} | Missing Audio |" not in backlog_text:
            additions.append(
                f"| {shloka_id} | {title} | Missing Audio | No local MP3 added yet. |"
            )

    if additions:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        backlog_text += "\n\n## Auto Import Backlog Additions - " + timestamp + "\n\n"
        backlog_text += "| ID | Title | Status | Notes |\n"
        backlog_text += "|---|---|---|---|\n"
        backlog_text += "\n".join(additions)
        backlog_text += "\n"

        backlog_file.write_text(backlog_text, encoding="utf-8")

def write_report(discovered, imported, skipped, failed, registry_entries):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = DOCS_FOLDER / f"shlokam_auto_import_report_{timestamp}.md"

    lines = []
    lines.append("# Shlokam Auto Import Report")
    lines.append("")
    lines.append(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append(f"Discovered detail URLs: {len(discovered)}")
    lines.append(f"Imported new shlokas: {len(imported)}")
    lines.append(f"Skipped: {len(skipped)}")
    lines.append(f"Failed: {len(failed)}")
    lines.append(f"Registry entries after rebuild: {len(registry_entries)}")
    lines.append("")

    lines.append("## Imported")
    lines.append("")
    lines.append("| ID | Title | Stanzas | Missing Meanings |")
    lines.append("|---|---|---:|---:|")
    for item in imported:
        lines.append(f"| {item['id']} | {item['title']} | {item['stanzas']} | {item['missingMeanings']} |")

    lines.append("")
    lines.append("## Skipped")
    lines.append("")
    lines.append("| URL/ID | Reason |")
    lines.append("|---|---|")
    for item in skipped:
        lines.append(f"| {item.get('url_or_id', '')} | {item.get('reason', '')} |")

    lines.append("")
    lines.append("## Failed")
    lines.append("")
    lines.append("| URL | Reason |")
    lines.append("|---|---|")
    for item in failed:
        lines.append(f"| {item.get('url', '')} | {item.get('reason', '')} |")

    report_file.write_text("\n".join(lines), encoding="utf-8")

    return report_file

def git_commit_and_push(imported_count):
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True
    )

    if not status.stdout.strip():
        print("No git changes to commit.")
        return

    subprocess.run(
        ["git", "add", "database", "docs", "tools/auto_shlokam_night_run.py"],
        cwd=ROOT,
        check=True
    )

    status_after_add = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True
    )

    if not status_after_add.stdout.strip():
        print("No staged changes to commit.")
        return

    commit_message = f"Auto import Shlokam.org batch ({imported_count} new)"
    subprocess.run(["git", "commit", "-m", commit_message], cwd=ROOT, check=True)
    subprocess.run(["git", "push"], cwd=ROOT, check=True)

def main():
    RAW_FOLDER.mkdir(parents=True, exist_ok=True)
    CLEANED_FOLDER.mkdir(parents=True, exist_ok=True)
    REVIEWED_FOLDER.mkdir(parents=True, exist_ok=True)
    DATABASE_FOLDER.mkdir(parents=True, exist_ok=True)
    DOCS_FOLDER.mkdir(parents=True, exist_ok=True)

    print("Checking git status before auto run...")
    git_status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True
    )

    if git_status.stdout.strip():
        print("Git working tree is not clean. Please commit or stash first.")
        print(git_status.stdout)
        return

    print("Creating safety tag...")
    tag_name = "before-shlokam-night-run-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    subprocess.run(["git", "tag", tag_name], cwd=ROOT, check=False)
    subprocess.run(["git", "push", "origin", tag_name], cwd=ROOT, check=False)

    print("Discovering Shlokam.org detail URLs...")
    discovered = set()
    discovered.update(discover_from_sitemaps())
    discovered.update(discover_from_seed_pages())

    discovered = sorted(discovered)

    discovered_file = RAW_FOLDER / "shlokam_discovered_urls.json"
    discovered_file.write_text(
        json.dumps(discovered, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"Discovered {len(discovered)} detail URLs.")

    existing_ids = load_existing_database_ids()
    imported = []
    skipped = []
    failed = []

    for index, url in enumerate(discovered[:MAX_DETAIL_PAGES], start=1):
        shloka_id = id_from_url(url)

        if shloka_id in existing_ids:
            skipped.append({
                "url_or_id": shloka_id,
                "reason": "already exists in database"
            })
            continue

        print(f"[{index}/{len(discovered)}] Importing {url}")

        try:
            html_text = fetch_url(url)
        except Exception as error:
            failed.append({
                "url": url,
                "reason": "download failed: " + str(error)
            })
            continue

        raw_file = RAW_FOLDER / f"{shloka_id}.html"
        raw_file.write_text(html_text, encoding="utf-8")

        title = title_from_html(html_text, shloka_id)

        reviewed_data = clean_html_to_reviewed(shloka_id, title, url, html_text)

        cleaned_file = CLEANED_FOLDER / f"{shloka_id}.clean.json"
        reviewed_file = REVIEWED_FOLDER / f"{shloka_id}.reviewed.json"

        cleaned_file.write_text(
            json.dumps(reviewed_data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        ok, reason = is_good_enough_for_database(reviewed_data)

        if not ok:
            skipped.append({
                "url_or_id": url,
                "reason": reason
            })
            time.sleep(REQUEST_DELAY_SECONDS)
            continue

        reviewed_file.write_text(
            json.dumps(reviewed_data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        export_to_database(reviewed_data)

        missing_meanings = [
            block for block in reviewed_data.get("contentBlocks", [])
            if not str(block.get("meanings", "")).strip()
        ]

        imported.append({
            "id": shloka_id,
            "title": title,
            "stanzas": len(reviewed_data.get("contentBlocks", [])),
            "missingMeanings": len(missing_meanings)
        })

        existing_ids.add(shloka_id)

        time.sleep(REQUEST_DELAY_SECONDS)

    registry_entries = rebuild_registry()
    update_backlog(imported)
    report_file = write_report(discovered, imported, skipped, failed, registry_entries)

    print("")
    print("Auto import complete.")
    print(f"Imported: {len(imported)}")
    print(f"Skipped: {len(skipped)}")
    print(f"Failed: {len(failed)}")
    print(f"Report: {report_file}")

    git_commit_and_push(len(imported))

    print("")
    print("Done. Morning review files:")
    print(f"- {report_file}")
    print("- docs/content_backlog.md")
    print("- database/registry.json")

if __name__ == "__main__":
    main()
