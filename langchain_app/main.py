import getpass
import os
import subprocess
from dataclasses import dataclass
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_openrouter import ChatOpenRouter
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from pydantic import Secret, SecretStr
import csv 

load_dotenv()
# Get API key
api_key = os.getenv("OPENROUTER_API_KEY")
if not os.getenv("OPENROUTER_API_KEY"):
    os.environ["OPENROUTER_API_KEY"] = getpass.getpass("Enter your OpenRouter API key: ")

if not api_key:
    raise ValueError("OPENROUTER_API_KEY not found in .env")

VERIFIED_API_KEY = SecretStr(api_key)

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

# Bind the pydantic layout to the extraction LLM
structured_flashcard_llm = flashcard_model.with_structured_output(FlashcardDeck)
prompt_template = ChatPromptTemplate.from_messages([
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
        "3. To include an image in a card, place the question text first in the 'front' field," 
        "followed by '<br>' and then the unaltered file path/name of the image (e.g., '[path_to_image.png]'). A different order will break the flashcard irreversibly"
        "4. CRITICAL: Never output descriptor block text inside any card field — only the raw image tag string.\n\n"

        "CRITICAL: When generating flashcards for process diagrams or architectures:\n"
        "- ABANDOM: simple 'What are the stages?' questions\n"
        "- MANDATE: 'How-it-works' questions. Focus on the relationship between components. For example 'How does [Stage A] prepare the input for [Stage B]?'\n"
        "- ENSURE the 'back' field explains the mechanism, not just the label.\n\n"
    )),
    ("human", "Generate exactly {num_cards} distinct and high-quality flashcards from the following markdown notes:\n\n{text}")
])

generation_chain = prompt_template | structured_flashcard_llm

def run_visual_flashcard_pipeline(source_markdown_path: str, vision_model, num_cards: int = 15) -> list:
    """
    Orchestrates the entire multi-agent visual flashcard processing loop.
    """
    # 1. Step 1: Intercept and resolve links
    from vision_utils import intercept_and_resolve_images
    image_map = intercept_and_resolve_images(source_markdown_path)
    
    # Read raw text
    with open(source_markdown_path, "r", encoding="utf-8") as f:
        raw_markdown = f.read()
    
    # 2. Step 2 & 3: Run vision extraction and fuse context if images exist
    if image_map:
        from vision_utils import generate_image_descriptions, augment_markdown_with_descriptions  # Assuming step 2 function location
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
        return extracted_deck.cards
    elif isinstance(extracted_deck, dict) and "cards" in extracted_deck:
        return extracted_deck["cards"]
    return []

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
                return f"Execution Success!\n\nSTDOUT:\n{result.stderr}"
            except subprocess.CalledProcessError as e:
                return f"Execution Failed (Exit Code {e.returncode}).\n\nSTDERR:\n{e.stderr}"
                

        @tool("generate_flashcards_from_markdown", args_schema=GenerateFlashcardsArguments)
        def generate_flashcards_from_markdown(source_markdown_path: str, num_cards : int = 60, output_csv_path: str = "./.tmp/tmp_flashcards.csv") -> str:
            """Use this tool when the user explicitly requests to create, extract, generate, or distill new flashcards from a markdown file text source."""
            if not os.path.exists(source_markdown_path):
                return f"Error: Source markdown file '{source_markdown_path}' not found."

            # Run the multi-agent visual pipeline to intercept images and extract flashcards
            cards_list = run_visual_flashcard_pipeline(
                source_markdown_path=source_markdown_path,
                vision_model=flashcard_model,
                num_cards=num_cards
            )

            if not cards_list:
                return "No flashcards were extracted from the text."

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

            return f"Success! {len(cards_list)} flashcards created locally at: {output_csv_path}"

        return [execute_local_skill, generate_flashcards_from_markdown]



if __name__ == "__main__":
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

    system_prompt_content = (
        "You are a local workflow execution engine. Your job is to read the user's request, "
        "consult the provided Markdown documentation, and call the correct tools in sequence to complete the workflow.\n\n"
        "Guidelines:\n"
        "- If the user wants to generate new flashcards from a file, first call 'generate_flashcards_from_markdown' "
        "to save the CSV file. Once successful, use 'execute_local_skill' to run 'main.py' with the proper flags to upload it.\n"
        "- For queries, checks, updates, or direct file imports, execute 'execute_local_skill' directly.\n\n"
        "- Do not include conversational filler, open-ended helpful remarks, or pleasantries (such as 'How can I help you with your flashcards today?') in your response. Keep the final text concise and strictly focused on reporting the direct results of the action.\n\n"
        "- Stop when you encounter any errors in the output"
        f"Allowed Skills Documentation:\n{runtime_deps.markdown_instructions}"
    )
    
    user_query = input("Enter your command: ").strip()
    print(f"\nUser Request: {user_query}\n---")
    
    messages = [
        SystemMessage(content=system_prompt_content),
        HumanMessage(content=user_query)
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