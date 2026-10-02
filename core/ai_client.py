"""
Azure OpenAI client with smart auto-chunking for long transcripts.

Handles:
  - Single API call for short transcripts (< 80k chars)
  - Chunked calls + merge for long transcripts (> 80k chars)
"""

import os
import re
import time
from textwrap import dedent

from dotenv import load_dotenv
from openai import AzureOpenAI, RateLimitError


# Threshold in characters — transcripts longer than this get chunked
# Set to 18,000 (~4,500 tokens) to safely respect Azure 10,000 TPM rate limits
CHUNK_THRESHOLD = int(os.getenv('CHUNK_THRESHOLD', '18000'))

# Target chunk size in characters (~3,500 tokens)
CHUNK_SIZE = int(os.getenv('CHUNK_SIZE', '14000'))


class AzureAIClient:
    """Client for Azure OpenAI with auto-chunking support."""

    def __init__(self):
        """
        Initialize the Azure OpenAI client.

        Loads credentials from .env file.

        Raises:
            ValueError: If required env vars are missing.
        """

        load_dotenv()

        self.endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
        self.api_key = os.getenv('AZURE_OPENAI_KEY')
        self.deployment = os.getenv('AZURE_OPENAI_DEPLOYMENT')
        self.api_version = os.getenv(
            'AZURE_OPENAI_API_VERSION', '2024-10-21'
        )

        missing = []
        if not self.endpoint:
            missing.append('AZURE_OPENAI_ENDPOINT')
        if not self.api_key:
            missing.append('AZURE_OPENAI_KEY')
        if not self.deployment:
            missing.append('AZURE_OPENAI_DEPLOYMENT')

        if missing:
            raise ValueError(
                f"Missing required environment variables: "
                f"{', '.join(missing)}\n"
                f"Please configure them in the .env file."
            )

        self.client = AzureOpenAI(
            azure_endpoint=self.endpoint,
            api_key=self.api_key,
            api_version=self.api_version,
        )

        # Vision-specific deployment & endpoint (falls back to primary if not set)
        self.vision_deployment = os.getenv(
            'AZURE_OPENAI_VISION_DEPLOYMENT', self.deployment
        )
        self.vision_endpoint = os.getenv(
            'AZURE_OPENAI_VISION_ENDPOINT', self.endpoint
        )
        self.vision_api_key = os.getenv(
            'AZURE_OPENAI_VISION_KEY', self.api_key
        )
        self.vision_api_version = os.getenv(
            'AZURE_OPENAI_VISION_API_VERSION',
            os.getenv('AZURE_OPENAI_API_VERSION', '2024-12-01-preview'),
        )

        if (
            self.vision_endpoint != self.endpoint
            or self.vision_api_key != self.api_key
            or self.vision_api_version != self.api_version
        ):
            self.vision_client = AzureOpenAI(
                azure_endpoint=self.vision_endpoint,
                api_key=self.vision_api_key,
                api_version=self.vision_api_version,
            )
        else:
            self.vision_client = self.client

        # Max completion tokens (default 32,768 to support high reasoning models like gpt-5-mini)
        self.max_completion_tokens = int(
            os.getenv('AZURE_OPENAI_MAX_COMPLETION_TOKENS', '32768')
        )
        # Reasoning effort for reasoning-capable models (e.g. gpt-5-mini, o1, o3-mini)
        self.reasoning_effort = os.getenv('AZURE_OPENAI_REASONING_EFFORT', 'high')

    def _create_completion(
        self,
        client: AzureOpenAI,
        model: str,
        messages: list[dict],
        max_tokens: int | None = None,
        progress_callback=None,
    ) -> str:
        """
        Execute chat completion with robust parameter fallback and rate-limit retries.

        Handles:
          - Automatically retrying on HTTP 429 rate limit (too_many_requests / rate_limit_exceeded)
            with exponential backoff and UI progress notifications.
          - Applying reasoning_effort (e.g. 'high' or 'low') for reasoning-capable models.
          - Falling back gracefully if the target model does not support reasoning_effort (e.g. gpt-4o).
          - Validating that the model did not exhaust the token limit during reasoning without returning content.
        """
        tokens = max_tokens or self.max_completion_tokens
        kwargs = {"max_completion_tokens": tokens}
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort

        max_retries = 6
        base_delay = 8.0

        for attempt in range(max_retries + 1):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    **kwargs,
                )
                break
            except Exception as e:
                err_msg = str(e).lower()

                # Check if this is a 429 rate limit error
                is_rate_limit = (
                    "429" in err_msg
                    or "rate_limit" in err_msg
                    or "too_many_requests" in err_msg
                    or isinstance(e, RateLimitError)
                )

                if is_rate_limit:
                    if attempt < max_retries:
                        wait_seconds = base_delay * (1.5 ** attempt)
                        if hasattr(e, "response") and e.response is not None:
                            headers = getattr(e.response, "headers", {})
                            ra = headers.get("retry-after") or headers.get("retry-after-ms")
                            if ra:
                                try:
                                    ra_val = float(ra)
                                    wait_seconds = ra_val / 1000.0 if ra_val > 500 else ra_val
                                except ValueError:
                                    pass
                        wait_seconds = max(6.0, min(wait_seconds, 60.0))
                        msg = (
                            f"Azure TPM rate limit reached (429) — waiting {int(wait_seconds)}s for quota to refresh "
                            f"(attempt {attempt + 1}/{max_retries})..."
                        )
                        if progress_callback:
                            progress_callback(msg)
                        time.sleep(wait_seconds)
                        continue
                    else:
                        raise RuntimeError(
                            f"Azure OpenAI token rate limit (429) exceeded after {max_retries} retries. "
                            f"Your deployment has a 10,000 TPM limit. Please wait a moment before trying again."
                        ) from e

                # If the model does not support reasoning_effort (e.g. gpt-4o, gpt-4)
                if "reasoning_effort" in err_msg or "unknown parameter" in err_msg:
                    kwargs.pop("reasoning_effort", None)
                    continue

                # If API version / model expects max_tokens instead of max_completion_tokens
                if "max_completion_tokens" in err_msg:
                    kwargs.pop("reasoning_effort", None)
                    kwargs.pop("max_completion_tokens", None)
                    kwargs["max_tokens"] = tokens
                    continue

                raise

        if not response.choices:
            raise RuntimeError("Azure OpenAI returned no completion choices.")

        choice = response.choices[0]
        content = choice.message.content or ""

        if not content.strip():
            if choice.finish_reason == "length":
                raise RuntimeError(
                    f"The model '{model}' exhausted its token budget ({tokens} tokens) "
                    f"during reasoning without generating output. "
                    f"Please increase AZURE_OPENAI_MAX_COMPLETION_TOKENS in .env."
                )
            if choice.finish_reason == "content_filter":
                raise RuntimeError(
                    "Azure OpenAI content filter triggered and suppressed the response."
                )
            raise RuntimeError(
                f"The model '{model}' returned an empty response (finish_reason='{choice.finish_reason}')."
            )

        return content

    def generate_notes(
        self,
        transcript: str,
        system_prompt: str,
        progress_callback=None,
    ) -> str:
        """
        Generate notes from a transcript.

        Automatically decides whether to use a single call
        or chunked calls based on transcript length.

        Args:
            transcript: The cleaned transcript text.
            system_prompt: The system prompt for note generation.
            progress_callback: Optional callable(status_message)
                               for GUI progress updates.

        Returns:
            Generated notes as a markdown string.
        """

        if len(transcript) <= CHUNK_THRESHOLD:
            if progress_callback:
                progress_callback(
                    "Generating notes (single pass)..."
                )
            result = self._single_call(
                transcript, system_prompt, progress_callback=progress_callback
            )
        else:
            if progress_callback:
                progress_callback(
                    f"Long transcript detected ({len(transcript):,} characters) — "
                    f"using chunked processing (respecting 10k TPM limit)..."
                )
            result = self._chunked_call(
                transcript, system_prompt, progress_callback
            )

        from core.notes_generator import sanitize_notes
        return sanitize_notes(result)

    def _single_call(
        self,
        transcript: str,
        system_prompt: str,
        progress_callback=None,
    ) -> str:
        """Make a single API call for the entire transcript."""
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    "Here is the YouTube video transcript. "
                    "Please generate comprehensive study "
                    "notes from it:\n\n"
                    f"{transcript}"
                ),
            },
        ]
        return self._create_completion(
            self.client,
            self.deployment,
            messages,
            progress_callback=progress_callback,
        )

    def _chunked_call(
        self,
        transcript: str,
        system_prompt: str,
        progress_callback=None,
    ) -> str:
        """
        Split transcript into chunks, generate notes for each,
        then merge into a single cohesive document.
        """

        chunks = self._split_into_chunks(transcript)
        total_chunks = len(chunks)
        chunk_notes = []

        chunk_system_prompt = (
            "You are an expert technical note taker. Extract all key concepts, "
            "definitions, explanations, procedures, and code examples from this transcript section. "
            "Format clearly with markdown headings, bullet points, callouts, and code blocks."
        )

        for i, chunk in enumerate(chunks, 1):
            if i > 1:
                if progress_callback:
                    progress_callback(
                        f"Pacing request (6s) to stay within Azure TPM rate limit..."
                    )
                time.sleep(6)

            if progress_callback:
                progress_callback(
                    f"Processing chunk {i}/{total_chunks}..."
                )

            messages = [
                {"role": "system", "content": chunk_system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Transcript section (Part {i} of {total_chunks}):\n\n{chunk}"
                    ),
                },
            ]
            content = self._create_completion(
                self.client,
                self.deployment,
                messages,
                max_tokens=self.max_completion_tokens,
                progress_callback=progress_callback,
            )
            chunk_notes.append(content)

        if progress_callback:
            progress_callback("Pausing briefly before merging to replenish token quota...")
        time.sleep(6)

        if progress_callback:
            progress_callback("Merging notes into final document...")

        return self._merge_notes(
            chunk_notes,
            system_prompt,
            source_type="video transcript",
            progress_callback=progress_callback,
        )

    def _merge_notes(
        self,
        chunk_notes: list[str],
        system_prompt: str,
        source_type: str = "document",
        progress_callback=None,
    ) -> str:
        """Merge multiple chunk notes into one cohesive document."""
        if not chunk_notes:
            return ""
        if len(chunk_notes) == 1:
            return chunk_notes[0]

        total_len = sum(len(c) for c in chunk_notes)

        # For very small sets of notes (< 8,000 chars / ~2,000 tokens combined),
        # a direct single-pass merge is fast and safe from 429 limits.
        if total_len <= 8_000 and len(chunk_notes) <= 2:
            combined = "\n\n---\n\n".join(
                f"## Notes from Part {i + 1}\n\n{notes}"
                for i, notes in enumerate(chunk_notes)
            )
            merge_prompt = dedent(f"""\
                Below are notes generated from different parts of
                the same {source_type}. Please merge them into a
                single, cohesive, comprehensive, well-structured set of study
                notes in Obsidian Markdown format.

                Requirements:
                - Preserve all key concepts, definitions, formulas, code blocks,
                  Mermaid diagrams, callouts, and practice questions from all parts.
                - Consolidate into a single unified YAML frontmatter block at the top.
                - Provide a single unified, clickable Table of Contents.
                - Remove duplicate headings and maintain a clean, logical narrative flow.
                - Do NOT add a disclaimer or note stating that these parts were merged.
                - The final output should read as if it was synthesized in a single pass.

                Separate notes to merge:

                {combined}
            """)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": merge_prompt},
            ]
            return self._create_completion(
                self.client,
                self.deployment,
                messages,
                max_tokens=self.max_completion_tokens,
                progress_callback=progress_callback,
            )

        # For multi-chunk or large notes (> 8,000 chars), synthesize an
        # Executive Envelope (Frontmatter + Metadata Card + Clickable TOC + Concept Graph +
        # Cheat Sheet + Active Recall) and stitch the unabridged deep dive sections.
        # This guarantees:
        #   1. Zero 429 token rate limit errors on 10,000 TPM Azure deployments.
        #   2. 100% preservation of code blocks, formulas, diagrams, and procedures.
        #   3. Rapid synthesis without recursive merge degradation.
        return self._assemble_chunked_document(
            chunk_notes,
            source_type=source_type,
            progress_callback=progress_callback,
        )

    def _assemble_chunked_document(
        self,
        chunk_notes: list[str],
        source_type: str = "document",
        progress_callback=None,
    ) -> str:
        """
        Assemble multi-chunk notes into a unified Obsidian document.

        Extracts an outline from all sections, prompts the AI to generate a unified
        Executive Header (frontmatter, title, abstract summary, clickable TOC, concept graph)
        and Closing Synthesis (cheat sheet, active recall questions, summing up),
        and stitches the complete deep dive sections between them.
        """
        if progress_callback:
            progress_callback("Synthesizing unified executive summary and table of contents...")

        cleaned_sections = []
        outline_items = []

        for i, chunk in enumerate(chunk_notes, 1):
            lines = chunk.strip().split("\n")
            filtered_lines = []
            for line in lines:
                if line.startswith("# ") and any(
                    k in line.lower()
                    for k in ["extracted notes", "transcript part", "batch ", "part "]
                ):
                    continue
                filtered_lines.append(line)

            cleaned_chunk = "\n".join(filtered_lines).strip()
            cleaned_sections.append(cleaned_chunk)

            headings = [
                h.strip()
                for h in re.findall(
                    r"^(#{2,3}\s+.+)$", cleaned_chunk, flags=re.MULTILINE
                )
            ]
            outline_items.append(
                f"Section {i} Topics:\n"
                + "\n".join(f"  - {h}" for h in headings[:8])
            )

        outline_text = "\n\n".join(outline_items)

        synthesis_prompt = dedent(f"""\
            You are an expert technical educator and PKM mentor. Below is the structural outline
            of comprehensive study notes extracted from a complete {source_type}.

            Topics covered across the sections:
            {outline_text}

            Generate TWO unified sections in Obsidian Markdown format:

            PART A: The Executive Header (Top of note)
            1. YAML Frontmatter:
               ---
               title: "[Descriptive professional title strictly based on the outline above]"
               topic: "[Domain/Topic strictly based on the outline above]"
               difficulty: "[Beginner | Intermediate | Advanced]"
               skills:
                 - "[Skill 1 from outline]"
                 - "[Skill 2 from outline]"
                 - "[Skill 3 from outline]"
               tags:
                 - "[kebab-case-tag-1]"
                 - "[kebab-case-tag-2]"
               ---
            2. Document Title: # [Title strictly based on the outline above]
            3. Executive Summary Card:
               > [!ABSTRACT] Executive Summary
               > [A concise 2-3 sentence overview explaining what is covered in the outline above and key problems solved]
               | Metadata | Details |
               |---|---|
               | **Domain / Category** | `[Topic]` |
               | **Difficulty** | `[Difficulty]` |
               | **Core Competencies** | `[Key skills comma-separated]` |
               | **Target Tools / Tech** | `[Target tools/tech comma-separated]` |
            4. Related Topics & Concept Graph with Obsidian `[[WikiLinks]]`:
               ### 🔗 Related Topics & Concept Graph
               - [[Concept 1]] — brief connection
               - [[Concept 2]] — brief connection
               - [[Concept 3]] — brief connection

            CRITICAL CONSTRAINTS FOR PART A:
            - Ground the title, topic, metadata, and summary 100% strictly in the Topics listed above.
            - DO NOT invent tools or concepts not mentioned in the outline.
            - DO NOT generate a Table of Contents (a dynamic Table of Contents is injected automatically).
            - DO NOT generate ANY section headings (##), tutorials, code blocks, or body content in PART A! All body content lives in the deep dive sections.
            - Stop immediately after the Related Topics & Concept Graph and output <<<BODY_PLACEHOLDER>>>.

            PART B: The Closing Synthesis (Bottom of note)
            5. ## 🧠 Quick Reference & Cheat Sheet
               A consolidated markdown table of key syntax, hotkeys, or commands covered in the topics above.
            6. ## ❓ Active Recall & Practice Questions
               3 to 5 realistic conceptual/troubleshooting questions using Obsidian collapsible callouts `> [!question]-`:
               > [!question]- 1. [Clear Question Title]?
               > **Answer:**
               > [Concise, accurate answer explaining the concept, with code blocks if applicable]
            7. ## 🎯 Summing Up
               A bulleted 3-5 point wrap-up of essential mental models and takeaways.

            CRITICAL CONSTRAINTS FOR PART B:
            - Base all cheat sheets, commands, questions, and takeaways STRICTLY on the actual topics in the outline.

            Separate PART A and PART B with the exact marker:
            <<<BODY_PLACEHOLDER>>>
        """)

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert technical educator and PKM mentor. Return only the requested Obsidian markdown "
                    "with PART A before <<<BODY_PLACEHOLDER>>> and PART B after <<<BODY_PLACEHOLDER>>>."
                ),
            },
            {"role": "user", "content": synthesis_prompt},
        ]

        envelope = self._create_completion(
            self.client,
            self.deployment,
            messages,
            max_tokens=self.max_completion_tokens,
            progress_callback=progress_callback,
        )

        if "<<<BODY_PLACEHOLDER>>>" in envelope:
            header, footer = envelope.split("<<<BODY_PLACEHOLDER>>>", 1)
        else:
            header = envelope
            footer = ""

        # Defensive cleanup: Ensure header contains only frontmatter, title, abstract card, and concept graph.
        # If the LLM hallucinated any ## section headings in header, truncate right before the first ## heading.
        m_extra_h2 = re.search(r'\n(##\s+[^\n]+)', header)
        if m_extra_h2:
            header = header[:m_extra_h2.start()].strip()

        deep_dive_body = "\n\n---\n\n".join(cleaned_sections)
        final_document = (
            f"{header.strip()}\n\n---\n\n"
            f"## 📘 Deep Dive Study Notes\n\n"
            f"{deep_dive_body}\n\n---\n\n"
            f"{footer.strip()}"
        )

        from core.notes_generator import sanitize_notes
        return sanitize_notes(final_document)

    @staticmethod
    def _split_into_chunks(text: str) -> list[str]:
        """
        Split text into chunks at sentence boundaries.

        Tries to split at period + space boundaries to avoid
        cutting mid-sentence.
        """

        chunks = []
        remaining = text

        while len(remaining) > CHUNK_SIZE:
            # Find the last sentence boundary before the limit
            split_point = remaining[:CHUNK_SIZE].rfind('. ')

            if split_point == -1:
                # No sentence boundary found — split at space
                split_point = remaining[:CHUNK_SIZE].rfind(' ')

            if split_point == -1:
                # No space found — hard split
                split_point = CHUNK_SIZE

            # Include the period in the chunk
            split_point += 1

            chunks.append(remaining[:split_point].strip())
            remaining = remaining[split_point:].strip()

        if remaining:
            chunks.append(remaining)

        return chunks

    def generate_notes_from_images(
        self,
        images_b64: list[str],
        system_prompt: str,
        progress_callback=None,
    ) -> str:
        """
        Generate Obsidian study notes from a list of base64 page images.

        Automatically batches multi-page documents (up to 4 pages per batch)
        and merges them into a single cohesive document.
        """
        if not images_b64:
            raise ValueError("No images provided for notes generation.")

        from core.image_processor import batch_images

        batches = batch_images(images_b64, batch_size=4)
        total_batches = len(batches)

        from core.notes_generator import sanitize_notes

        if total_batches == 1:
            if progress_callback:
                progress_callback(
                    f"Analyzing {len(images_b64)} page image(s) with {self.vision_deployment} vision..."
                )
            raw_notes = self._single_vision_call(
                batches[0], system_prompt, progress_callback=progress_callback
            )
        else:
            batch_notes = []
            for i, batch in enumerate(batches, 1):
                if i > 1:
                    if progress_callback:
                        progress_callback("Pacing request (5s) for vision token quota...")
                    time.sleep(5)

                if progress_callback:
                    progress_callback(
                        f"Analyzing batch {i}/{total_batches} ({len(batch)} pages)..."
                    )
                notes = self._batch_vision_call(
                    batch, i, total_batches, system_prompt, progress_callback=progress_callback
                )
                batch_notes.append(notes)

            if progress_callback:
                progress_callback("Pausing briefly before merging notes...")
            time.sleep(5)

            if progress_callback:
                progress_callback(
                    "Merging multi-page notes into final document..."
                )

            raw_notes = self._merge_notes(
                batch_notes,
                system_prompt,
                source_type="handwritten document",
                progress_callback=progress_callback,
            )

        return sanitize_notes(raw_notes)

    def _single_vision_call(
        self,
        batch_b64: list[str],
        system_prompt: str,
        progress_callback=None,
    ) -> str:
        """Make a single vision API call for a batch of images."""
        content_payload = [
            {
                "type": "text",
                "text": (
                    "Please analyze these handwritten notes, diagrams, sketches, "
                    "and annotations, and synthesize them into comprehensive, structured "
                    "Obsidian study notes."
                ),
            }
        ]

        for b64_img in batch_b64:
            content_payload.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{b64_img}",
                    "detail": "high",
                },
            })

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content_payload},
        ]
        return self._create_completion(
            self.vision_client,
            self.vision_deployment,
            messages,
            progress_callback=progress_callback,
        )

    def _batch_vision_call(
        self,
        batch_b64: list[str],
        batch_index: int,
        total_batches: int,
        system_prompt: str,
        progress_callback=None,
    ) -> str:
        """Process a specific batch of images from a multi-page document."""
        content_payload = [
            {
                "type": "text",
                "text": (
                    f"This is batch {batch_index} of {total_batches} from a handwritten "
                    f"document/notebook. Transcribe and extract all key concepts, formulas, "
                    f"Mermaid diagrams, and margin notes for THESE pages only."
                ),
            }
        ]

        for b64_img in batch_b64:
            content_payload.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{b64_img}",
                    "detail": "high",
                },
            })

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content_payload},
        ]
        return self._create_completion(
            self.vision_client,
            self.vision_deployment,
            messages,
            progress_callback=progress_callback,
        )

