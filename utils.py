import re


def extract_video_id_from_url(url):
    # Regex pattern for YouTube video URL
    pattern = r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/watch\?v=|youtu.be\/)([a-zA-Z0-9_-]{11})"
    match = re.search(pattern, url)
    print(match)
    return match.group(1) if match else None
