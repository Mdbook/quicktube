import argparse
import time
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from gpt import summarize

# Setting up argument parser
parser = argparse.ArgumentParser(description="Fetch YouTube video transcripts.")
parser.add_argument("--api-key", type=str, help="YouTube Data API Key")
parser.add_argument("--openai-key", type=str, help="YouTube Channel ID")
parser.add_argument("--channel-id", type=str, help="YouTube Channel ID")

args = parser.parse_args()

# Interval for checking new videos (in seconds)
check_interval = 600  # 10 minutes


def get_latest_video_id(youtube):
    request = youtube.search().list(
        part="snippet", channelId=args.channel_id, maxResults=1, order="date"
    )
    response = request.execute()

    if response["items"]:
        return response["items"][0]["id"]["videoId"]
    else:
        return None


def fetch_transcript(video_id):
    transcript_text = ""
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        for text in transcript:
            transcript_text += text["text"] + " "
    except Exception as e:
        print(f"Could not get transcript for video ID {video_id}: {e}")
    return transcript_text


def main():
    youtube = build("youtube", "v3", developerKey=args.api_key)
    last_video_id = None

    while True:
        current_video_id = get_latest_video_id(youtube)

        if current_video_id and current_video_id != last_video_id:
            print(f"New video found: {current_video_id}")
            transcript_text = fetch_transcript(current_video_id)
            print(summarize(transcript_text, args.openai_key))
            last_video_id = current_video_id

        time.sleep(check_interval)


if __name__ == "__main__":
    main()
