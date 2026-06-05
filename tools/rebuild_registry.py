import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATABASE_FOLDER = ROOT / "database"

GITHUB_RAW_BASE = "https://raw.githubusercontent.com/ParryBawa/bhakti-core/main/database"

SKIP_FILES = {
    "registry.json",
    "registry.backup.json",
    "registry.before_3_item_fix.json",
    "registry.before_4_item_fix.json"
}

def should_include_database_file(path):
    if path.name in SKIP_FILES:
        return False

    if path.name.startswith("registry."):
        return False

    if not path.name.endswith(".json"):
        return False

    return True

def main():
    entries = []

    database_files = sorted(DATABASE_FOLDER.glob("*.json"))

    for json_file in database_files:
        if not should_include_database_file(json_file):
            continue

        shloka_id = json_file.stem

        try:
            data = json.loads(json_file.read_text(encoding="utf-8-sig"))
        except Exception as error:
            print(f"Skipping invalid JSON: {json_file.name}")
            print(f"Reason: {error}")
            continue

        title = data.get("title", "").strip()

        if not title:
            print(f"Skipping file without title: {json_file.name}")
            continue

        entries.append({
            "id": shloka_id,
            "title": title,
            "fetchUrl": f"{GITHUB_RAW_BASE}/{json_file.name}"
        })

    registry_file = DATABASE_FOLDER / "registry.json"

    registry_file.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"Rebuilt registry.json with {len(entries)} entries.")

    for entry in entries:
        print(f"- {entry['id']} | {entry['title']}")

if __name__ == "__main__":
    main()
