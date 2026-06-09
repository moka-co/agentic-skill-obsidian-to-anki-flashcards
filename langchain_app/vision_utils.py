import os
import re
import base64
import os
from langchain_core.messages import HumanMessage
from langchain_openrouter import ChatOpenRouter

def intercept_and_resolve_images(source_markdown_path: str) -> dict[str, str]:
    """
    Scans a markdown file for Obsidian-style image tags ![[...]].
    Resolves their paths relative to the markdown file's location and verifies existence.
    
    Returns:
        dict: A mapping where the key is the exact raw tag string found in the text,
              and the value is the verified absolute system file path.
    """
    if not os.path.exists(source_markdown_path):
        raise FileNotFoundError(f"Source markdown file not found: {source_markdown_path}")
        
    with open(source_markdown_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Regex to capture:
    # group[0]: The entire raw tag block (e.g., '![[../../../Attachments/img.png]]')
    # group[1]: The inner path content (e.g., '../../../Attachments/img.png')
    pattern = r"(!\[\[([^\]]+)\]\])"
    matches = re.findall(pattern, content)
    
    # Identify the folder housing the markdown file to correctly anchor relative jumps
    md_dir = os.path.dirname(os.path.abspath(source_markdown_path))
    
    image_tracking_map = {}
    
    for raw_tag, relative_path in matches:
        # Strip trailing/leading spaces or accidental line breaks inside brackets
        clean_relative_path = relative_path.strip()
        
        # Build and resolve the full absolute file path on disk
        absolute_path = os.path.abspath(os.path.join(md_dir, clean_relative_path))
        
        # Track only valid files; print a notice for broken links
        if os.path.exists(absolute_path):
            image_tracking_map[raw_tag] = absolute_path
        else:
            print(f"Warning: Reference file missing on disk at: {absolute_path}")
            
    return image_tracking_map


def augment_markdown_with_descriptions(markdown_text: str, descriptions_map: dict[str, str]) -> str:
    """
    Injects the generated text descriptions directly beneath their respective 
    markdown image tags to supply visual context to the text-based extraction model.
    """
    augmented_text = markdown_text
    
    for raw_tag, description in descriptions_map.items():
        # Build a highly explicit context frame that the flashcard model can parse
        context_block = (
            f"{raw_tag}\n"
            f"[IMAGE CONTENT DESCRIPTOR: This tag contains an image file. "
            f"If you choose to create a flashcard testing the concepts shown in this diagram, "
            f"you MUST include the exact string '{raw_tag}' at the top of your card's 'front' field "
            f"so the image renders for the user. Here is what is visually inside the image:\n"
            f"{description}]\n"
        )
        # Replace the isolated tag with the tag + context framework
        augmented_text = augmented_text.replace(raw_tag, context_block)
        
    return augmented_text


def encode_image_to_base64(image_path: str) -> str:
    """Reads a local image file and converts it to a base64 encoded string."""
    with open(image_path, "rb") as image_file:
        binary_data = image_file.read()
    return base64.b64encode(binary_data).decode("utf-8")

def generate_image_descriptions(image_tracking_map: dict[str, str], vision_model: ChatOpenRouter) -> dict[str, str]:
    """
    Iterates through the verified image paths, encodes them, and utilizes 
    a multimodal vision model to create rich context summaries.
    
    Returns:
        dict: A mapping where the key is the raw markdown tag string, 
              and the value is the detailed textual description of the image contents.
    """
    descriptions_map = {}
    
    # Prompt explicitly designed to feed information to a downstream flashcard model
    vision_prompt = (
        "You are an educational vision assistant analyzing diagrams for flashcard generation. "
        "Provide a highly descriptive text summary of this image so a blind student or a purely "
        "text-based LLM can fully understand the core concept being taught.\n\n"
        "Analyze and extract the following layers clear and concisely:\n"
        "1. Core Concept: What system, architecture, framework, or workflow is shown?\n"
        "2. EDUCATIONAL VALUE: Explain what a student is expected to learn from this specific diagram.\n"
        "3. KEY RELATIONSHIPS: Detail how the components interact to achieve the goal.\n"
        "4. OCR/TEXT: List the critical terms that must be memorized.\n\n"
        "Ignore cosmetic layout details. Focus purely on technical/theoretical meaning."
    )
    
    for raw_tag, absolute_path in image_tracking_map.items():
        print(f"Analyzing visual assets for: {os.path.basename(absolute_path)}...")
        
        try:
            # Detect MIME type based on file extension
            _, ext = os.path.splitext(absolute_path.lower())
            mime_type = "image/png" if ext == ".png" else "image/jpeg"
            
            base64_image = encode_image_to_base64(absolute_path)
            
            # Construct a multimodal LangChain message structure
            message = HumanMessage(
                content=[
                    {"type": "text", "text": vision_prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{base64_image}"
                        }
                    }
                ]
            )
            
            response = vision_model.invoke([message])
            descriptions_map[raw_tag] = response.content.strip()
            
        except Exception as e:
            print(f"Failed to process image asset '{absolute_path}': {e}")
            # Fallback description so the pipeline doesn't break entirely
            descriptions_map[raw_tag] = f"[Visual Asset analysis failed for local file reference: {os.path.basename(absolute_path)}]"
            
    return descriptions_map

