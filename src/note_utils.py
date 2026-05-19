import re
import os
from dataclasses import dataclass, field


@dataclass
class NoteBuilder:
    """
    Builder for AnkiConnect 'add_note' payloads.

    Usage:
        note = (
            NoteBuilder()
            .deck("My Deck")
            .model("Basic")
            .field("Front", "What is the capital of France?")
            .field("Back", "Paris")
            .tag("geography")
            .allow_duplicates(False)
            .build()
        )
    """

    _deck_name: str = ""
    _model_name: str = ""
    _fields: dict = field(default_factory=dict)
    _tags: list = field(default_factory=list)
    _allow_duplicates: bool = False

    def deck(self, deck_name: str) -> "NoteBuilder":
        self._deck_name = deck_name
        return self

    def model(self, model_name: str) -> "NoteBuilder":
        self._model_name = model_name
        return self

    def tag(self, *tags: str) -> "NoteBuilder":
        self._tags.extend(tags)
        return self

    def allow_duplicates(self, allow: bool) -> "NoteBuilder":
        self._allow_duplicates = allow
        return self

    def add_field(self, name: str, value: str) -> "NoteBuilder":
        self._fields[name] = value
        return self

    def basic(self, front: str, back: str) -> "NoteBuilder":
        return self.model("Basic").add_field("Front", front).add_field("Back", back)

    def cloze(self, text: str, back_extra: str = "") -> "NoteBuilder":
        """Shorthand for a Cloze note. Text must contain {{c1::...}} markers."""
        return (
            self.model("Cloze")
            .add_field("Text", text)
            .add_field("Back Extra", back_extra)
        )

    def _validate(self):
        errors = []
        if not self._deck_name:
            errors.append("Deck name is required.")
        if not self._model_name:
            errors.append("Model name is required.")
        if not self._fields:
            errors.append("At least one field is required.")
        if self._model_name == "Cloze" and "Text" in self._fields:
            if "{{c" not in self._fields["Text"]:
                errors.append(
                    "Cloze note 'Text' field must contain at least one {{c1::...}} marker."
                )
        if errors:
            raise ValueError(
                "NoteBuilder validation failed:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )

    def build(self) -> dict:
        """Returns the raw AnkiConnect payload dict."""
        self._validate()
        return {
            "action": "addNote",
            "version": 6,
            "params": {
                "note": {
                    "deckName": self._deck_name,
                    "modelName": self._model_name,
                    "fields": self._fields,
                    "tags": self._tags,
                    "options": {
                        "allowDuplicate": self._allow_duplicates,
                    },
                }
            },
        }


@dataclass
class ImageNoteBuilder(NoteBuilder):
    """
    Extended builder that supports adding picture attachments to Anki notes.
    """

    _picture: list = field(default_factory=list)

    def add_picture(
        self, file_path: str, filename: str, fields: list | None
    ) -> "ImageNoteBuilder":
        """
        Adds a local picture attachment to the note.

        Args:
            file_path: Absolute path to the file on the local system.
            filename: The name the file will have in Anki's media folder.
            fields: A list of field names where the image should be displayed.
        """
        if not os.path.isabs(file_path):  # Enforce absolute paths
            file_path = os.path.abspath(file_path)

        self._picture.append(
            {"path": file_path, "filename": filename, "fields": fields}
        )
        return self

    def build(self) -> dict:
        """
        Builds the payload and injects the picture data into the 'note' section.
        """
        # Get the base payload from the parent class
        payload = super().build()

        # Inject picture data if any exists
        if self._picture:
            payload["params"]["note"]["picture"] = self._picture

        return payload


# Take in input a deck name (required by any NoteBuilder class)
# - the front_content and the back content of the note
# - The model name of the card i.e. cloze vs text
# Accordingly to the input parameters return in output the appropriate NoteBuilder implementation
def note_builder_factory(
    deck_name: str, front_content: str, back_content: str, model_name: str
) -> NoteBuilder | ImageNoteBuilder:
    image_path_front = get_image_path(front_content)
    image_path_back = get_image_path(back_content)

    expression = image_path_front is not None or image_path_back is not None
    if expression:
        payload_builder = ImageNoteBuilder().deck(deck_name)
    else:
        payload_builder = NoteBuilder().deck(deck_name)

    payload_image_fields = None

    # Check if it's a Cloze or Basic note
    if model_name == "Cloze":
        payload_builder = payload_builder.cloze(front_content, back_content)
        payload_image_fields = ["Text" if image_path_front else "Back Extra"]
    else:
        payload_builder = payload_builder.basic(front_content, back_content)
        payload_image_fields = ["Front" if image_path_front else "Back"]

    # Add the correct field for the correct note type
    # e.g. image_path_front for a Cloze note should be "Text"
    if isinstance(payload_builder, ImageNoteBuilder):
        if isinstance(image_path_front, str) and (
            "Text" in payload_image_fields or "Front" in payload_image_fields
        ):
            filename = os.path.basename(image_path_front)
            payload_builder.add_picture(
                image_path_front, filename, payload_image_fields
            )

            # Remove the image placeholder from the content to avoid duplication
            if "Text" in payload_image_fields:
                front_content = front_content.replace(f"[{image_path_front}]", "")
                payload_builder.add_field("Text", front_content)
            else:
                front_content = front_content.replace(f"[{image_path_front}]", "")
                payload_builder.add_field("Front", front_content)
        else:
            if isinstance(image_path_back, str):
                filename = os.path.basename(image_path_back)
                payload_builder.add_picture(
                    image_path_back, filename, payload_image_fields
                )

                # Remove the image placeholder from the content to avoid duplication
                if "Back Extra" in payload_image_fields:
                    back_content = back_content.replace(f"[{image_path_back}]", "")
                    payload_builder.add_field("Back Extra", back_content)
                else:
                    back_content = back_content.replace(f"[{image_path_back}]", "")
                    payload_builder.add_field("Back", back_content)

    return payload_builder


# These notes comes from obsidian where bold formatting is done with "**" around words"
# However, Anki wants a different format i.e. <b>word</b>
# A similar issue with Latex
def fix_formatting(text):
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text)
    result = re.sub(r"\$(.*?)\$", r"\(\1\)", text)
    return result


def get_image_path(text: str) -> str | None:
    pattern = r"\[.*?\.(?:png|jpg|jpeg|gif|webp)\]"

    match = re.search(pattern, text, re.IGNORECASE)

    if match:
        full_match = match.group(0)
        return full_match.strip("[").strip("]")

    return None


# Remove any leading/trailing whitespace first
def remove_wrapping_quotes(text):
    text = text.strip()
    if not text:
        return text
    if (text[0] == '"' or text[0] == '"'):
        text = text[1:].strip()
    if (text[-1] == '"' or text[-1] == '"'):
        text = text[:-1].strip()
    return text
