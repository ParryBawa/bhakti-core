import json
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]

SOURCE_LIST = ROOT / "source_data" / "raw" / "shlokam_org" / "shlokam_source_list.json"
RAW_FOLDER = ROOT / "source_data" / "raw" / "shlokam_org"

def download_page(url):
    request = Request(
        url,
        headers={
            "User-Agent": "BhaktiSangrahDatabaseBuilder/1.0"
        }
    )

    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")

def main():
    with open(SOURCE_LIST, "r", encoding="utf-8-sig") as file:
        sources = json.load(file)

    RAW_FOLDER.mkdir(parents=True, exist_ok=True)

    for item in sources:
        shloka_id = item["id"]
        title = item["title"]
        url = item["sourceUrl"]

        output_file = RAW_FOLDER / f"{shloka_id}.html"

        print(f"Downloading: {title}")
        print(f"From: {url}")

        html = download_page(url)

        with open(output_file, "w", encoding="utf-8") as file:
            file.write(html)

        print(f"Saved: {output_file}")
        print()

        time.sleep(1)

    print("Done.")

if __name__ == "__main__":
    main()
