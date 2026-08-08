# 🗃️ Slopcards to Anki
![Python](https://img.shields.io/badge/python-blue)
![License](https://img.shields.io/badge/license-AGPL%20v3.0-blue)
![Anki](https://img.shields.io/badge/Anki-Compatible-blue)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)

`slopcards-to-anki` gives Claude/Gemini the ability to transform your **local markdown notes** into high-retention flashcards. It automatically uploads and syncs them to your local Anki profile. Perfect for **Obsidian** users.

## 🚀Features
- **Automatic Upload & Sync**: automatically breaks down complex notes into single-fact "atmoic" cards for maximum retention
- **LaTeX Support & STEM Ready**: Full support for inline `$math$` and block `$$math$$` notation, preserved perfectly for Anki's rendering engine
- **Smart Cloze Deletion**: Identifies definitions and sequences to generate cloze card dynamically
- **Supports both skill and MCP server**

> [!IMPORTANT]
> This is a **local AI skill**. It is designed to run in environments where the AI has access to your local machine:
> - ✅ Supported: Claude Code, Gemini CLI, Aider, or **any local LLM agent with shell access**.
> - ❌ Not Supported: Standard web interfaces (claude.ai, gemini.google.com, chatgPT.com). These browser-based tools cannot communicate with your local Anki installation.


## 🛠️ Quick Start
### 1. Prerequisites
- [Anki](https://apps.ankiweb.net/) must be installed and running
- [AnkiConnect](https://ankiweb.net/shared/info/2055492159) Add on: Install code `2055492159` in anki (Tools > Add-ons > Get Add-ons)

### 2. Installation

#### As Skill (Suggested)
Instructions for Gemini
```
git clone https://github.com/moka-co/slopcards2anki.git
cd slopcard2anki
gemini skill link $PWD
```

#### As Langchain app (advanced but more accurate)
As langchain app, you need an open router key and some credits. Langchain app has an additional feature; a **critic** that verifies the quality of the generated flashcards and eventually add missing content. 

Instructions:
1. Create a file called `.env` and add in the first line: "OPENROUTER_API_KEY=xxxxx", substitute xxxxx with your key
2. Run `python -m uv run --project . -m langchain_app.main -f 'path/to/your_note.md' -d 'Test Deck'`

You can optionally specify "-q" as argument and input your query

#### As MCP
Instruction for Gemini (claude follows the same pattern):

Powershell:
```shell
git clone https://github.com/moka-co/slopcards2anki.git
cd slopcard2anki
gemini mcp add slopcards2anki "$PWD\\mcp_server\\mcp_start.bat"     
```

Linux:
```bash
git clone https://github.com/moka-co/slopcards2anki.git
cd slopcard2anki
gemini mcp add slopcards2anki "python" "-m" "uv" "run" "--project" "$PWD" "python" "-m" "mcp_server.mcp_server"  
```

### 3. Usage
Once registered, you can use **natural language** to automatically upload flashcards. 

**Example Prompts**:
- "Convert my 'Calculus_Notes.md' into 30 atomic flashcards using slopcards-to-anki"
- "Find the Anki card about "Photosynthetis" and update the back with more detail from this paragraph."

If you installed the MCP server, type `/mcp` in your CLI to see available tools.

## 🏗️ How it works
1. The AI (e.g. Claude Code / Gemini CLI) analyzes your notes, identifies high-value concepts and make flashcards
2. The the AI calls the `main.py` or `mcp_server` tools to create or update cards to your local Anki profile

## ⚠️ Scope & Roadmap
- **Text & Math Focused**: currently optimized for text and LaTeX formulas.
- **Media Support**: Audio uploads are not currently supported (help is appreciated).
- **Format**: it works better with markdown files, however as long as you're using a multimodal model e.g. Gemini 3.1 it works too with PDFs. You may want to try tools like [markitdown](https://github.com/microsoft/markitdown)


