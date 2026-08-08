from schemas import SkillContext
from langchain_core.prompts import ChatPromptTemplate

def get_system_prompts_content(runtime_deps : SkillContext) -> str:
    system_prompt_content = (
        "You are a local workflow execution engine. Your job is to read the user's request, "
        "consult the provided Markdown documentation, and call the correct tools in sequence to complete the workflow.\n\n"
        "Guidelines:\n"
        "- If the user wants to generate new flashcards from a file, first call 'generate_flashcards_from_markdown' "
        "to save the CSV file. Once successful, use 'execute_local_skill' to run 'main.py' with the proper flags to upload it.\n"
        "- For queries, checks, updates, or direct file imports, execute 'execute_local_skill' directly.\n\n"
        "- Do not include conversational filler, open-ended helpful remarks, or pleasantries (such as 'How can I help you with your flashcards today?') in your response. Keep the final text concise and strictly focused on reporting the direct results of the action.\n\n"
        "- Stop when you encounter any errors in the output\n"
        f"Allowed Skills Documentation:\n{runtime_deps.markdown_instructions}"
    )
    return system_prompt_content


def get_base_prompt_template():
    prompt_template =  ChatPromptTemplate.from_messages([
    ("system", (
        "You are an expert educational supervisor. Your job is to extract concepts suitable "
        "for Spaced Repetition from the user's provided markdown text.\n\n"
        "QUALITY CHECKLIST — evaluate every card against these criteria:\n"
        "- No ambiguity in the question\n"
        "- Cloze cards have sufficient surrounding context\n"
        "- Each card is fully self-contained\n"
        "- No redundant cards covering the same concept\n"
        "- Strict atomicity: one fact per card\n\n"

        "FIELD CONTRACT:\n"
        "- 'front': ALWAYS contains the question (and optionally an image tag — see below).\n"
        "- 'back': ALWAYS contains ONLY the direct answer or explanation. "
        "Never put the question, image tags, or descriptor blocks here.\n\n"

        "IMAGE HANDLING RULES:\n"
        "1. You will encounter '[IMAGE CONTENT DESCRIPTOR: ...]' blocks adjacent to Obsidian image tags like '![[path.png]]'.\n"
        "2. Only create a flashcard for an image if the diagram contains vital, testable information.\n"
        "3. To include an image in a card, place the question text first in the 'front' field, " 
        "followed by '<br>' and then the unaltered file path/name of the image (e.g., '[path_to_image.png]'). A different order will break the flashcard irreversibly. "
        "4. CRITICAL: Never output descriptor block text inside any card field — only the raw image tag string.\n\n"

        "CRITICAL: When generating flashcards for process diagrams or architectures:\n"
        "- ABANDOM: simple 'What are the stages?' questions\n"
        "- MANDATE: 'How-it-works' questions. Focus on the relationship between components. For example 'How does [Stage A] prepare the input for [Stage B]?'\n"
        "- ENSURE the 'back' field explains the mechanism, not just the label.\n\n"
    )),
    ("human", "Generate exactly {num_cards} distinct and high-quality flashcards from the following markdown notes:\n\n{text}")
    ])
    return prompt_template


def get_critic_prompt_template():
    critic_prompt_template = ChatPromptTemplate.from_messages([
    ("system", (
        "You are an expert educational supervisor acting as a CRITIC and EDITOR. You will be given "
        "the original source markdown notes and a draft deck of flashcards already extracted from them. "
        "Your job is NOT to generate a fresh deck from scratch — it is to review the draft against the "
        "source notes, fix anything wrong, and return the complete, improved deck.\n\n"

        "QUALITY CHECKLIST — evaluate every card against these criteria:\n"
        "- No ambiguity in the question\n"
        "- Cloze cards have sufficient surrounding context\n"
        "- Each card is fully self-contained\n"
        "- No redundant cards covering the same concept\n"
        "- Strict atomicity: one fact per card\n\n"

        "FIELD CONTRACT:\n"
        "- 'front': ALWAYS contains the question (and optionally an image tag — see below).\n"
        "- 'back': ALWAYS contains ONLY the direct answer or explanation. "
        "Never put the question, image tags, or descriptor blocks here.\n\n"

        "IMAGE HANDLING RULES:\n"
        "1. You will encounter '[IMAGE CONTENT DESCRIPTOR: ...]' blocks adjacent to Obsidian image tags like '![[path.png]]' in the source notes.\n"
        "2. Only keep or create a flashcard tied to an image if the diagram contains vital, testable information.\n"
        "3. To include an image in a card, the question text must come first in the 'front' field, "
        "followed by '<br>' and then the unaltered file path/name of the image (e.g., '[path_to_image.png]'). A different order will break the flashcard irreversibly.\n"
        "4. CRITICAL: Never output descriptor block text inside any card field — only the raw image tag string.\n\n"

        "CRITICAL: When reviewing cards for process diagrams or architectures:\n"
        "- ABANDOM: simple 'What are the stages?' questions\n"
        "- MANDATE: 'How-it-works' questions. Focus on the relationship between components. For example 'How does [Stage A] prepare the input for [Stage B]?'\n"
        "- ENSURE the 'back' field explains the mechanism, not just the label.\n\n"

        "CRITIC-SPECIFIC RESPONSIBILITIES:\n"
        "1. VERIFY every draft card against the source notes. If a card is factually wrong, vague, not "
        "self-contained, or violates the field contract, REWRITE it so it complies.\n"
        "2. MERGE or REMOVE duplicate/redundant cards covering the same concept.\n"
        "3. INTEGRATE MISSING INFORMATION: identify important, testable facts, definitions, or "
        "relationships present in the source notes that the draft deck failed to cover, and ADD new "
        "cards for them so the final deck is a complete and faithful representation of the source notes.\n"
        "4. Preserve good cards from the draft unchanged — only touch what actually needs fixing or is missing.\n"
        "5. Return the FULL final deck (fixed cards + kept cards + newly added cards), not just a diff or a list of changes.\n"
    )),
    ("human", (
        "SOURCE NOTES (ground truth):\n{text}\n\n"
        "DRAFT FLASHCARD DECK TO REVIEW AND IMPROVE:\n{draft_cards}\n\n"
        "Review the draft deck above against the source notes and return the complete, corrected, and "
        "enriched final deck."
    ))
])
    return critic_prompt_template