"""
File manager — saving notes and persisting app configuration.

Handles:
  - Generating Obsidian YAML frontmatter
  - Writing markdown files to the chosen folder
  - Persisting and loading user preferences (last folder, etc.)
"""

import json
import os
from datetime import datetime
from pathlib import Path


# Config file path — stored next to the script
CONFIG_FILE = Path(__file__).parent.parent / 'config.json'


def generate_frontmatter(
    video_url: str = "",
    video_id: str = "",
    source_type: str = "YouTube",
    source_file: str = "",
    page_count: int = 1,
    extra_yaml: str = "",
) -> str:
    """
    Generate Obsidian YAML frontmatter for a note.

    Merges system metadata (source, url/file, date, pages) with any
    AI-generated classification metadata (topic, difficulty, skills, tags).
    """

    today = datetime.now().strftime('%Y-%m-%d')

    if source_type == "YouTube":
        system_lines = [
            "source: YouTube",
            f'youtube_url: "{video_url}"',
            f'video_id: "{video_id}"',
            f'created: "{today}"',
        ]
    else:
        system_lines = [
            f"source: {source_type}",
            f'source_file: "{source_file}"',
            f"pages_processed: {page_count}",
            f'created: "{today}"',
        ]

    if extra_yaml.strip():
        # Clean up any leading/trailing delimiters from extra_yaml
        cleaned_extra = extra_yaml.strip()
        if cleaned_extra.startswith('---'):
            cleaned_extra = cleaned_extra[3:].lstrip()
        if cleaned_extra.endswith('---'):
            cleaned_extra = cleaned_extra[:-3].rstrip()

        combined = "\n".join(system_lines) + "\n" + cleaned_extra
        return f"---\n{combined}\n---\n\n"
    else:
        tags_block = (
            "tags:\n"
            "  - handwritten-notes\n"
            "  - learning\n"
            if source_type != "YouTube"
            else "tags:\n  - youtube\n  - learning\n"
        )
        return (
            f"---\n"
            f"{chr(10).join(system_lines)}\n"
            f"{tags_block}"
            f"---\n\n"
        )


def merge_content_with_frontmatter(
    notes: str,
    video_url: str = "",
    video_id: str = "",
    source_type: str = "YouTube",
    source_file: str = "",
    page_count: int = 1,
) -> str:
    """
    Ensure the note has a single, valid YAML frontmatter block.

    If notes already begin with `---`, extracts that frontmatter,
    merges system metadata into it, and attaches the rest of the body.
    """

    stripped = notes.lstrip()
    if not stripped:
        raise ValueError("Cannot format empty note content.")

    if stripped.startswith('---'):
        parts = stripped.split('---', 2)
        if len(parts) >= 3:
            existing_yaml = parts[1].strip()
            rest = parts[2].lstrip()
            fm = generate_frontmatter(
                video_url=video_url,
                video_id=video_id,
                source_type=source_type,
                source_file=source_file,
                page_count=page_count,
                extra_yaml=existing_yaml,
            )
            return fm + rest

    # If no frontmatter exists in notes, prepend default
    return (
        generate_frontmatter(
            video_url=video_url,
            video_id=video_id,
            source_type=source_type,
            source_file=source_file,
            page_count=page_count,
        )
        + notes
    )


def save_note(
    folder: Path,
    filename: str,
    notes: str,
    video_url: str = "",
    video_id: str = "",
    source_type: str = "YouTube",
    source_file: str = "",
    page_count: int = 1,
) -> Path:
    """
    Save a note to the specified folder with unified YAML frontmatter.

    Args:
        folder: Directory to save the note in.
        filename: Filename (without .md extension).
        notes: The generated markdown notes content.
        video_url: Original YouTube URL for frontmatter (if YouTube).
        video_id: Video ID for frontmatter (if YouTube).
        source_type: Source category ("YouTube" or "Handwritten Notes").
        source_file: File name for document sources.
        page_count: Number of pages processed.

    Returns:
        Path to the created file.

    Raises:
        ValueError: If notes content is empty.
        OSError: If the file cannot be written.
    """
    if not notes or not notes.strip():
        raise ValueError("Cannot save empty notes: Note content was not generated properly.")

    # Ensure folder exists
    folder.mkdir(parents=True, exist_ok=True)

    # Sanitize notes (Mermaid syntax validation, node quoting, etc.)
    from core.notes_generator import sanitize_notes
    notes = sanitize_notes(notes)

    # Build the full content with clean, unified frontmatter
    full_content = merge_content_with_frontmatter(
        notes,
        video_url=video_url,
        video_id=video_id,
        source_type=source_type,
        source_file=source_file,
        page_count=page_count,
    )

    # Write the file
    filepath = folder / f"{filename}.md"

    # Handle duplicate filenames
    if filepath.exists():
        counter = 1
        while filepath.exists():
            filepath = folder / f"{filename} ({counter}).md"
            counter += 1

    filepath.write_text(full_content, encoding='utf-8')

    return filepath


def load_config() -> dict:
    """
    Load saved configuration from config.json.

    Returns:
        A dict with saved preferences, or empty dict
        if no config file exists.
    """

    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    return {}


def save_config(config: dict) -> None:
    """
    Save configuration to config.json.

    Args:
        config: Dictionary of preferences to save.
    """

    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
    except OSError:
        # Silently fail — not critical
        pass


def get_last_folder() -> str:
    """Get the last used folder from config, or empty string."""

    config = load_config()
    return config.get('last_folder', '')


def set_last_folder(folder: str) -> None:
    """Save the last used folder to config."""

    config = load_config()
    config['last_folder'] = folder
    save_config(config)
