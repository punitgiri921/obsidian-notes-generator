"""
YouTube transcript extraction and cleaning utilities.

Uses the youtube-transcript-api package to fetch transcripts
without needing a YouTube Data API key.
"""

import re
from urllib.parse import urlparse, parse_qs

from youtube_transcript_api import YouTubeTranscriptApi


def extract_video_id(url: str) -> str:
    """
    Extract the video ID from various YouTube URL formats.

    Supports:
      - https://www.youtube.com/watch?v=VIDEO_ID
      - https://youtu.be/VIDEO_ID
      - https://www.youtube.com/embed/VIDEO_ID
      - https://www.youtube.com/shorts/VIDEO_ID
      - https://www.youtube.com/live/VIDEO_ID

    Returns:
        The video ID string.

    Raises:
        ValueError: If the URL format is not recognized
                    or no video ID can be found.
    """

    url = url.strip()

    # Handle bare video IDs (11 characters, alphanumeric + - + _)
    if re.match(r'^[A-Za-z0-9_-]{11}$', url):
        return url

    parsed = urlparse(url)

    # youtube.com/watch?v=...
    if parsed.hostname in (
        'www.youtube.com', 'youtube.com', 'm.youtube.com'
    ):
        if parsed.path == '/watch':
            qs = parse_qs(parsed.query)
            if 'v' in qs:
                return qs['v'][0]

        # /embed/VIDEO_ID, /shorts/VIDEO_ID, /live/VIDEO_ID
        for prefix in ('/embed/', '/shorts/', '/live/'):
            if parsed.path.startswith(prefix):
                video_id = parsed.path[len(prefix):].split('/')[0]
                if video_id:
                    return video_id

    # youtu.be/VIDEO_ID
    if parsed.hostname == 'youtu.be':
        video_id = parsed.path.lstrip('/')
        if video_id:
            return video_id.split('/')[0]

    raise ValueError(
        f"Could not extract video ID from URL: {url}\n"
        "Supported formats:\n"
        "  - https://www.youtube.com/watch?v=VIDEO_ID\n"
        "  - https://youtu.be/VIDEO_ID\n"
        "  - https://www.youtube.com/shorts/VIDEO_ID"
    )


def get_transcript(video_id: str) -> str:
    """
    Fetch the transcript for a YouTube video.

    Uses youtube-transcript-api v1.x API.
    Tries English first, then falls back to any available language.

    Returns:
        The full transcript as a single string.

    Raises:
        Exception: If no transcript is available for the video.
    """

    ytt_api = YouTubeTranscriptApi()

    try:
        # Try English first
        fetched = ytt_api.fetch(video_id, languages=['en'])

        # Join all text segments
        full_text = ' '.join(
            snippet.text for snippet in fetched
        )

        return full_text

    except Exception:
        pass

    try:
        # Fall back: list available transcripts, pick first one
        transcript_list = ytt_api.list(video_id)

        if not transcript_list:
            raise Exception(
                "No transcript/captions found for this video. "
                "The video may not have captions enabled."
            )

        # Use the first available transcript
        first_lang = transcript_list[0].language_code
        fetched = ytt_api.fetch(video_id, languages=[first_lang])

        full_text = ' '.join(
            snippet.text for snippet in fetched
        )

        return full_text

    except Exception as e:
        error_msg = str(e)

        if 'disabled' in error_msg.lower():
            raise Exception(
                "This video has subtitles disabled. "
                "Cannot extract transcript."
            )
        elif 'No transcript' in error_msg:
            raise Exception(
                "No transcript/captions found for this video. "
                "The video may not have captions enabled."
            )
        else:
            raise Exception(
                f"Failed to get transcript: {error_msg}"
            )


def clean_transcript(text: str) -> str:
    """
    Clean up a raw transcript text.

    Removes:
      - [Music], [Applause], and similar bracketed annotations
      - Excessive whitespace
      - Common filler artifacts from auto-captions
    """

    # Remove bracketed annotations like [Music], [Applause], etc.
    text = re.sub(r'\[.*?\]', '', text)

    # Remove common auto-caption artifacts
    text = re.sub(r'\b(um|uh|ah|er)\b', '', text, flags=re.IGNORECASE)

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    return text
