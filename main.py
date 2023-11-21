import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import argparse
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from gpt import summarize
from utils import extract_video_id_from_url

monitored_channels = []  # List of channels to monitor

intents = discord.Intents.default()
intents.message_content = True  # Set this before creating the bot instance
bot = commands.Bot(command_prefix="!", intents=intents)

check_interval = 600  # 10 minutes

# Setting up argument parser
parser = argparse.ArgumentParser(description="Fetch YouTube video transcripts.")
parser.add_argument("--api-key", required=True, type=str, help="YouTube Data API Key")
parser.add_argument("--openai-key", required=True, type=str, help="OpenAI API Key")
parser.add_argument("--channel-id", required=True, type=str, help="YouTube Channel ID")
parser.add_argument(
    "--discord-token", required=True, type=str, help="Discord Bot Token"
)
args = parser.parse_args()

configured_channel_id = None  # This will store the configured channel ID


def get_latest_video_id(youtube, channel_id):
    request = youtube.search().list(
        part="snippet", channelId=channel_id, maxResults=1, order="date"
    )
    response = request.execute()

    if response["items"]:
        item = response["items"][0]
        video_id = item["id"]["videoId"]
        snippet = item["snippet"]
        video_title = snippet["title"]
        channel_title = snippet["channelTitle"]
        thumbnail_url = snippet["thumbnails"]["high"]["url"]
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        publish_date = snippet["publishedAt"]
        return (
            video_id,
            video_title,
            channel_title,
            thumbnail_url,
            video_url,
            publish_date,
        )
    else:
        return None, None, None, None, None, None


def extract_channel_id_from_url(url):
    # Extract the channel ID from the YouTube channel URL
    pattern = r"(?:https?:\/\/)?(?:www\.)?youtube\.com\/(?:c\/|channel\/|user\/)?([a-zA-Z0-9_-]+)"
    match = re.search(pattern, url)
    return match.group(1) if match else None


def fetch_transcript(video_id, max_length=4000):  # Adjust max_length as needed
    transcript_text = ""
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        for text in transcript:
            if (
                len(transcript_text) + len(text["text"]) < max_length - 200
            ):  # 200 char buffer
                transcript_text += text["text"] + " "
            else:
                break  # Stop adding text if max_length is reached
    except Exception as e:
        print(f"Could not get transcript for video ID {video_id}: {e}")
    return transcript_text


async def check_new_videos(youtube):
    global monitored_channels
    last_video_ids = {}  # Dictionary to store the last video ID for each channel

    while True:
        for channel_id in monitored_channels:
            (
                video_id,
                video_title,
                channel_title,
                thumbnail_url,
                video_url,
                publish_date,
            ) = get_latest_video_id(youtube, channel_id)

            if (
                video_id
                and video_id != last_video_ids.get(channel_id)
                and configured_channel_id
            ):
                print(f"New video found in {channel_title}: {video_id}")
                transcript_text = fetch_transcript(video_id)
                summary = summarize(transcript_text, args.openai_key)

                embed = discord.Embed(
                    title=f"Summary: {video_title}", description=summary, color=0x00FF00
                )
                channel = bot.get_channel(configured_channel_id)
                if channel:
                    await channel.send(embed=embed)

                last_video_ids[channel_id] = video_id

        await asyncio.sleep(check_interval)


@bot.tree.command(name="addchannel", description="Add a YouTube channel to monitor")
@app_commands.describe(url="URL of the YouTube channel")
async def addchannel(interaction: discord.Interaction, url: str):
    channel_id = extract_channel_id_from_url(url)
    if channel_id and channel_id not in monitored_channels:
        monitored_channels.append(channel_id)
        await interaction.response.send_message(
            f"Channel {channel_id} added for monitoring."
        )
    else:
        await interaction.response.send_message(
            "Invalid URL or channel already monitored."
        )


@bot.tree.command(
    name="removechannel", description="Remove a YouTube channel from monitoring"
)
async def removechannel(interaction: discord.Interaction):
    # Generate a list of options for currently monitored channels
    choices = [
        app_commands.Choice(name=channel_id, value=channel_id)
        for channel_id in monitored_channels
    ]

    @app_commands.choices(channel=choices)
    async def inner(interaction: discord.Interaction, channel: str):
        if channel in monitored_channels:
            monitored_channels.remove(channel)
            await interaction.response.send_message(
                f"Channel {channel} removed from monitoring."
            )
        else:
            await interaction.response.send_message(
                "Channel not found in monitored list."
            )

    await inner(interaction)


@bot.tree.command(
    name="config", description="Configure the channel for posting summaries"
)
@app_commands.describe(channel="Channel to post summaries")
async def config(interaction: discord.Interaction, channel: discord.TextChannel):
    global configured_channel_id
    configured_channel_id = channel.id
    await interaction.response.send_message(
        f"Configured to post summaries in {channel.mention}"
    )


@bot.tree.command(
    name="summary", description="Get summary of a specified YouTube video"
)
@app_commands.describe(url="URL of the YouTube video")
async def summary(interaction: discord.Interaction, url: str):
    await interaction.response.defer()

    video_id = extract_video_id_from_url(url)
    if not video_id:
        await interaction.followup.send("Invalid YouTube video URL.")
        return

    youtube = build("youtube", "v3", developerKey=args.api_key)
    transcript_text = fetch_transcript(video_id)
    if transcript_text:
        summary_text = summarize(transcript_text, args.openai_key)

        # Fetch additional details like title, channel name, etc.
        video_details = get_video_details(youtube, video_id)
        if video_details:
            (
                video_title,
                channel_title,
                thumbnail_url,
                video_url,
                publish_date,
            ) = video_details

            embed = discord.Embed(
                title=f"Summary: {video_title}",
                url=video_url,
                description=summary_text,
                color=0x00FF00,
            )
            embed.set_author(name=channel_title)
            embed.set_thumbnail(url=thumbnail_url)
            embed.add_field(name="Published Date", value=publish_date, inline=False)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("Could not fetch video details.")
    else:
        await interaction.followup.send(
            "Could not fetch or summarize the video transcript."
        )


def get_video_details(youtube, video_id):
    request = youtube.videos().list(part="snippet", id=video_id)
    response = request.execute()

    if response["items"]:
        item = response["items"][0]
        snippet = item["snippet"]
        video_title = snippet["title"]
        channel_title = snippet["channelTitle"]
        thumbnail_url = snippet["thumbnails"]["high"]["url"]
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        publish_date = snippet["publishedAt"]
        return video_title, channel_title, thumbnail_url, video_url, publish_date
    else:
        return None


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"{bot.user} has connected to Discord!")
    youtube = build("youtube", "v3", developerKey=args.api_key)
    asyncio.create_task(check_new_videos(youtube))


bot.run(args.discord_token)
