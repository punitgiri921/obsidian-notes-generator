"""
Azure OpenAI client with smart auto-chunking for long transcripts.

Handles:
  - Single API call for short transcripts (< 80k chars)
  - Chunked calls + merge for long transcripts (> 80k chars)
"""

import os
import re
from textwrap import dedent

from dotenv import load_dotenv
from openai import AzureOpenAI


# Threshold in characters — transcripts longer than this get chunked
CHUNK_THRESHOLD = 80_000

# Target chunk size — leave room for prompt tokens
CHUNK_SIZE = 60_000


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
            result = self._single_call(transcript, system_prompt)
        else:
            if progress_callback:
                progress_callback(
                    "Long transcript detected — "
                    "using chunked processing..."
                )
            result = self._chunked_call(
                transcript, system_prompt, progress_callback
            )

        from core.notes_generator import sanitize_notes
        return sanitize_notes(result)

    def _single_call(
        self, transcript: str, system_prompt: str
    ) -> str:
        """Make a single API call for the entire transcript."""

        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
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
            ],

            max_completion_tokens=5000,
        )

        return response.choices[0].message.content

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

        for i, chunk in enumerate(chunks, 1):
            if progress_callback:
                progress_callback(
                    f"Processing chunk {i}/{total_chunks}..."
                )

            chunk_prompt = dedent(f"""\
                This is part {i} of {total_chunks} of a
                YouTube video transcript. Generate detailed
                notes for THIS section only. Include all key
                concepts, definitions, and procedures mentioned.

                Transcript (Part {i}/{total_chunks}):

                {chunk}
            """)

            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": chunk_prompt},
                ],
    
                max_completion_tokens=5000,
            )

            chunk_notes.append(
                response.choices[0].message.content
            )

        # Merge all chunk notes into a single cohesive document
        if progress_callback:
            progress_callback("Merging notes into final document...")

        return self._merge_notes(chunk_notes, system_prompt)

    def _merge_notes(
        self, chunk_notes: list[str], system_prompt: str
    ) -> str:
        """Merge multiple chunk notes into one cohesive document."""

        combined = "\n\n---\n\n".join(
            f"## Notes from Part {i + 1}\n\n{notes}"
            for i, notes in enumerate(chunk_notes)
        )

        merge_prompt = dedent(f"""\
            Below are notes generated from different parts of
            the same YouTube video. Please merge them into a
            single, cohesive, well-structured set of study
            notes. Remove duplicate content, maintain logical
            flow, and follow the original formatting guidelines.

            Do NOT add a note saying these were merged.
            The final output should read as if it was generated
            from a single transcript.

            Separate notes to merge:

            {combined}
        """)

        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": merge_prompt},
            ],

            max_completion_tokens=5000,
        )

        return response.choices[0].message.content

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
            raw_notes = self._single_vision_call(batches[0], system_prompt)
        else:
            batch_notes = []
            for i, batch in enumerate(batches, 1):
                if progress_callback:
                    progress_callback(
                        f"Analyzing batch {i}/{total_batches} ({len(batch)} pages)..."
                    )
                notes = self._batch_vision_call(
                    batch, i, total_batches, system_prompt
                )
                batch_notes.append(notes)

            if progress_callback:
                progress_callback(
                    "Merging multi-page notes into final document..."
                )

            raw_notes = self._merge_notes(batch_notes, system_prompt)

        return sanitize_notes(raw_notes)

    def _single_vision_call(
        self,
        batch_b64: list[str],
        system_prompt: str,
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

        response = self.vision_client.chat.completions.create(
            model=self.vision_deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content_payload},
            ],
            max_completion_tokens=5000,
        )

        return response.choices[0].message.content

    def _batch_vision_call(
        self,
        batch_b64: list[str],
        batch_index: int,
        total_batches: int,
        system_prompt: str,
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

        response = self.vision_client.chat.completions.create(
            model=self.vision_deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content_payload},
            ],
            max_completion_tokens=5000,
        )

        return response.choices[0].message.content

