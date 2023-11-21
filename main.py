import argparse
from bot import Bot


def main():
    
    monitored_channels = []  # List of channels to monitor
    
    bot = Bot(args.discord_token, args.channel_id, monitored_channels)  


    # Setting up argument parser
    parser = argparse.ArgumentParser(description="Fetch YouTube video transcripts.")
    parser.add_argument("--api-key", required=True, type=str, help="YouTube Data API Key")
    parser.add_argument("--openai-key", required=True, type=str, help="OpenAI API Key")
    parser.add_argument("--channel-id", required=False, type=str, help="YouTube Channel ID")
    parser.add_argument(
        "--discord-token", required=True, type=str, help="Discord Bot Token"
    )
    args = parser.parse_args()

    
    configured_channel_id = None  # This will store the configured channel ID

if __name__ == "__main__":
    main()