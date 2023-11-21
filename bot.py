import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import argparse
import re
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from gpt import summarize
from utils import (
    extract_video_id_from_url,
    extract_channel_identifier_from_url,
    get_channel_id_from_name,
    get_channel_name,
)
from config import Config
from sql_worker import Session, ServerModel, SQLWorker

EMBED_COLOR = 0xE04141


class Quicktube:
    def __init__(self, yt_api_key, openai_key, discord_token):
        self.sql_worker = SQLWorker(yt_api_key, discord_token)
        self.yt_api_key = yt_api_key
        self.openai_key = openai_key
        self.discord_token = discord_token
        self.check_interval = 600  # 10 minutes
        self.monitored_channels = []  # List of channels to monitor
        self.configured_channel_id = None  # Store the configured channel ID
        self.last_video_ids = {}  # Store the last video ID for each channel
        self.youtube = build("youtube", "v3", developerKey=self.yt_api_key)

        intents = discord.Intents.default()
        intents.message_content = True
        self.bot = commands.Bot(command_prefix="!", intents=intents)

        @self.bot.event
        async def on_ready():
            print(f"{self.bot.user} has connected to Discord!")
            await self.bot.tree.sync()  # Sync here, after the bot is ready
            # Start checking for new videos here
            asyncio.create_task(self.check_new_videos())
            self.config.guild_id = self.bot.guilds[0].id

        self.setup_commands()

    @app_commands.describe(channel="Channel to post summaries")
    async def config(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        self.configured_channel_id = channel.id
        # store guild in to new config
        self.config.guild_id = interaction.guild.id
        await interaction.response.send_message(
            f"Configured to post summaries in {channel.mention}", ephemeral=True
        )

    def setup_commands(self):
        self.bot.tree.command(
            name="addchannel", description="Add a YouTube channel to monitor"
        )(self.addchannel)
        self.bot.tree.command(
            name="removechannel", description="Remove a YouTube channel from monitoring"
        )(self.removechannel)
        self.bot.tree.command(
            name="config", description="Configure the channel for posting summaries"
        )(self.config)
        self.bot.tree.command(
            name="summary", description="Get summary of a specified YouTube video"
        )(self.summary)
        self.bot.tree.command(
            name="listchannels", description="List all currently monitored channels"
        )(self.listchannels)

    async def start(self):
        youtube = build("youtube", "v3", developerKey=self.yt_api_key)
        await self.bot.start(self.discord_token)

    def get_latest_video_id(self, channel_id):
        request = self.youtube.search().list(
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

    async def check_new_videos(self):
        while True:
            print("checking")
            for channel_id in self.monitored_channels:
                (
                    video_id,
                    video_title,
                    channel_title,
                    thumbnail_url,
                    video_url,
                    publish_date,
                ) = self.get_latest_video_id(channel_id)

                if (
                    video_id
                    and video_id != self.last_video_ids.get(channel_id)
                    and self.configured_channel_id
                ):
                    print(f"New video found in {channel_title}: {video_id}")
                    transcript_text = self.fetch_transcript(video_id)
                    summary_text = summarize(transcript_text, self.openai_key)
                    print("prepping embed")
                    video_details = self.get_video_details(video_id)
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
                            color=EMBED_COLOR,
                        )
                        embed.set_author(name=channel_title)
                        embed.set_thumbnail(url=thumbnail_url)
                        embed.add_field(
                            name="Published Date", value=publish_date, inline=False
                        )
                        channel = self.bot.get_channel(self.configured_channel_id)
                        if channel:
                            await channel.send(embed=embed)
                        self.last_video_ids[channel_id] = video_id
                    else:
                        await interaction.followup.send(
                            "Could not fetch video details."
                        )

            await asyncio.sleep(self.check_interval)

    @app_commands.describe(url="URL of the YouTube video")
    async def summary(self, interaction: discord.Interaction, url: str):
        await interaction.response.defer()

        video_id = extract_video_id_from_url(url)
        if not video_id:
            await interaction.followup.send(
                "Invalid YouTube video URL.", ephemeral=True
            )
            return

        transcript_text = self.fetch_transcript(video_id)
        if transcript_text:
            summary_text = summarize(transcript_text, self.openai_key)

            # Fetch additional details like title, channel name, etc.
            video_details = self.get_video_details(video_id)
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
                    color=EMBED_COLOR,
                )
                embed.set_author(name=channel_title)
                embed.set_thumbnail(url=thumbnail_url)
                embed.add_field(name="Published Date", value=publish_date, inline=False)
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(
                    "Could not fetch video details."
                )
        else:
            await interaction.followup.send(
                "Could not fetch or summarize the video transcript."
            )

    def get_video_details(self, video_id):
        request = self.youtube.videos().list(part="snippet", id=video_id)
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

    def fetch_transcript(
        self, video_id, max_length=4000
    ):  # Adjust max_length as needed
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

    @app_commands.describe(url="URL of the YouTube channel")
    async def addchannel(self, interaction: discord.Interaction, url: str):
        identifier = extract_channel_identifier_from_url(url)
        channel_id = identifier

        # If the identifier is not in the channel ID format, retrieve the channel ID
        if identifier and not identifier.startswith("UC"):
            channel_id = get_channel_id_from_name(self.youtube, identifier)

        if channel_id and channel_id not in self.monitored_channels:
            self.monitored_channels.append(channel_id)
            channel_name = get_channel_name(self.youtube, channel_id)
            await interaction.response.send_message(
                f"Channel **{channel_name}** added for monitoring.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "Invalid URL or channel already monitored.", ephemeral=True
            )

    @app_commands.describe()
    async def listchannels(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        # Check if there are monitored channels
        if not self.monitored_channels:
            await interaction.followup.send(
                "No channels are currently being monitored.", ephemeral=True
            )
            return

        # Start creating the embed
        embed = discord.Embed(title="Monitored YouTube Channels", color=EMBED_COLOR)
        # embed.set_thumbnail(url="URL_TO_A_RELEVANT_IMAGE")  # Optional: Set a thumbnail image for the embed
        # Iterate over monitored channels and add their information to the embed
        for index, channel_id in enumerate(self.monitored_channels):
            channel_name = get_channel_name(self.youtube, channel_id)
            embed.add_field(
                name=f"{index+1}. {channel_name}",
                value=f"ID: `{channel_id}`",
                inline=False,
            )
        # Send the embed in the response
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.describe(channel_identifier="Name or ID of the YouTube Channel")
    async def removechannel(
        self, interaction: discord.Interaction, channel_identifier: str
    ):
        # Check if channel_identifier is a channel ID in the monitored list
        if channel_identifier in self.monitored_channels:
            channel_name = get_channel_name(self.youtube, channel_identifier)
            self.monitored_channels.remove(channel_identifier)
        else:
            # Check if the identifier is a digit (index)
            if channel_identifier.isdigit():
                index = (
                    int(channel_identifier) - 1
                )  # Subtract one for zero-based indexing
                if 0 <= index < len(self.monitored_channels):
                    channel_id = self.monitored_channels[index]
                    channel_name = get_channel_name(self.youtube, channel_id)
                    self.monitored_channels.pop(
                        index
                    )  # Remove the channel at the given index
                else:
                    await interaction.response.send_message(
                        "Invalid index provided.", ephemeral=True
                    )
                    return
            else:
                # If not a channel ID or index, check if it's a channel name
                found = False
                for channel_id in self.monitored_channels:
                    name = get_channel_name(self.youtube, channel_id)
                    if channel_identifier == name:
                        self.monitored_channels.remove(channel_id)
                        channel_name = name
                        found = True
                        break

                if not found:
                    await interaction.response.send_message(
                        "Channel not found in the monitored list.", ephemeral=True
                    )
                    return

        await interaction.response.send_message(
            f"Channel **{channel_name}** removed from monitoring.", ephemeral=True
        )


def main():
    # Setting up argument parser
    parser = argparse.ArgumentParser(description="Fetch YouTube video transcripts.")
    parser.add_argument(
        "--api-key", required=True, type=str, help="YouTube Data API Key"
    )
    parser.add_argument("--openai-key", required=True, type=str, help="OpenAI API Key")
    parser.add_argument(
        "--discord-token", required=True, type=str, help="Discord Bot Token"
    )
    args = parser.parse_args()

    bot = Quicktube(args.api_key, args.openai_key, args.discord_token)
    asyncio.run(bot.start())


if __name__ == "__main__":
    main()
