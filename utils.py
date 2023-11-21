import re


def extract_video_id_from_url(url):
    # Regex pattern for YouTube video URL
    pattern = r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/watch\?v=|youtu.be\/)([a-zA-Z0-9_-]{11})"
    match = re.search(pattern, url)
    return match.group(1) if match else None

def extract_channel_identifier_from_url(url):
    # Pattern to match channel ID or channel/user name
    pattern = r"(?:https?:\/\/)?(?:www\.)?youtube\.com\/(?:channel\/|c\/|@|user\/)?([a-zA-Z0-9_-]+)"
    match = re.search(pattern, url)
    return match.group(1) if match else None

def get_channel_id_from_name(youtube, name):
    try:
        # First, try to get the channel by username
        request = youtube.channels().list(forUsername=name, part="id")
        response = request.execute()
        if response.get("items"):
            return response["items"][0]["id"]
        else:
            # If no channel found with username, try to search with custom URL (c/ or @)
            request = youtube.search().list(
                q=name, part="snippet", type="channel", maxResults=1
            )
            response = request.execute()
            if response.get("items"):
                return response["items"][0]["snippet"]["channelId"]
    except Exception as e:
        print(f"Error in getting channel ID from name: {e}")
    return None

def get_channel_name(youtube, channel_id):
    request = youtube.channels().list(part="snippet", id=channel_id)
    response = request.execute()

    if response["items"]:
        return response["items"][0]["snippet"]["title"]
    return "Unknown Channel"