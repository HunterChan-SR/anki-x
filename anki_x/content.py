"""Anki-native sample creation and package import, idempotent on reconnect."""

import base64
import json
from pathlib import Path

from .bootstrap import ASSETS


def starter_deck(client):
    manifest = json.loads((ASSETS / "starter.json").read_text(encoding="utf-8"))
    name = manifest["deck"]
    deck = client.change("decks.create", name=name)
    model_name = "anki-x Vocabulary"
    models = client.col("noteTypes.list")
    model = next((item for item in models if item["name"] == model_name), None)
    if model is None:
        model = client.change("noteTypes.create", name=model_name,
                              fields=[{"name": name} for name in ("Word", "Meaning", "Example", "Translation", "Audio")],
                              templates=[{"name": "Vocabulary", "questionHtml": "{{Word}}<br>{{Audio}}",
                                          "answerHtml": "{{FrontSide}}<hr>{{Meaning}}<br>{{Example}}<br>{{Translation}}"}],
                              css=".card {font-family: sans-serif; text-align: center; font-size: 24px}")
    for index, item in enumerate(manifest["notes"]):
        tag = f"anki-x::starter-v1::{index}"
        if client.col("notes.search", query="tag:" + tag, limit=1)["ids"]:
            continue
        fields = {"Word": item["word"], "Meaning": item["meaning"], "Example": item["example"],
                  "Translation": item["translation"], "Audio": ""}
        if item.get("audio"):
            audio = ASSETS / "starter-audio" / item["audio"]
            stored = client.change("media.store", filename="anki-x-" + item["audio"],
                                   source={"data": base64.b64encode(audio.read_bytes()).decode()})
            fields["Audio"] = "[sound:" + stored["filename"] + "]"
        client.change("notes.create", noteType={"id": model["id"]}, deck={"id": deck["id"]}, fields=fields,
                      tags=["anki-x::starter", tag])
    return name


def import_package(client, filename):
    path = Path(filename).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() != ".apkg":
        raise ValueError("请选择已有的 .apkg 牌组文件。")
    return client.change("packages.import", path=str(path))
