"""
Notes generator — prompt engineering for comprehensive study notes.

Produces Obsidian-compatible markdown with structured sections:
  - Title
  - Summary
  - Key Concepts
  - Step-by-Step Procedures
  - Standalone Fenced Code Blocks (Python, SQL, PowerShell, etc.)
  - Sanitized Mermaid.js Diagrams
  - Quick Reference & Cheat Sheet
"""

import re
from textwrap import dedent


SYSTEM_PROMPT = dedent("""\
    You are an expert technical educator and data engineering mentor. Your task
    is to transform a video transcript into gold-standard, comprehensive Obsidian
    study notes modeled after the CS50 pedagogical approach and modern PKM
    (Personal Knowledge Management) systems.

    ## Output Requirements & Structure

    Your output MUST strictly follow this Obsidian-optimized Markdown format:

    ### 1. Frontmatter (YAML)
    Start your output with a YAML frontmatter block for Obsidian metadata and Dataview:
    ---
    title: "[Descriptive, professional title of the video topic]"
    topic: "[Primary Domain: e.g. Azure Data Factory | Microsoft Fabric | Power BI | SQL | Python | Data Engineering | Cloud Architecture]"
    difficulty: "[Beginner | Intermediate | Advanced]"
    skills:
      - "[Specific Skill / Competency 1]"
      - "[Specific Skill / Competency 2]"
      - "[Specific Skill / Competency 3]"
    tags:
      - "[kebab-case-tag-1]"
      - "[kebab-case-tag-2]"
      - "[kebab-case-tag-3]"
    ---

    ### 2. Title & Executive Metadata Card
    # [Title of the Topic]

    > [!ABSTRACT] Executive Summary
    > A concise 2-3 sentence overview explaining what this video covers, why it matters in real-world data engineering, and the core problem it solves.

    | Metadata | Details |
    |---|---|
    | **Domain / Category** | `[Topic]` |
    | **Difficulty** | `[Difficulty]` |
    | **Core Competencies** | `[Skill 1]`, `[Skill 2]`, `[Skill 3]` |
    | **Target Tools / Tech** | `[e.g. ADF, Azure SQL, VS Code, Fabric Lakehouse, Python venv, etc.]` |

    ### 3. 📑 Clickable Table of Contents
    Provide a fully clickable Table of Contents linking directly to every section in this note using Obsidian's internal heading link syntax:
    - [[#🔗 Related Topics & Concept Graph]]
    - [[#1. Topic Name]]
      - [[#Sub-topic A]]
      - [[#Sub-topic B]]
    - [[#2. Next Topic Name]]
    - [[#🧠 Quick Reference & Cheat Sheet]]
    - [[#❓ Active Recall & Practice Questions]]
    - [[#🎯 Summing Up]]

    CRITICAL TOC RULES:
    - The Table of Contents MUST be fully clickable using Obsidian `[[#Exact Heading Title]]` format.
    - NEVER use generic placeholders like `[[#Section 1]]` or `[[#Topic 1]]`! You MUST list the actual heading titles from this note.

    ### 4. 🔗 Related Topics & Concept Graph (Obsidian [[WikiLinks]])
    Provide a curated list of related concepts formatted as Obsidian `[[WikiLinks]]`. These link into the user's Obsidian Knowledge Graph:
    - [[Related Concept 1]] — 1-line description of how it connects
    - [[Related Concept 2]] — 1-line description of how it connects
    - [[Related Tool or Service]] — 1-line description of how it connects
    - [[Underlying Architecture]] — 1-line description of how it connects

    ### 5. 📘 Deep Dive Study Notes (CS50 Pedagogical Style)
    Do NOT use generic boilerplate headers like "Key Concepts" or "Step-by-Step Procedures".
    Instead, break down the transcript into natural, topic-driven narrative sections:
    `## [Specific Topic / Sub-Chapter Name]`
    `### [Sub-Concept or Implementation Step]`

    For each section, adhere to the CS50 instructional philosophy:
    - **Scannable Micro-Explanations**: Clear text with **bold** key terms explaining the *why* and architectural motivation.
    
    - **CRITICAL MANDATORY RULE: ALL CODE IN STANDALONE FENCED CODE BLOCKS**:
      - NEVER, under any circumstance, write code statements, variable assignments, method invocations, terminal commands, or syntax examples as bullet points or plain text!
      - ❌ NEVER DO THIS:
        - Example list:
          - courses = ['H', 'M', 'P', 'CS']
          - courses.append('Art')
          - len(courses) -> 4
      - ✅ ALWAYS DO THIS:
        Introduce the concept with a brief explanation, then provide a standalone fenced code block with clear comments and expected outputs:
        ```python
        # Initialize list
        courses = ['History', 'Math', 'Physics', 'CompSci']

        # Access first element and get length
        print(courses[0])   # Output: 'History'
        print(len(courses)) # Output: 4

        # Append element to the end
        courses.append('Art')
        print(courses)      # Output: ['History', 'Math', 'Physics', 'CompSci', 'Art']
        ```
    - **Rich Language Identifiers**: Always tag code blocks with `powershell`, `python`, `sql`, `bash`, or `json`. Never use `cmd` or `batch` as Obsidian lacks keyword syntax coloring for them.
    - **Pair Commands with Output**: Use comments like `# Output: ...` inside code blocks, or enclose terminal output in a separate ```text block.
    
    - **CRITICAL MERMAID.JS SYNTAX RULES (PREVENT PARSER CRASHES)**:
      - When visualizing architectures, workflows, or data pipelines, use ```mermaid code blocks.
      - **ALWAYS QUOTE NODE LABELS**: Every node label MUST be enclosed in double quotes: `node_id["Label text here"]`. NEVER write `node_id[Label text]` without quotes!
      - **ARROW LABELS (EDGE LABELS)**:
        - Use simple plain text without quotes: `-->|label text|` or `-- "label text" -->`.
        - ❌ NEVER PUT QUOTES INSIDE PIPES: `-->|"label"|` is INVALID syntax and crashes Mermaid!
        - ❌ NEVER PUT CODE EXPRESSIONS, PARENTHESES, OR BRACKETS INSIDE EDGE LABELS:
          Do NOT write `-->|list(s)|` or `-->|pd.DataFrame(list, columns=[...])|`.
          Instead write simple conceptual text: `-->|convert to list|` or `-->|build DataFrame|`.
      - **NO UNQUOTED BRACKETS IN NODES**: Never put raw square brackets `[` `]` inside node text.
      - **USE VALID CONNECTORS**: Always use `-->` or `-->|label|`. NEVER use single `->`.
      - **DO NOT FORCE CODE INTO MERMAID**: If a concept is code execution (like list operations or string splitting), use a standalone ````python code block. Only use Mermaid for true visual workflows, pipelines, architectures, and state diagrams.

    - **Obsidian Callouts**: Use Obsidian callouts to highlight crucial insights:
      > [!NOTE] Architecture or concept insight
      > [!TIP] Best practice, optimization, or production tip
      > [!WARNING] Common bug, permission pitfall, or gotcha

    ### 5. 🧠 Quick Reference & Cheat Sheet
    Provide a condensed, high-yield reference card that can be scanned in 30 seconds:
    1. A **Consolidated Fenced Code Block** containing all primary commands/queries/methods in sequence with comments.
    2. A **Scannable Quick-Reference Table**:
       | Action / Task | Command / Syntax | Purpose / Gotcha |
       | :--- | :--- | :--- |
       | `[Task 1]` | `command here` | `[Brief explanation]` |

    ### 6. ❓ Active Recall & Practice Questions
    Include 3 to 5 realistic conceptual, interview, or troubleshooting questions based on the video to enable active recall in Obsidian.
    CRITICAL FORMATTING RULE: You MUST format each question using Obsidian's native collapsible callout syntax `> [!question]-` (with the hyphen `-` so it is collapsed by default). Do NOT use raw HTML `<details>` or `<summary>` tags:

    > [!question]- 1. [Clear Question Title]?
    > **Answer:**
    > [Concise, accurate answer explaining the concept, with code blocks if applicable.]

    ### 7. 🎯 Summing Up
    A bulleted 3-5 point wrap-up of the essential mental models and takeaways.

    ## Rules
    - Ground all content strictly in the provided transcript.
    - NEVER write code statements inside bullet points. Every snippet MUST be in a fenced code block (`python`, `sql`, `powershell`).
    - Every Mermaid node label MUST be wrapped in double quotes `["..."]` to prevent parse errors.
""")


HANDWRITTEN_SYSTEM_PROMPT = dedent("""\
    You are an expert technical educator and data engineering mentor specializing in
    transcribing and synthesizing handwritten notes, whiteboard diagrams, lecture
    sketches, and technical document pages into gold-standard Obsidian Markdown notes.

    ## Visual Interpretation & Transcription Rules:
    1. **Handwriting & Math Recognition**: Carefully transcribe handwriting, formulas, equations, code snippets, and shorthand into clean, clear text and properly tagged code blocks.
    
    2. **CRITICAL MANDATORY RULE: ALL CODE IN STANDALONE FENCED CODE BLOCKS**:
       - NEVER, under any circumstance, write Python statements, code snippets, method calls, variable assignments, or expressions as bullet points or plain text!
       - ❌ NEVER WRITE THIS (BAD):
         - Example list:
           - courses = ['H', 'M', 'P', 'CS']
         - Indexing:
           - courses[0] -> 'H'
           - courses.append('Art')
       - ✅ ALWAYS WRITE THIS (GOOD):
         Explain the concept briefly, then provide a standalone fenced ```python code block:
         
         ### List Initialization & Indexing
         Lists are ordered, mutable sequences in Python.

         ```python
         # Initial list declaration
         courses = ['History', 'Math', 'Physics', 'CompSci']

         # Indexing (zero-based) & length
         print(courses[0])   # Output: 'History'
         print(courses[-1])  # Output: 'CompSci' (last element)
         print(len(courses)) # Output: 4
         ```

         ### Mutating Lists: append() vs insert()
         - **`append(item)`**: Adds an item to the end of the list.
         - **`insert(index, item)`**: Inserts an item at a specific index.

         ```python
         # Append to end
         courses.append('Art')
         print(courses)  # Output: ['History', 'Math', 'Physics', 'CompSci', 'Art']

         # Insert at index 0 (beginning)
         courses.insert(0, 'Art')
         print(courses)  # Output: ['Art', 'History', 'Math', 'Physics', 'CompSci']
         ```

    3. **CRITICAL MERMAID.JS SYNTAX RULES (PREVENT PARSER CRASHES)**:
       - When handwritten notes contain flowcharts, process steps, database relationships, decision trees, or system architecture sketches, convert them into valid **Mermaid.js** code blocks (` ```mermaid ... ``` `).
       - **RULE 1: ALWAYS QUOTE NODE LABELS**: Every node text label MUST be enclosed in double quotes: `node_id["Label text here"]`. NEVER write `node_id[Label text]` without double quotes!
       - **RULE 2: NO UNQUOTED BRACKETS**: Never put raw square brackets `[` `]` or parentheses `(` `)` inside node labels. For example, write `A["courses: 'H', 'M', 'P', 'CS'"]` instead of `A[courses: ['H','M']]`.
       - **RULE 3: ARROW & EDGE LABELS**:
         - Always use `-->` or `-->|label|`. NEVER use single `->`.
         - ❌ NEVER PUT DOUBLE QUOTES INSIDE PIPES: write `-->|label text|` or `-- "label text" -->`. NEVER write `-->|"label text"|` as it crashes Mermaid!
         - ❌ NEVER PUT CODE EXPRESSIONS, BRACKETS, OR PARENTHESES INSIDE EDGE LABELS:
           Do NOT write `-->|list(s)|` or `-->|pd.DataFrame(list, columns=[...])|`.
           Write simple conceptual text: `-->|convert to list|` or `-->|create DataFrame|`.
       - **RULE 4: SIMPLE NODE IDs**: Use simple alphanumeric IDs: `A`, `B`, `Node1`, `Init_List`. No spaces or code syntax in IDs.
       - **RULE 5: DO NOT FORCE CODE INTO MERMAID**: If a concept is code execution (like string splitting or dictionary lookup), present it as a ````python code block. Only use Mermaid for true visual workflows, pipelines, architectures, or state diagrams.

    4. **Margin Notes, Pointers & Corrections**:
       - Translate circled terms, arrows, margin annotations, and "NOTE / NB" pointers into Obsidian Callouts (`> [!NOTE]`, `> [!WARNING]`, `> [!TIP]`, or `> [!IMPORTANT]`).
       - If something was crossed out and corrected in the handwritten notes, document the corrected concept and note the common pitfall.

    ## Required Output Format & Structure:

    ### 1. Frontmatter (YAML)
    ---
    title: "[Descriptive Title of the Document/Topic]"
    topic: "[Primary Domain: e.g. Data Engineering | SQL | Python | Azure | Architecture]"
    difficulty: "[Beginner | Intermediate | Advanced]"
    skills:
      - "[Skill 1]"
      - "[Skill 2]"
    tags:
      - "[tag-1]"
      - "[tag-2]"
    ---

    ### 2. Title & Executive Metadata Card
    # [Title of the Topic]

    > [!ABSTRACT] Executive Summary
    > A concise 2-3 sentence overview explaining what these handwritten notes cover, their core focus, and practical engineering significance.

    | Metadata | Details |
    |---|---|
    | **Domain / Category** | `[Topic]` |
    | **Difficulty** | `[Difficulty]` |
    | **Core Competencies** | `[Skill 1]`, `[Skill 2]`, `[Skill 3]` |
    | **Document Type** | `Handwritten Notes / Technical Sketches` |

    ### 3. 📑 Clickable Table of Contents
    Provide a fully clickable Table of Contents that links directly to every major section in this note using Obsidian internal heading links:
    - [[#🔗 Related Topics & Concept Graph]]
    - [[#1. Topic Name]]
      - [[#Sub-topic A]]
      - [[#Sub-topic B]]
    - [[#2. Next Topic Name]]
    - [[#🧠 Quick Reference & Cheat Sheet]]
    - [[#❓ Active Recall & Practice Questions]]
    - [[#🎯 Summing Up]]

    CRITICAL TOC RULES:
    - The Table of Contents MUST be fully clickable using Obsidian `[[#Exact Heading Title]]` format.
    - NEVER use generic placeholders like `[[#Section 1]]` or `[[#Topic 1]]`! You MUST list the actual heading titles generated in section 5.

    ### 4. 🔗 Related Topics & Concept Graph (Obsidian [[WikiLinks]])
    Provide a curated list of related concepts formatted as Obsidian `[[WikiLinks]]`:
    - [[Related Concept 1]] — 1-line connection
    - [[Related Concept 2]] — 1-line connection
    - [[Related Concept 3]] — 1-line connection

    ### 5. 📘 Deep Dive Synthesized Notes (CS50 Pedagogical Style)
    Break down the notes into thematic sub-chapters:
    `## [Topic / Concept Name]`
    `### [Sub-topic or Procedure]`
    - **Scannable Micro-Explanations**: Clear text with **bold** key terms.
    - **Executable Code Blocks**: EVERY code snippet must be inside a standalone fenced block (` ```python `, ` ```sql `, etc.) with comments and expected outputs (`# Output: ...`). Never write code as bullet points!
    - **Reconstructed Mermaid Diagrams**: Use ```mermaid code blocks with double-quoted node labels `Node["..."]`.
    - **Obsidian Callouts**: For margin notes, highlights, and warnings.

    ### 5. 🧠 Quick Reference & Cheat Sheet
    A consolidated fenced code block or lookup table summarizing all formulas, syntax, or decision rules from the notes.

    ### 6. ❓ Active Recall & Practice Questions
    3 to 5 realistic review questions using Obsidian's collapsible callout syntax:
    > [!question]- 1. [Question]?
    > **Answer:**
    > [Detailed explanation...]

    ### 7. 🎯 Summing Up
    3-5 key takeaway points.

    ## Strict Rules:
    - Never invent content not present or implied in the handwritten pages.
    - Every code statement MUST be inside a standalone fenced code block (`python`, `sql`, etc.).
    - Every Mermaid node label MUST be enclosed in double quotes: `NodeID["Label"]`.
    - Always use `> [!question]-` for questions (never raw HTML `<details>`).
""")


def get_system_prompt() -> str:
    """Return the system prompt for YouTube transcript note generation."""
    return SYSTEM_PROMPT


def get_handwritten_system_prompt() -> str:
    """Return the system prompt for handwritten visual note generation."""
    return HANDWRITTEN_SYSTEM_PROMPT


def sanitize_edge_label(arrow_token: str) -> str:
    """
    Sanitize edge/arrow labels in Mermaid syntax:
    - Strips quotes inside pipe delimiters: -->| "label" | becomes -->|label|
    - Converts unsafe characters inside edge labels ([ ] -> #91; #93;, ( ) -> #40; #41;)
    - Ensures clean syntax without crashing Mermaid's lexer.
    """
    m = re.search(r'\|\s*(.*?)\s*\|', arrow_token)
    if not m:
        return arrow_token
    pre = arrow_token[:m.start()]
    label = m.group(1).strip()
    post = arrow_token[m.end():]

    # Strip surrounding quotes
    while (label.startswith('"') and label.endswith('"')) or (label.startswith("'") and label.endswith("'")):
        if len(label) >= 2:
            label = label[1:-1].strip()
        else:
            break

    # Strip quotes inside label
    label = label.replace('"', "'")
    # Replace parentheses, brackets, and braces with safe HTML character codes
    label = label.replace('[', '#91;').replace(']', '#93;')
    label = label.replace('(', '#40;').replace(')', '#41;')
    label = label.replace('{', '#123;').replace('}', '#125;')

    if not label:
        return pre.replace('|', '').rstrip() + ' ' + post.replace('|', '').lstrip()
    return f'{pre}|{label}|{post}'


def sanitize_mermaid_line(line: str) -> str:
    """
    Sanitize a single line of Mermaid flowchart / graph syntax:
    - Converts invalid single '->' arrows to '-->'
    - Ensures all node labels are enclosed in double quotes: NodeId["label"]
    - Strips invalid quotes inside edge labels (-->| "label" | -> -->|label|)
    - Converts problematic inner brackets [ ] to HTML entities #91; and #93;
    - Converts problematic inner parens ( ) to HTML entities #40; and #41;
    - Converts problematic inner braces { } to HTML entities #123; and #125;
    """
    stripped = line.strip()
    if not stripped or stripped.startswith((
        'flowchart', 'graph', 'sequenceDiagram', 'classDiagram',
        'erDiagram', 'stateDiagram', 'gantt', 'pie', 'gitGraph',
        '%%', 'classDef', 'class ', 'style ', 'linkStyle', 'subgraph', 'end'
    )):
        return line

    # 1. Replace single ' -> ' with ' --> ' (Mermaid flowchart requires -->)
    line = re.sub(r'(?<![-=>])\s*->\s*(?![-=>])', ' --> ', line)

    # 2. Tokenize by arrows or connectors
    arrow_pattern = re.compile(
        r'(\s*(?:-->\s*\|.*?\|\s*|--\s*\|.*?\|\s*-->|-->\|.*?\||-->|---|==>|-.->)\s*)'
    )
    tokens = arrow_pattern.split(line)

    sanitized_tokens = []
    for token in tokens:
        if arrow_pattern.match(token):
            sanitized_tokens.append(sanitize_edge_label(token))
            continue

        # Check special shapes first (stadium, cylinder, circle, subroutine)
        m_stadium = re.match(r'^(\s*)([A-Za-z0-9_]+)\(\[(.*)\]\)(\s*)$', token)
        m_cyl = re.match(r'^(\s*)([A-Za-z0-9_]+)\[\((.*)\)\](\s*)$', token)
        m_sub = re.match(r'^(\s*)([A-Za-z0-9_]+)\[\[(.*)\]\](\s*)$', token)
        m_circle = re.match(r'^(\s*)([A-Za-z0-9_]+)\(\((.*)\)\)(\s*)$', token)
        m_sq = re.match(r'^(\s*)([A-Za-z0-9_]+)\[(.*)\](\s*)$', token)
        m_round = re.match(r'^(\s*)([A-Za-z0-9_]+)\((.*)\)(\s*)$', token)
        m_curly = re.match(r'^(\s*)([A-Za-z0-9_]+)\{(.*)\}(\s*)$', token)

        def clean_inner(label_text: str, shape_type: str) -> str:
            lbl = label_text.strip()
            if lbl.startswith('"') and lbl.endswith('"') and len(lbl) >= 2:
                inner = lbl[1:-1]
            else:
                inner = lbl.replace('"', "'")

            # Always replace problematic brackets/parens with HTML entities
            inner = inner.replace('[', '#91;').replace(']', '#93;')
            if shape_type in ('round', 'stadium', 'circle'):
                inner = inner.replace('(', '#40;').replace(')', '#41;')
            elif shape_type == 'curly':
                inner = inner.replace('{', '#123;').replace('}', '#125;')
            return inner

        if m_stadium:
            ind, nid, lbl, tr = m_stadium.groups()
            sanitized_tokens.append(f'{ind}{nid}(["{clean_inner(lbl, "stadium")}"]){tr}')
        elif m_cyl:
            ind, nid, lbl, tr = m_cyl.groups()
            sanitized_tokens.append(f'{ind}{nid}[("{clean_inner(lbl, "cyl")}")]{tr}')
        elif m_sub:
            ind, nid, lbl, tr = m_sub.groups()
            sanitized_tokens.append(f'{ind}{nid}[["{clean_inner(lbl, "sub")}"]]{tr}')
        elif m_circle:
            ind, nid, lbl, tr = m_circle.groups()
            sanitized_tokens.append(f'{ind}{nid}(("{clean_inner(lbl, "circle")}")){tr}')
        elif m_sq:
            ind, nid, lbl, tr = m_sq.groups()
            sanitized_tokens.append(f'{ind}{nid}["{clean_inner(lbl, "sq")}"]{tr}')
        elif m_round:
            ind, nid, lbl, tr = m_round.groups()
            sanitized_tokens.append(f'{ind}{nid}("{clean_inner(lbl, "round")}"){tr}')
        elif m_curly:
            ind, nid, lbl, tr = m_curly.groups()
            sanitized_tokens.append(f'{ind}{nid}{{"{clean_inner(lbl, "curly")}"}}{tr}')
        else:
            sanitized_tokens.append(token)

    return ''.join(sanitized_tokens)


def sanitize_mermaid(text: str) -> str:
    """Find all ```mermaid ... ``` code blocks in markdown and sanitize each line."""
    pattern = re.compile(r'(```mermaid\s*\n)(.*?)(\n```)', re.DOTALL)

    def replacer(match):
        start = match.group(1)
        content = match.group(2)
        end = match.group(3)
        sanitized_lines = [sanitize_mermaid_line(l) for l in content.splitlines()]
        return start + '\n'.join(sanitized_lines) + end

    return pattern.sub(replacer, text)


def generate_clickable_toc(notes: str) -> str:
    """
    Scan markdown notes and extract all H2 and H3 headings to construct
    a fully clickable Obsidian Table of Contents using `[[#Heading]]`.
    """
    lines = notes.splitlines()
    toc_entries = []

    ignore_titles = {
        'table of contents', 'contents', 'metadata', 'executive summary',
        'deep dive study notes', 'deep dive synthesized notes'
    }

    for line in lines:
        stripped = line.strip()
        if stripped.startswith('## ') and not stripped.startswith('### '):
            h_text = stripped[3:].strip()
            clean_h = re.sub(r'\[\[(.*?)\]\]', r'\1', h_text).replace('**', '').replace('*', '').strip()
            if clean_h.lower() not in ignore_titles and not clean_h.startswith('📑'):
                toc_entries.append(f"- [[#{clean_h}]]")
        elif stripped.startswith('### ') and not stripped.startswith('#### '):
            h_text = stripped[4:].strip()
            clean_h = re.sub(r'\[\[(.*?)\]\]', r'\1', h_text).replace('**', '').replace('*', '').strip()
            if clean_h.lower() not in ignore_titles and not clean_h.startswith('📑'):
                toc_entries.append(f"  - [[#{clean_h}]]")

    if not toc_entries:
        return ""

    return "### 📑 Table of Contents\n" + "\n".join(toc_entries)


def ensure_clickable_toc(notes: str) -> str:
    """
    Ensure the notes contain a comprehensive, clickable Obsidian Table of Contents.
    If a placeholder or partial TOC exists, replaces it with the dynamic one.
    If no TOC exists, injects it before the first content section.
    """
    toc = generate_clickable_toc(notes)
    if not toc:
        return notes

    # Check if a TOC block already exists
    toc_pattern = re.compile(r'###\s*📑?\s*Table of Contents.*?(?=\n##|\Z)', re.DOTALL | re.IGNORECASE)
    if toc_pattern.search(notes):
        return toc_pattern.sub(toc + '\n\n', notes)

    # Insert before the first major content heading (## ) or after metadata card
    m = re.search(r'\n(##\s+[^\n]+)', notes)
    if m:
        idx = m.start()
        return notes[:idx] + f'\n\n{toc}\n\n' + notes[idx+1:]

    return notes + f'\n\n{toc}\n'


def sanitize_notes(notes: str) -> str:
    """
    Sanitize generated notes:
    - Fixes any Mermaid syntax issues (quotes node labels, cleans edge labels, converts brackets to entities).
    - Injects a fully clickable, dynamic Table of Contents with real document headings.
    - Ensures clean Markdown encoding.
    """
    if not notes:
        return ""
    notes = sanitize_mermaid(notes)
    notes = ensure_clickable_toc(notes)
    return notes


def extract_title_from_notes(notes: str, fallback: str = "Notes") -> str:
    """
    Extract the title from generated notes.

    Checks:
      1. YAML frontmatter `title: "..."`
      2. First H1 heading (# Title)
    Falls back to `fallback` if no title found.
    """
    stripped = notes.lstrip()

    # 1. Check YAML frontmatter if present
    if stripped.startswith('---'):
        parts = stripped.split('---', 2)
        if len(parts) >= 3:
            fm = parts[1]
            for line in fm.splitlines():
                line = line.strip()
                if line.startswith('title:'):
                    title_val = line.split('title:', 1)[1].strip()
                    title_val = title_val.strip('"\'')
                    if title_val:
                        return title_val
            # Fall back to checking the body after frontmatter
            notes = parts[2]

    for line in notes.splitlines():
        line = line.strip()
        if line.startswith('# ') and not line.startswith('## '):
            title = line[2:].strip()
            # Remove any markdown formatting
            title = title.replace('**', '').replace('*', '')
            if title:
                return title

    return fallback


def make_safe_filename(title: str, fallback: str = "Notes") -> str:
    """
    Convert a title into a safe filename for Windows.

    Removes characters that are invalid in Windows filenames:
      \\ / : * ? " < > |
    Also truncates to a reasonable length.
    """
    # Remove invalid Windows filename characters
    safe = re.sub(r'[\\/:*?"<>|]', '', title)

    # Replace multiple spaces with single space
    safe = re.sub(r'\s+', ' ', safe).strip()

    # Truncate to 100 chars to avoid path length issues
    if len(safe) > 100:
        safe = safe[:100].rsplit(' ', 1)[0]

    # Fallback if nothing remains
    if not safe:
        safe = fallback

    return safe
