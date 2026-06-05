import json
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RAW_FOLDER = ROOT / "source_data" / "raw" / "shlokam_org"
CLEANED_FOLDER = ROOT / "source_data" / "cleaned" / "shlokam_org"
SOURCE_LIST = RAW_FOLDER / "shlokam_source_list.json"

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

                # Skip visible section labels like Sanskrit, Translation, etc.
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
        text = unescape(text)
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

def main():
    CLEANED_FOLDER.mkdir(parents=True, exist_ok=True)

    with open(SOURCE_LIST, "r", encoding="utf-8-sig") as file:
        sources = json.load(file)

    for item in sources:
        shloka_id = item["id"]
        title = item["title"]
        source_url = item["sourceUrl"]

        raw_file = RAW_FOLDER / f"{shloka_id}.html"
        cleaned_file = CLEANED_FOLDER / f"{shloka_id}.clean.json"

        print(f"Cleaning: {title}")

        html = raw_file.read_text(encoding="utf-8")

        parser = DetailSectionParser()
        parser.feed(html)

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

        cleaned_file.write_text(
            json.dumps(cleaned_data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        print(f"Created: {cleaned_file}")
        print(f"Stanzas found: {len(content_blocks)}")
        print()

    print("Done.")

if __name__ == "__main__":
    main()
