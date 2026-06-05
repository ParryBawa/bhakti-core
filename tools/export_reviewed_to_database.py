import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REVIEWED_FOLDER = ROOT / "source_data" / "reviewed" / "shlokam_org"
DATABASE_FOLDER = ROOT / "database"
AUDIO_FOLDER = ROOT / "audio"

GITHUB_RAW_BASE = "https://raw.githubusercontent.com/ParryBawa/bhakti-core/main"

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

def main():
    DATABASE_FOLDER.mkdir(parents=True, exist_ok=True)

    reviewed_files = sorted(REVIEWED_FOLDER.glob("*.reviewed.json"))

    if not reviewed_files:
        print("No reviewed files found.")
        return

    for reviewed_file in reviewed_files:
        print(f"Exporting: {reviewed_file.name}")

        reviewed_data = json.loads(reviewed_file.read_text(encoding="utf-8-sig"))
        shloka_id = reviewed_data["id"]

        app_ready_data = make_app_ready_data(reviewed_data)

        output_file = DATABASE_FOLDER / f"{shloka_id}.json"
        output_file.write_text(
            json.dumps(app_ready_data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        print(f"Created: {output_file}")

    print("Done.")

if __name__ == "__main__":
    main()
