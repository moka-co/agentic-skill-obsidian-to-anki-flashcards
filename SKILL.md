---
name: slopcards-to-anki
description: Manages Anki flashcards via AnkiConnect - adds flashcards from CSV files, searches existing flashcards, and updates card content. Use when working with Anki flashcards, CSV imports, spaced repetition, or when user mentions Anki, flashcards, or flashcard management.
---

#  Slopcard2Anki - Anki Flashcard Manager
This skill allows Claude/Gemini to read local files, distill them into high-quality flashcards, and sync them to Anki via a local `skill/main.py` script.

## Usage via MCP

When accessed as an MCP server, use these tools directly:

- `list_anki_decks()` — list available decks
- `create_anki_deck(name)` — create a deck
- `find_cards_by_text(query)` — search notes
- `update_anki_note(note_id, front, back)` — edit a note
- `get_anki_status()` — check if Anki is running
- `launch_anki()` — start Anki if needed

## Operational Environment
This skill operates exclusively in a **local execution context**. It requires access to the host machine's filesystem to read/write CSV files and access to `localhost:8765` to communicate with AnkiConnect. If you are being executed in a cloud-hosted web sandbox (e.g., a browser-based chat interface), notify the user that you cannot reach their local Anki instance and recommend using a local CLI-based agent instead.

**Assume Anki is already running**. Do NOT call `--try_launch_anki proactively` or as a first step. It is a last-resort fallback — only invoke it after a real connection error occurs during an actual operation [Troubleshot](#troubleshooting)


## Prerequisites
Ensure the environment has the necessary dependencies:
```shell
python -m pip install requests psutil
```

## Card Creation Principles
When generating content, adhere to these "Gold Standard" SR (Spaced Repetition) rules:
To ensure high-quality cards, follow these rules when generating content:
- **Atomicity:** One card = one specific fact. Avoid "wall-of-text" answers
- **Clarity:** **bold** key terms for visual scanning.
- Follow Data sanization rules
- **Cloze Deletion**: some cards and concepts must be cloze e.g. Front: "The derivative of an exponential is \_\_\_\_" Back: "Another derivative". You can use Anki's Cloze format: "{{c1::hidden text}}". 
    - *Example:* "{{c1::Rome}} is the capital of Italy."
- **Formula Integrity:** If a formula is present, preserve it exactly using LaTeX syntax.
    - Use $inline math$ for small variables.
    - Use $$display math$$ for standalone equations.
- **The "Principle of Two-Way" (Optional):** For key formulas, generate two cards: 
   - Card A: Name/Concept -> Formula
   - Card B: Formula -> Concept/Variable definitions.
- **Contextual Wikilinks**: If a markdown file contains [[wikilinks]], generate at least one question that references the linked concept (reading the linked file if available)
- **Images**: If the source file contains images, analyze each one and make sure to include them into flashcards. Flashcards with images are high quality flashcards. Only include images that are actually present and readable in the source file. For the correct path and syntax, follow the rules in the [Data Sanitization](#data-sanitization) section below.
- **Output:** Write the flashcards into a temporary .csv file under `.tmp/` directory e.g. `./tmp/tmp_flashcards.csv`.


## Coherence Checklist
Check every generated card against these criteria. **Any card that fails a check must be revised or dropped.**
- [ ] **Ambiguity:** For normal cards, does the front have exactly one valid answer?
- [ ] **Cloze Context:** For cloze cards, is there enough context to infer the blank without giving it away?
- [ ] **Self-containment:** Can the front be answered without referring back to the source material?
- [ ] **Redundancy:** Is any part of the answer already revealed in the question?
- [ ] **Atomicity:** Does the card test exactly one fact?
- [ ] **Formatting:** is formatting correct?

## Data Sanitization
When generating CSV files for `add_cards_from_csv`:
- **No Headers**: do **not** include "Front, Back" headers rows in the CSV
- **Escaping**: escape double quotes by doubling them ("").
- **Newlines**: replace internal newlines with <br>
- **LaTeX**: ensure LaTeX backslashes (\\) are preserved and not treated as escape characters by the CLI.
- **Images in flashcards**: include in the flashcard the path to the file enclosed with "[]" like in the markdown file. Use the absolute pat
- **Images path resolution**: always resolve image paths relative to absolute path.
- **Missing images**: if an image path cannot be resolved or the file does not exist, skip it and remove that flashcard.
- **Supported image formats**: only embed images with the following extensions: `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`. If an image has unsupported format skip it and remove the flashcard.

## CSV Format Required
The `main.py` script expects a standard CSV with a header row. Use this structure:
```csv
"What is the capital of France?", "Paris"
"{{c1::Rome}} is the capital of Italy", "and the most populated municipality of Italy"
```

- The first field is the `front` that is the question or the prompt
- The second field is the `back` that is the answer or explanation



## Core Workflows

### Workflow 1 - Generate flashcards and upload 
When a user provides a file or text and asks for "flashcards", follow these steps:
1. **Analyze:** Read the source file/text provided by the user.
2. **Extract:** extract concepts suitable for Spaced Repetition.
3. **Sanitize**: apply the [Data Sanitization](#data-sanitization) rules above.
4. **Generate CSV:** Create a temporary file (e.g., `tmp_cards.csv`) using the format defined below.
5. **Coherence Check & Fix**: check every card according to the [Coherence Checklist](#coherence-checklist). Any card failing a check MUST be revised or dropped.
6. **Execute:** Run `python -m skill.main --f tmp_cards.csv --deck_name "Target Deck"`.
7. **Clean up:** Delete the temporary CSV file after a successful run.
8. **Stop**:  report the result to the user and wait for futher instructions. Do NOT run any additional commands. 

**Constraint**: if generating <100 cards, **do not** write a Python script to build the CSV; directly output the raw CSV data to a file.

### Workflow 2 - Import
To import an **existing** CSV file:
```shell
python -m skill.main --f file_name.csv --deck_name "Deck Name"
```
*Note:* if no deck name is provided, prompt the user for one. Never assume the deck name.
After a successful import, report the result and **stop**.

## Workflow 3 - Query for cards
To find a flashcard by keyword:
```shell
python -m skill.main --find_note "search term"
```

Returns:
- CARD ID (needed for updates)
- Front text
- Back text

If multiple flashcards match, review the returned text to identify the correct flashcard.

### Workflow 4: Update Flashcards
1. **Search**: find the ID via `python -m skill.main --find_note` follow instruction from [Workflow 3](#workflow-3---search--discovery)
2. Review the return back text and improve it by adding additional context
    - You may ask the user for a file where to look for additional context
3. **Update**: 
```shell
python -m skill.main --update_note_by_id CARD_ID --new_front_text "New front" --new_back_text "New back"
```

*Note* you can also include only one of the back/front arguments e.g. to update only back: `python -m skill.main --update_note_by_id CARD_ID --new_back_text "Better back text"`

## Troubleshooting
Always notify the user of any error you encounter.

**If a command fails with a connection error (Anki not reachable)**:
1. Confirm the error is genuinely a connection failure, not a malformed command or CSV issue.
2. Only then attempt auto-launch as a fallback:
`python -m skill.main --try_launch_anki`
3. If auto-launch succeeds, retry the original command.
4. If auto-launch also fails, notify the user and ask them to start Anki manually, then retry.

**If flashcard not found**
- Try broader search terms
- Check if card exists in the correct deck
- Ask the user for what to do

**On Windows:**
If the standard `python -m skill.main` fails, ensure your environment is set up correctly for `src` to be in your PYTHONPATH, or run it from the project root.

---