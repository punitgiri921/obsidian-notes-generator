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


def extract_playlist_id(url: str) -> str | None:
    """
    Extract the playlist ID from various YouTube URL formats.
    
    Supports:
      - https://www.youtube.com/playlist?list=PLAYLIST_ID
      - https://www.youtube.com/watch?v=VIDEO_ID&list=PLAYLIST_ID
      - Raw playlist ID starting with PL, RD, UL, etc.
    """
    if not url:
        return None
    url = url.strip()
    if (url.startswith("PL") or url.startswith("RD") or url.startswith("UL")) and len(url) >= 12 and "/" not in url:
        return url
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "list" in qs and qs["list"]:
        return qs["list"][0]
    return None


def is_playlist_url(url: str) -> bool:
    """Check if the provided URL or string is a YouTube playlist."""
    return extract_playlist_id(url) is not None


def get_playlist_videos(playlist_url_or_id: str) -> list[dict]:
    """
    Extract all video IDs and titles from a YouTube playlist without an API key.

    Returns:
        List of dicts: [{'video_id': ..., 'title': ..., 'url': ...}]
    """
    import json
    import requests

    pl_id = extract_playlist_id(playlist_url_or_id) or playlist_url_or_id.strip()
    url = f"https://www.youtube.com/playlist?list={pl_id}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()

    match = re.search(r"var ytInitialData = ({.*?});</script>", resp.text)
    if not match:
        raise ValueError(f"Could not extract playlist data from YouTube page for list={pl_id}.")

    data = json.loads(match.group(1))
    videos = []

    # Strategy 1: Search lockupViewModel (YouTube modern desktop layout)
    try:
        tabs = data["contents"]["twoColumnBrowseResultsRenderer"]["tabs"]
        sec_contents = tabs[0]["tabRenderer"]["content"]["sectionListRenderer"]["contents"]
        items = sec_contents[0]["itemSectionRenderer"]["contents"]
        for item in items:
            lvm = item.get("lockupViewModel", {})
            content_id = lvm.get("contentId")
            metadata = lvm.get("metadata", {}).get("lockupMetadataViewModel", {})
            title = metadata.get("title", {}).get("content", "")
            if content_id and len(content_id) == 11:
                videos.append({
                    "video_id": content_id,
                    "title": title or f"Video {content_id}",
                    "url": f"https://www.youtube.com/watch?v={content_id}",
                })
    except Exception:
        pass

    # Strategy 2: Search playlistVideoRenderer (classic YouTube layout)
    if not videos:
        def find_renderers(obj):
            if isinstance(obj, dict):
                if "playlistVideoRenderer" in obj:
                    r = obj["playlistVideoRenderer"]
                    vid = r.get("videoId")
                    title_obj = r.get("title", {})
                    title = title_obj.get("simpleText") or (title_obj.get("runs", [{}])[0].get("text", ""))
                    if vid:
                        videos.append({
                            "video_id": vid,
                            "title": title or f"Video {vid}",
                            "url": f"https://www.youtube.com/watch?v={vid}",
                        })
                else:
                    for v in obj.values():
                        find_renderers(v)
            elif isinstance(obj, list):
                for elem in obj:
                    find_renderers(elem)

        find_renderers(data)

    # Strategy 3: Regex deduplicated fallback
    if not videos:
        raw_ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', resp.text)
        seen = set()
        for vid in raw_ids:
            if vid not in seen:
                seen.add(vid)
                videos.append({
                    "video_id": vid,
                    "title": f"Video {vid}",
                    "url": f"https://www.youtube.com/watch?v={vid}",
                })

    # Deduplicate while strictly preserving playlist order
    unique_videos = []
    seen_ids = set()
    for v in videos:
        if v["video_id"] not in seen_ids:
            seen_ids.add(v["video_id"])
            unique_videos.append(v)

    if not unique_videos:
        raise ValueError(f"No videos found in playlist {pl_id}. Check if the playlist is public or unlisted.")

    return unique_videos
