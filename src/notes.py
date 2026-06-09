import requests
import re
import logging
import csv
from src.note_utils import fix_formatting, remove_wrapping_quotes, note_builder_factory

ENDPOINT = "http://127.0.0.1:8765"  # AnkiConnect works only locally

logger = logging.getLogger(__name__)


# Get cards id by specifying a deck name
def get_cards_id_by_deckname(deck_name: str) -> list | None:
    payload = {
        "action": "findNotes",
        "version": 6,
        "params": {"query": f'deck:"{deck_name}"'},
    }

    try:
        response = requests.post(ENDPOINT, json=payload, timeout=(5, 30))
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to get cards id by deckaname: {e}")
        return None

    body = response.json()
    return body["result"]


# Get cards id by specifying a query
# e.e. if the query is "*" then it will return every note
# e.g. if the query is 'deck: "Test Deck"' it will return every note id from that deck
# TODO: add a query sanitizer
def get_cards_id_by_query(query: str) -> list | None:
    payload = {"action": "findNotes", "version": 6, "params": {"query": f'"{query}"'}}

    try:
        response = requests.post(ENDPOINT, json=payload, timeout=(5, 30))
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to get cards id by query: {e}")
        return None

    body = response.json()
    return body["result"]


# Get notes info i.e. content, tags etc... by specifying a list of note ids
def get_notes_info_by_id(note_ids: list) -> list | None:
    payload = {"action": "notesInfo", "version": 6, "params": {"notes": note_ids}}

    try:
        response = requests.post(ENDPOINT, json=payload, timeout=(5, 30))
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to get notes info by id: {e}")
        return None

    body = response.json()
    return body["result"]


# Add a note to an Anki Deck
# You need to specify: a deck name (that must exists), a model name (that must be allowed), a front content and back content
def add_note(deck_name, model_name, front_content, back_content):
    # print(f"Deck Name: {deck_name}\n Model Name: {model_name}\n Front Content: {front_content}\n Back Content: {back_content}")

    # add break row for clarity
    front_content = fix_formatting(front_content) + "<br>"
    # fix formatting and remove wrapping quotes
    back_content = remove_wrapping_quotes(fix_formatting(back_content))

    payload_builder = note_builder_factory(
        deck_name=deck_name,
        model_name=model_name,
        front_content=front_content,
        back_content=back_content,
    )
    payload = payload_builder.build()

    try:
        requests.post(ENDPOINT, json=payload, timeout=(5, 30))  # Make request
    except Exception as e:
        logger.error(
            f"Failed to add note (model: {model_name}) to deck {deck_name}\n Front Content: {front_content}\n Back Content: {back_content}\nError: {e}"
        )


# Read a CSV file and add each note to the specified deck
def add_notes_from_csv_file(file_name, deck_name):
    model_name = "Cloze"  # By default gemini generates flashcards with cloze
    with open(file_name, newline="") as f:
        reader = csv.reader(f)

        # Iterate over each row in the file
        for row in reader:
            front_content = row[0]
            back_content = row[1] if len(row) > 1 else ""

            # Dynamically adapt the model_name
            pattern = r"c1::*"
            if not re.search(pattern, front_content):
                model_name = "Basic"
            else:
                model_name = "Cloze"
            
            # HACK
            # Correction utility: TODO this is an hack that must be fixed
            # Correction Utility: Swap if the model inverted the image-based card
            # Logic: If front contains an image tag but looks like an answer, or back is clearly the question
            if model_name == "Basic":
                if "![[" in front_content and "?" not in front_content and "?" in back_content:
                    front_content, back_content = back_content, front_content


            # Add note
            add_note(deck_name, model_name, front_content, back_content)


# Update note by specifying an id
# Optional arguments:
# - front and back content (that also works for cloze and other notes)
# - list of tags
def update_note(
    note_id: int, front: str = "", back: str = "", tags: list = []
) -> list | None:
    # Get note info to determine the model and field names
    note_info = get_notes_info_by_id([note_id])
    if not note_info:
        logger.error(f"Could not find note info for id {note_id}")
        return None

    model_name = note_info[0].get("modelName", "Basic")

    # Construct the fields dynamically based on the model
    fields = {}
    if model_name == "Cloze":
        if front != "":
            fields["Text"] = front
        if back != "":
            fields["Back Extra"] = back
    else:
        # Default to Basic field names
        if front != "":
            fields["Front"] = front
        if back != "":
            fields["Back"] = back

    payload = {
        "action": "updateNote",
        "version": 6,
        "params": {"note": {"id": note_id, "fields": fields, "tags": tags}},
    }

    try:
        response = requests.post(ENDPOINT, json=payload, timeout=(5, 30))
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to update note with id {note_id}\n Error: {e}")
        return None

    return response.json()
