import argparse
import getpass
import os
import subprocess
from dotenv import load_dotenv
from langchain_openrouter import ChatOpenRouter
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from pydantic import Secret, SecretStr
from schemas import SkillContext, SkillArguments, GenerateFlashcardsArguments, FlashcardDeck
import csv 

from prompts import get_system_prompts_content, get_base_prompt_template, get_critic_prompt_template
from vision_utils import intercept_and_resolve_images, generate_image_descriptions, augment_markdown_with_descriptions

load_dotenv()
# Get API key
api_key = os.getenv("OPENROUTER_API_KEY")
if not os.getenv("OPENROUTER_API_KEY"):
    os.environ["OPENROUTER_API_KEY"] = getpass.getpass("Enter your OpenRouter API key: ")

if not api_key:
    raise ValueError("OPENROUTER_API_KEY not found in .env")

VERIFIED_API_KEY = SecretStr(api_key)


# Initialize LangChain's ChatOpenAI configured for OpenRouter
# Hardcoded key preserved exactly from your sample snippet
orchestrator_model = ChatOpenRouter(
    model="google/gemini-3.5-flash",
    api_key=VERIFIED_API_KEY,
    temperature=0.3
)

# The distinct extraction model instance isolated specifically for processing card content
flashcard_model = ChatOpenRouter(
    model="google/gemini-3.5-flash",
    api_key=VERIFIED_API_KEY,
    temperature=0.3
)

# Dedicated critic model instance responsible for reviewing and improving the generated deck
critic_model = ChatOpenRouter(
    model="google/gemini-3.5-flash",
    api_key=VERIFIED_API_KEY,
    temperature=0.3
)

    
    
# Bind the pydantic layout to the extraction LLM
structured_flashcard_llm = flashcard_model.with_structured_output(FlashcardDeck)
prompt_template = get_base_prompt_template()
generation_chain = prompt_template | structured_flashcard_llm

# Bind the same pydantic layout to the critic LLM so it returns a revised, structured deck
structured_critic_llm = critic_model.with_structured_output(FlashcardDeck)
critic_prompt_template = get_critic_prompt_template()
critic_chain = critic_prompt_template | structured_critic_llm

def _format_cards_for_critic(cards: list) -> str:
    """Render a list of Flashcard-like objects/dicts into a readable numbered block for the critic prompt."""
    lines = []
    for i, card in enumerate(cards, start=1):
        if isinstance(card, dict):
            front_text = card.get("front", "")
            back_text = card.get("back", "")
        else:
            front_text = getattr(card, "front", "")
            back_text = getattr(card, "back", "")
        lines.append(f"{i}. FRONT: {front_text}\n   BACK: {back_text}")
    return "\n".join(lines) if lines else "(no cards were generated)"


def run_flashcard_critic(source_text: str, draft_cards: list) -> list:
    """
    Invokes the critic model, giving it the original source markdown (with any image
    descriptions already fused in) plus the draft deck, and returns the revised deck —
    fixing broken/nonsensical cards, removing redundancy, and adding cards for any
    important information the draft missed.
    """
    print("Running flashcard critic chain...")

    formatted_draft = _format_cards_for_critic(draft_cards)

    revised_deck = critic_chain.invoke({
        "text": source_text,
        "draft_cards": formatted_draft
    })

    if isinstance(revised_deck, FlashcardDeck):
        return revised_deck.cards
    elif isinstance(revised_deck, dict) and "cards" in revised_deck:
        return revised_deck["cards"]
    return draft_cards

def run_visual_flashcard_pipeline(source_markdown_path: str, vision_model, num_cards: int = 15) -> tuple[list, str]:
    """
    Orchestrates the entire multi-agent visual flashcard processing loop.
    Returns a tuple of (cards_list, processed_text) so downstream steps (like the
    critic) can reuse the same image-augmented source context.
    """
    # 1. Step 1: Intercept and resolve links
    image_map = intercept_and_resolve_images(source_markdown_path)
    
    # Read raw text
    with open(source_markdown_path, "r", encoding="utf-8") as f:
        raw_markdown = f.read()
    
    # 2. Step 2 & 3: Run vision extraction and fuse context if images exist
    if image_map:
        descriptions = generate_image_descriptions(image_map, vision_model)
        processed_text = augment_markdown_with_descriptions(raw_markdown, descriptions)
    else:
        processed_text = raw_markdown

    print("Running flashcard extraction chain...")
    
    # 4. Step 4: Invoke the extraction engine with augmented context
    extracted_deck = generation_chain.invoke({
        "text": processed_text, 
        "num_cards": num_cards
    })
    
    # Normalize structural output format for your downstream CSV writer
    if isinstance(extracted_deck, FlashcardDeck):
        cards = extracted_deck.cards
    elif isinstance(extracted_deck, dict) and "cards" in extracted_deck:
        cards = extracted_deck["cards"]
    else:
        cards = []

    return cards, processed_text


# 3. Encapsulate dynamic tool paths within a container class
class LocalSkillContainer:
    def __init__(self, context: SkillContext):
        self.context = context

    def get_tools(self):
        
        @tool("execute_local_skill", args_schema=SkillArguments)
        def execute_local_skill(script_name: str, flags: list[str] = []) -> str:
            """Executes a verified local python script or system tool defined in the Markdown documentation. Use this for running imports, status checks, updates, or queries."""
            project_root = os.getcwd()
            validated_path = None

            for directory in self.context.allowed_directories:
                candidate_path = os.path.abspath(os.path.join(directory, script_name))
                abs_allowed_dir = os.path.abspath(directory)
                
                if candidate_path.startswith(abs_allowed_dir) and os.path.exists(candidate_path):
                    validated_path = candidate_path
                    break
            
            if not validated_path:
                allowed_folders = ", ".join(self.context.allowed_directories)
                return f"Error: Script '{script_name}' was not found inside allowed directories: [{allowed_folders}]."

            command = ["python3", validated_path] + flags

            env = os.environ.copy()
            existing_pythonpath = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = f"{project_root}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else project_root
            
            try:
                result = subprocess.run(command, capture_output=True, text=True, check=True, env=env, cwd=project_root)
                return f"Execution Success!\n\nSTDOUT:\n{result.stdout}"
            except subprocess.CalledProcessError as e:
                return f"Execution Failed (Exit Code {e.returncode}).\n\nSTDERR:\n{e.stderr}"
                

        def _write_cards_csv(cards_list: list, output_csv_path: str) -> None:
            os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)

            with open(output_csv_path, "w", newline="", encoding="utf-8") as csv_file:
                writer = csv.writer(csv_file, quoting=csv.QUOTE_ALL)

                for card in cards_list:
                    if isinstance(card, dict):
                        front_text = card.get("front", "")
                        back_text = card.get("back", "")
                    else:
                        front_text = getattr(card, "front", "")
                        back_text = getattr(card, "back", "")

                    sanitized_front = front_text.replace("\n", "<br>")
                    sanitized_back = back_text.replace("\n", "<br>")
                    writer.writerow([sanitized_front, sanitized_back])

        @tool("generate_flashcards_from_markdown", args_schema=GenerateFlashcardsArguments)
        def generate_flashcards_from_markdown(source_markdown_path: str, num_cards : int = 60, output_csv_path: str = "./.tmp/tmp_flashcards.csv") -> str:
            """Use this tool when the user explicitly requests to create, extract, generate, or distill new flashcards from a markdown file text source."""
            if not os.path.exists(source_markdown_path):
                return f"Error: Source markdown file '{source_markdown_path}' not found."

            # Step 1: Run the multi-agent visual pipeline to intercept images and extract a draft deck
            draft_cards, processed_source_text = run_visual_flashcard_pipeline(
                source_markdown_path=source_markdown_path,
                vision_model=flashcard_model,
                num_cards=num_cards
            )

            if not draft_cards:
                return "No flashcards were extracted from the text."

            # Write the draft deck to disk first, so tmp_flashcards.csv reflects the pipeline's raw output
            _write_cards_csv(draft_cards, output_csv_path)

            # Step 2: Invoke the critic to read tmp_flashcards.csv (+ the source markdown for context),
            # verify quality, fix nonsensical/broken cards, and integrate any missing information
            final_cards = run_flashcard_critic(
                source_text=processed_source_text,
                draft_cards=draft_cards
            )

            if not final_cards:
                final_cards = draft_cards

            # Overwrite the CSV with the critic-reviewed, improved deck
            _write_cards_csv(final_cards, output_csv_path)

            return (
                f"Success! {len(draft_cards)} flashcards drafted, reviewed by critic, "
                f"and {len(final_cards)} finalized flashcards saved locally at: {output_csv_path}"
            )

        return [execute_local_skill, generate_flashcards_from_markdown]

def parse_args() -> argparse.Namespace:
    """
    CLI entrypoint arguments. The markdown file path is now a required
    positional/flag argument instead of being typed interactively. An
    optional free-form query can be supplied to steer the orchestrator
    (e.g. extra instructions, a target deck name, etc). If omitted, it
    defaults to an empty string and the workflow just generates flashcards
    for the given file.
    """

    parser = argparse.ArgumentParser(
        description="Generate (and upload) Anki-style flashcards from a local markdown file."
    )
    parser.add_argument(
        "-f", "--file",
        dest="file_path",
        required=True,
        help="Path to the markdown file to generate flashcards from."
    )
    parser.add_argument(
        "-d", "--deck-name",
        dest="deck_name",
        default=None,
        help="Optional name for the flashcard deck (e.g. 'Biology Chapter 4'). Defaults to none."
    )
    parser.add_argument(
        "-q", "--query",
        dest="user_query",
        default="",
        help="Optional extra instructions for the orchestrator (e.g. deck name, card count, tone). Defaults to empty."
    )
    parser.add_argument(
        "-n", "--num-cards",
        dest="num_cards",
        type=int,
        default=None,
        help="Optional target number of flashcards to generate."
    )
    return parser.parse_args()


def build_user_request(file_path: str, user_query: str, num_cards: int | None, deck_name: str | None) -> str:
    """Compose the instruction sent to the orchestrator from CLI args."""
    request = f"Generate flashcards from the markdown file located at: {file_path}."
    if num_cards:
        request += f" Target approximately {num_cards} flashcards."
    if deck_name:
        request += f" Name this deck: '{deck_name}'."
    if user_query:
        request += f" Additional instructions: {user_query}"
    return request


if __name__ == "__main__":
    args = parse_args()

    if not os.path.exists(args.file_path):
        raise FileNotFoundError(f"Markdown file not found: {args.file_path}")

    with open("./SKILL.md", "r") as f:
        md_content = f.read()
        
    runtime_deps = SkillContext(
        markdown_instructions=md_content,
        allowed_directories=["./src", "./skill"]
    )
    
    tool_container = LocalSkillContainer(runtime_deps)
    tools_list = tool_container.get_tools()
    
    # Map both tools dynamically to the execution coordinator
    model_with_tools = orchestrator_model.bind_tools(tools_list)

    # Get system prompts, see prompts.py
    system_prompt_content = get_system_prompts_content(runtime_deps)

    user_request = build_user_request(args.file_path, args.user_query, args.num_cards, args.deck_name)
    print(f"\nRequest: {user_request}\n---")
    
    messages = [
        SystemMessage(content=system_prompt_content),
        HumanMessage(content=user_request)
    ]
    
    # Loop execution allows processing dependencies sequentially
    while True:
        response = model_with_tools.invoke(messages)
        messages.append(response)
        
        if not response.tool_calls:
            print(f"Orchestrator Final Response:\n{response.content}")
            break
            
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            print(f"[Orchestrator Selection] Action: {tool_name} -> Arguments: {tool_args}")
            
            # Locate and run the active tool tool call
            target_tool = next((t for t in tools_list if t.name == tool_name), None)
            if target_tool:
                execution_output = target_tool.invoke(tool_args)
                print(f"[Execution Output]: {execution_output}\n")
                messages.append(ToolMessage(content=execution_output, tool_call_id=tool_call["id"]))
            else:
                error_msg = f"Error: Tool '{tool_name}' is not registered."
                print(error_msg)
                messages.append(ToolMessage(content=error_msg, tool_call_id=tool_call["id"]))