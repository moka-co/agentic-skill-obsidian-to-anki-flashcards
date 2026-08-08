from dataclasses import dataclass
from pydantic import BaseModel, Field

# Local environment layout definition
@dataclass
class SkillContext:
    markdown_instructions: str
    allowed_directories: list[str]

# Define strict parameters the LLM must extract to run a local script skill
class SkillArguments(BaseModel):
    script_name: str = Field(
        description="The base Python filename containing the execution logic (e.g., 'main.py'). Never use action names or flags as the script name."
    )
    flags: list[str] = Field(
        default_factory=list,
        description="The explicit switches, flags, or arguments to pass to the script (e.g., ['--f', './tmp/tmp_flashcards.csv', '--deck_name', 'Computer Science'])"
    )

# Define parameters for the dedicated flashcard extraction tool
class GenerateFlashcardsArguments(BaseModel):
    source_markdown_path: str = Field(
        description="The relative or absolute file path to the local markdown file containing the study notes that need to be distilled into flashcards."
    )
    num_cards: int = Field(
        default=60,
        description="The target number of flashcards the user wants to generate from the document text."
    )
    output_csv_path: str = Field(
        default="./tmp/tmp_flashcards.csv",
        description="The destination path where the generated headerless CSV file must be written."
    )

# Define the structured flashcard layout
class Flashcard(BaseModel):
    front: str = Field(
        description=(
            "The QUESTION or PROMPT field. Prepend the exact unaltered Obsidian image tag"
            "here if the card is based on an image descriptor block, followed by '<br>' and the question text. "
            "Never place the answer or explanation in this field."
            "Strictly follow these rules: "
            "1. Atomicity: Test exactly one specific fact. "
            "2. Clarity: Bold key terms for visual scanning. "
            "3. Cloze Deletion: Use Anki format like '{{c1::hidden text}}' when appropriate. "
            "4. Formula Integrity: Preserve LaTeX ($inline$ or $$display$$) exactly."
        )
    )
    back: str = Field(
        description=(
            "The ANSWER or EXPLANATION field. Provide ONLY the direct answer to the question asked on the front. "
           "CRITICAL: Never include any image tags (like ![[...]] or ![]), question text, or descriptor blocks in this field."
        )
    )

class FlashcardDeck(BaseModel):
    cards: list[Flashcard] = Field(description="A collection of generated flashcards.")