"""
CustomTkinter GUI for YouTube & Handwritten Notes → Obsidian Notes Generator.

Modern dark-themed desktop app with:
  - Dual-source mode: YouTube URLs vs Handwritten Notes / Documents (PDF, PNG, JPG)
  - Folder picker with Browse button and persistence
  - Progress bar with live status logging
  - Open Note / Open Folder buttons upon completion
  - Threaded processing for a fully responsive UI
"""

import os
import subprocess
import threading
import traceback
from pathlib import Path

import customtkinter as ctk

from core.transcript import (
    extract_video_id,
    get_transcript,
    clean_transcript,
)
from core.image_processor import (
    is_supported_document,
    get_document_info,
    load_document_images_b64,
)
from core.ai_client import AzureAIClient
from core.notes_generator import (
    get_system_prompt,
    get_handwritten_system_prompt,
    extract_title_from_notes,
    make_safe_filename,
)
from core.file_manager import (
    save_note,
    get_last_folder,
    set_last_folder,
)


# --- Theme Configuration ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__()

        # Window setup
        self.title("Obsidian Study Notes Generator")
        self.geometry("700x640")
        self.minsize(620, 560)
        self.resizable(True, True)

        # Track state
        self._result_filepath: Path | None = None
        self._processing = False
        self._selected_doc_path: Path | None = None

        # Build the UI
        self._build_ui()

    def _build_ui(self):
        """Construct all UI widgets."""

        # --- Main container with padding ---
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(
            fill="both", expand=True, padx=24, pady=20
        )

        # --- Header ---
        header_label = ctk.CTkLabel(
            self.main_frame,
            text="🧠  Obsidian Study Notes Generator",
            font=ctk.CTkFont(size=23, weight="bold"),
        )
        header_label.pack(pady=(0, 4))

        subtitle_label = ctk.CTkLabel(
            self.main_frame,
            text="Convert YouTube videos or Handwritten Notes (PDF/Images) into structured study notes",
            font=ctk.CTkFont(size=12),
            text_color="gray60",
        )
        subtitle_label.pack(pady=(0, 16))

        # --- Source Mode Selector (Segmented Button) ---
        self.mode_selector = ctk.CTkSegmentedButton(
            self.main_frame,
            values=["📺  YouTube Video", "📝  Handwritten Notes / PDF"],
            command=self._on_mode_changed,
            font=ctk.CTkFont(size=13, weight="bold"),
            height=36,
        )
        self.mode_selector.set("📺  YouTube Video")
        self.mode_selector.pack(fill="x", pady=(0, 14))

        # --- Input Container (Dynamic per mode) ---
        self.input_container = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.input_container.pack(fill="x", pady=(0, 12))

        # 1. YouTube Frame
        self.youtube_frame = ctk.CTkFrame(self.input_container, fg_color="transparent")
        url_label = ctk.CTkLabel(
            self.youtube_frame,
            text="YouTube URL",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        )
        url_label.pack(fill="x")

        self.url_entry = ctk.CTkEntry(
            self.youtube_frame,
            placeholder_text="https://www.youtube.com/watch?v=...",
            height=40,
            font=ctk.CTkFont(size=13),
        )
        self.url_entry.pack(fill="x", pady=(4, 0))

        # 2. Document / Handwritten Frame
        self.document_frame = ctk.CTkFrame(self.input_container, fg_color="transparent")
        doc_label = ctk.CTkLabel(
            self.document_frame,
            text="Select Handwritten Notes or Document (PDF, PNG, JPG)",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        )
        doc_label.pack(fill="x")

        doc_row = ctk.CTkFrame(self.document_frame, fg_color="transparent")
        doc_row.pack(fill="x", pady=(4, 4))

        self.doc_entry = ctk.CTkEntry(
            doc_row,
            placeholder_text="No document selected...",
            height=40,
            font=ctk.CTkFont(size=13),
        )
        self.doc_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        browse_doc_btn = ctk.CTkButton(
            doc_row,
            text="Browse...",
            width=100,
            height=40,
            command=self._browse_document,
        )
        browse_doc_btn.pack(side="right")

        self.doc_info_badge = ctk.CTkLabel(
            self.document_frame,
            text="Supported: .pdf (multi-page), .png, .jpg, .jpeg",
            font=ctk.CTkFont(size=11),
            text_color="gray60",
            anchor="w",
        )
        self.doc_info_badge.pack(fill="x")

        # Initially show YouTube input
        self.youtube_frame.pack(fill="x")

        # --- Folder selector ---
        folder_label = ctk.CTkLabel(
            self.main_frame,
            text="Save notes to",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        )
        folder_label.pack(fill="x")

        folder_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        folder_frame.pack(fill="x", pady=(4, 16))

        self.folder_entry = ctk.CTkEntry(
            folder_frame,
            placeholder_text="Select an Obsidian vault folder...",
            height=40,
            font=ctk.CTkFont(size=13),
        )
        self.folder_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        browse_btn = ctk.CTkButton(
            folder_frame,
            text="Browse...",
            width=100,
            height=40,
            command=self._browse_folder,
        )
        browse_btn.pack(side="right")

        # Pre-fill with last used folder
        last_folder = get_last_folder()
        if last_folder:
            self.folder_entry.insert(0, last_folder)

        # --- Create Notes button ---
        self.create_btn = ctk.CTkButton(
            self.main_frame,
            text="🚀  Create Notes",
            height=44,
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self._on_create_notes,
        )
        self.create_btn.pack(fill="x", pady=(0, 16))

        # --- Status area ---
        status_frame = ctk.CTkFrame(self.main_frame)
        status_frame.pack(fill="both", expand=True)

        self.status_label = ctk.CTkLabel(
            status_frame,
            text="Status: Ready",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        )
        self.status_label.pack(fill="x", padx=16, pady=(10, 4))

        self.progress_bar = ctk.CTkProgressBar(status_frame)
        self.progress_bar.pack(fill="x", padx=16, pady=(0, 8))
        self.progress_bar.set(0)

        self.log_textbox = ctk.CTkTextbox(
            status_frame,
            height=110,
            font=ctk.CTkFont(size=12),
            state="disabled",
            wrap="word",
        )
        self.log_textbox.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        # --- Action buttons (hidden until success) ---
        self.action_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.action_frame.pack(fill="x", pady=(6, 0))

        self.open_note_btn = ctk.CTkButton(
            self.action_frame,
            text="📄 Open Note",
            width=140,
            height=36,
            command=self._open_note,
            state="disabled",
            fg_color="gray30",
        )
        self.open_note_btn.pack(side="right", padx=(8, 0))

        self.open_folder_btn = ctk.CTkButton(
            self.action_frame,
            text="📁 Open Folder",
            width=140,
            height=36,
            command=self._open_folder,
            state="disabled",
            fg_color="gray30",
        )
        self.open_folder_btn.pack(side="right")

    # ----- Event Handlers -----

    def _on_mode_changed(self, mode: str):
        """Toggle between YouTube URL input and Document file picker."""
        if "YouTube" in mode:
            self.document_frame.pack_forget()
            self.youtube_frame.pack(fill="x")
            self._set_status("Ready for YouTube URL")
        else:
            self.youtube_frame.pack_forget()
            self.document_frame.pack(fill="x")
            self._set_status("Ready for Handwritten Notes / Document")

    def _browse_document(self):
        """Open a file picker for handwritten notes / PDF / Images."""
        file_selected = ctk.filedialog.askopenfilename(
            title="Select Handwritten Notes or Document",
            filetypes=[
                ("Supported Files", "*.pdf;*.png;*.jpg;*.jpeg"),
                ("PDF Documents", "*.pdf"),
                ("Images", "*.png;*.jpg;*.jpeg"),
                ("All Files", "*.*"),
            ],
        )

        if file_selected:
            path = Path(file_selected)
            self._selected_doc_path = path
            self.doc_entry.delete(0, "end")
            self.doc_entry.insert(0, str(path))

            try:
                info = get_document_info(path)
                size_mb = info["size_bytes"] / (1024 * 1024)
                if info["extension"] == ".pdf":
                    desc = f"📄 PDF: {info['filename']} ({info['page_count']} page(s), {size_mb:.2f} MB)"
                else:
                    desc = f"🖼️ Image: {info['filename']} ({size_mb:.2f} MB)"
                self.doc_info_badge.configure(text=desc, text_color="#79c0ff")
            except Exception as e:
                self.doc_info_badge.configure(
                    text=f"⚠️ {str(e)}", text_color="red"
                )

    def _browse_folder(self):
        """Open a folder picker dialog."""
        folder = ctk.filedialog.askdirectory(title="Select Obsidian Notes Folder")
        if folder:
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, folder)

    def _on_create_notes(self):
        """Validate inputs and launch background worker thread."""
        if self._processing:
            return

        mode = self.mode_selector.get()
        folder = self.folder_entry.get().strip()

        if not folder:
            self._set_status("⚠️ Please select an Obsidian folder.", "red")
            return

        folder_path = Path(folder)
        if not folder_path.exists():
            self._set_status("⚠️ Folder does not exist. Check the path.", "red")
            return

        # Save folder for future sessions
        set_last_folder(folder)

        if "YouTube" in mode:
            url = self.url_entry.get().strip()
            if not url:
                self._set_status("⚠️ Please enter a YouTube URL.", "red")
                return

            self._start_processing()
            threading.Thread(
                target=self._process_video,
                args=(url, folder_path),
                daemon=True,
            ).start()
        else:
            file_str = self.doc_entry.get().strip()
            if not file_str or not Path(file_str).exists():
                self._set_status("⚠️ Please browse and select a valid document.", "red")
                return

            doc_path = Path(file_str)
            if not is_supported_document(doc_path):
                self._set_status("⚠️ Unsupported format. Use .pdf, .png, or .jpg.", "red")
                return

            self._start_processing()
            threading.Thread(
                target=self._process_document,
                args=(doc_path, folder_path),
                daemon=True,
            ).start()

    def _start_processing(self):
        """Reset UI state before processing begins."""
        self._processing = True
        self.create_btn.configure(state="disabled", text="Processing...")
        self.open_note_btn.configure(state="disabled", fg_color="gray30")
        self.open_folder_btn.configure(state="disabled", fg_color="gray30")
        self._result_filepath = None
        self._clear_log()
        self.progress_bar.set(0)

    # ----- Processing Pipelines -----

    def _process_video(self, url: str, folder: Path):
        """YouTube processing pipeline."""
        try:
            self._update_progress(0.1, "Extracting video ID...")
            video_id = extract_video_id(url)
            self._log(f"✓ Video ID: {video_id}")

            self._update_progress(0.2, "Fetching transcript...")
            transcript = get_transcript(video_id)
            self._log(f"✓ Transcript fetched ({len(transcript):,} characters)")

            self._update_progress(0.3, "Cleaning transcript...")
            transcript = clean_transcript(transcript)
            self._log(f"✓ Transcript cleaned ({len(transcript):,} characters)")

            self._update_progress(0.4, "Generating notes via Azure OpenAI...")
            client = AzureAIClient()
            system_prompt = get_system_prompt()

            def ai_progress(msg):
                self._log(f"  → {msg}")

            notes = client.generate_notes(
                transcript, system_prompt, progress_callback=ai_progress
            )
            if not notes or not notes.strip():
                raise RuntimeError("Failed to generate notes: AI model returned an empty response.")
            self._log("✓ Notes generated successfully")

            self._update_progress(0.85, "Saving note...")
            title = extract_title_from_notes(notes, fallback="YouTube Notes")
            filename = make_safe_filename(title, fallback="YouTube Notes")
            self._log(f"✓ Title: {title}")

            filepath = save_note(
                folder=folder,
                filename=filename,
                notes=notes,
                video_url=url,
                video_id=video_id,
                source_type="YouTube",
            )
            self._result_filepath = filepath
            self._log(f"✓ Saved to: {filepath}")

            self._update_progress(1.0, "✅ Notes created successfully!")
            self._finish_success()

        except Exception as e:
            error_msg = str(e)
            self._log(f"\n❌ Error: {error_msg}")
            self._update_progress(0, f"❌ Failed: {error_msg[:80]}")
            self._finish_error()

    def _process_document(self, file_path: Path, folder: Path):
        """Handwritten notes and document vision processing pipeline."""
        try:
            self._update_progress(0.1, "Inspecting document...")
            doc_info = get_document_info(file_path)
            size_kb = doc_info["size_bytes"] / 1024
            self._log(
                f"✓ Document: {doc_info['filename']} "
                f"({doc_info['page_count']} page(s), {size_kb:.1f} KB)"
            )

            self._update_progress(0.25, "Rendering pages for vision analysis...")
            images_b64 = load_document_images_b64(file_path)
            self._log(f"✓ Rendered {len(images_b64)} page(s) at high resolution")

            client = AzureAIClient()
            self._update_progress(0.4, f"Synthesizing with Azure OpenAI Vision ({client.vision_deployment})...")
            system_prompt = get_handwritten_system_prompt()

            def vision_progress(msg):
                self._log(f"  → {msg}")

            notes = client.generate_notes_from_images(
                images_b64, system_prompt, progress_callback=vision_progress
            )
            if not notes or not notes.strip():
                raise RuntimeError("Failed to generate notes: AI model returned an empty response.")
            self._log("✓ Notes and Mermaid diagrams synthesized successfully")

            self._update_progress(0.85, "Saving note...")
            fallback_title = file_path.stem.replace("_", " ").replace("-", " ").title()
            title = extract_title_from_notes(notes, fallback=fallback_title)
            filename = make_safe_filename(title, fallback=fallback_title)
            self._log(f"✓ Title: {title}")

            filepath = save_note(
                folder=folder,
                filename=filename,
                notes=notes,
                source_type="Handwritten Notes",
                source_file=file_path.name,
                page_count=doc_info["page_count"],
            )
            self._result_filepath = filepath
            self._log(f"✓ Saved to: {filepath}")

            self._update_progress(1.0, "✅ Notes created successfully!")
            self._finish_success()

        except Exception as e:
            error_msg = str(e)
            self._log(f"\n❌ Error: {error_msg}")
            self._update_progress(0, f"❌ Failed: {error_msg[:80]}")
            self._finish_error()

    # ----- UI Update Helpers (thread-safe) -----

    def _update_progress(self, value: float, status: str):
        """Update progress bar and status label from any thread."""
        self.after(0, lambda: self.progress_bar.set(value))
        self._set_status(status)

    def _set_status(self, text: str, color: str = None):
        """Update status label text."""
        def _update():
            self.status_label.configure(text=f"Status: {text}")
            if color:
                self.status_label.configure(text_color=color)
            else:
                self.status_label.configure(text_color="white")
        self.after(0, _update)

    def _log(self, message: str):
        """Append a message to the log textbox."""
        def _append():
            self.log_textbox.configure(state="normal")
            self.log_textbox.insert("end", message + "\n")
            self.log_textbox.see("end")
            self.log_textbox.configure(state="disabled")
        self.after(0, _append)

    def _clear_log(self):
        """Clear the log textbox."""
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", "end")
        self.log_textbox.configure(state="disabled")

    def _finish_success(self):
        """Enable action buttons after successful processing."""
        def _enable():
            self._processing = False
            self.create_btn.configure(state="normal", text="🚀  Create Notes")
            self.open_note_btn.configure(
                state="normal", fg_color=["#3B8ED0", "#1F6AA5"]
            )
            self.open_folder_btn.configure(
                state="normal", fg_color=["#3B8ED0", "#1F6AA5"]
            )
        self.after(0, _enable)

    def _finish_error(self):
        """Reset button state after an error."""
        def _reset():
            self._processing = False
            self.create_btn.configure(state="normal", text="🚀  Create Notes")
        self.after(0, _reset)

    def _open_note(self):
        """Open the generated note file in the default app."""
        if self._result_filepath and self._result_filepath.exists():
            os.startfile(str(self._result_filepath))

    def _open_folder(self):
        """Open the folder containing the note in Explorer."""
        if self._result_filepath and self._result_filepath.exists():
            subprocess.Popen(
                ['explorer', '/select,', str(self._result_filepath)]
            )
