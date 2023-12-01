import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import argparse
import re
from bson.objectid import ObjectId
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from gpt import summarize
from utils import (
    extract_video_id_from_url,
    extract_channel_identifier_from_url,
    get_channel_id_from_name,
    get_channel_name,
)
from mongo_worker import MongoDBWorker

EMBED_COLOR = 0xE04141

# TODO make sure only admins can change config

class Quicktube:
    def __init__(self, yt_api_key, discord_token):
        self.mongo = MongoDBWorker(yt_api_key, discord_token)
        self.yt_api_key = yt_api_key
        self.discord_token = discord_token
        self.check_interval = 600  # 10 minutes
        self.youtube = build("youtube", "v3", developerKey=self.yt_api_key)
        intents = discord.Intents.default()
        intents.message_content = True
        self.bot = commands.Bot(command_prefix="!", intents=intents)

        @self.bot.event
        async def on_ready():
            print(f"{self.bot.user} has connected to Discord!")
            await self.bot.tree.sync()  # Sync here, after the bot is ready
            # Start checking for new videos here
            print("Syncing databases...")
            try:
                self.mongo.initial_sync([guild.id for guild in self.bot.guilds])
            except Exception as e:
                print(f"Error during initial sync: {e}")

            print("Databases synced.")
            # print out a list of guilds and their monitored channels
            for guild in self.bot.guilds:
                print(f"Guild: {guild.name}")
                server = self.mongo.get_server(guild.id)
                print(server)
                if server:
                    print(f"Monitored Channels: {server['monitored_channels']}")
                else:
                    print("No server entry found.")
            asyncio.create_task(self.check_new_videos())

        self.setup_commands()

        @self.bot.event
        async def on_guild_join(guild):
            print(f"Joined a new guild: {guild.name}")
            if not self.mongo.server_exists(guild.id):
                self.mongo.new_server(guild.id)


    @app_commands.describe(
        channel="Channel to post summaries (optional)",
        openai_key="Your OpenAI key for using the API (optional)"
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
            #iterate through every guild id
            for guild in self.bot.guilds:
                print()
                guild_id = guild.id
                # Check to see if the server entry exists
                if not self.mongo.server_exists(guild_id):
                    # Throw fatal error
                    print(f"Fatal error: server entry does not exist for guild {guild.name}. Please contact the bot owner.")
                    continue
                # Get the server configuration
                server = self.mongo.get_server(guild_id)
                # Check to see if the server has a channel configured
                if not server['update_channel']:
                    print(f"Server {guild.name} does not have a channel configured.")
                    continue
                # Check to see if the server has an OpenAI key configured
                if not server['openai_key']:
                    print(f"Server {guild.name} does not have an OpenAI key configured.")
                    continue
                # Check to see if the server has any monitored channels
                print(server['monitored_channels'])
                if (not server['monitored_channels']) or (len(server['monitored_channels']) == 0):
                    print(f"Server {guild.name} does not have any monitored channels.")
                    continue
                # Iterate through every monitored channel
                for channel_id in server['monitored_channels']:
                    # Get the latest video ID
                    (
                        video_id,
                        video_title,
                        channel_title,
                        thumbnail_url,
                        video_url,
                        publish_date,
                    ) = self.get_latest_video_id(channel_id)
                    print('ah')
                    # Check to see if the video ID is valid
                    if not video_id:
                        print(f"Could not get latest video ID for channel {channel_title}.")
                        continue
                    # Check to see if the video ID is different from the last video ID
                    if len(server['last_video_ids']) >= 1 and server['last_video_ids'][channel_id] and video_id == server['last_video_ids'][channel_id]:
                        print(f"No new videos for channel {channel_title}.")
                        continue

                    #Check for openai key
                    if not server['openai_key'] or server['openai_key'] == "None":
                        print(f"OpenAI key not configured for server {guild.name}.")
                        continue
                    # Get the transcript text
                    transcript_text = self.fetch_transcript(video_id)
                    # Check to see if the transcript text is valid
                    if not transcript_text:
                        print(f"Could not fetch transcript text for video ID {video_id}.")
                        continue
                    # Summarize the transcript text
                    summary_text = summarize(transcript_text, server['openai_key'])
                    # Check to see if the summary text is valid
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
                        channel = self.bot.get_channel(server['update_channel'])
                        if channel:
                            await channel.send(embed=embed)
                        # update the last video ID field
                        server['last_video_ids'][channel_id] = video_id
                        # sync with mongo
                        self.mongo.servers.replace_one({'_id': ObjectId(server['_id'])}, server)
                    else:
                        await interaction.followup.send(
                            "Could not fetch video details for video {video_title}."
                        )
            await asyncio.sleep(self.check_interval)
            

    @app_commands.describe(url="URL of the YouTube video")
    async def summary(self, interaction: discord.Interaction, url: str):
        openai_key = self.mongo.get_openai_key(interaction.guild.id)
        if (not openai_key) or openai_key == "None":
            await interaction.followup.send(
                "OpenAI key not configured. Please contact the server administrator.", ephemeral=False
            )
            return
        await interaction.response.defer()
        video_id = extract_video_id_from_url(url)
        if not video_id:
            await interaction.followup.send(
                "Invalid YouTube video URL.", ephemeral=True
            )
            return
        transcript_text = self.fetch_transcript(video_id)
        if transcript_text:
            summary_text = summarize(transcript_text, self.mongo.get_openai_key(interaction.guild.id))

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
        
        # Check if channel_id is valid
        if not channel_id:
            await interaction.response.send_message(
                "Invalid URL or channel not found.", ephemeral=True
            )
            return
        # Update the mongo server
        guild_id = interaction.guild.id
        if not self.mongo.server_exists(guild_id):
            # Throw fatal error
            await interaction.response.send_message(
                "Fatal error: server entry does not exist. Please contact the bot owner.", 
                ephemeral=True
            )
        else:
            print('a')
            server = self.mongo.get_server(guild_id)
            print('b')
            if channel_id not in server['monitored_channels']:
                server['monitored_channels'].append(channel_id)
                print('c')
                try:
                    result = self.mongo.servers.replace_one({'_id': ObjectId(server['_id'])}, server)
                    if result.matched_count == 0:
                        print("No matching document found to replace.")
                    elif result.modified_count == 0:
                        print("Document found but not modified.")
                except Exception as e:
                    print(f"An error occurred: {e}")

                print('d')
                channel_name = get_channel_name(self.youtube, channel_id)
                print('e')
                await interaction.response.send_message(
                    f"Channel **{channel_name}** added for monitoring.", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "Invalid URL or channel already monitored.", ephemeral=True
                )

        # if channel_id and channel_id not in self.monitored_channels:
        #     self.monitored_channels.append(channel_id)
        #     channel_name = get_channel_name(self.youtube, channel_id)
        #     await interaction.response.send_message(
        #         f"Channel **{channel_name}** added for monitoring.", ephemeral=True
        #     )
        # else:
        #     await interaction.response.send_message(
        #         "Invalid URL or channel already monitored.", ephemeral=True
        #     )

    @app_commands.describe()
    async def listchannels(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        # Check if there are monitored channels for the guild
        if not self.mongo.server_exists(interaction.guild.id):
            # Throw fatal error
            await interaction.followup.send(
                "Fatal error: server entry does not exist. Please contact the bot owner.", ephemeral=True
            )
            return
        # Get the list of monitored channels
        server = self.mongo.get_server(interaction.guild.id)
        print(server)
        monitored_channels = server['monitored_channels']
        print(monitored_channels)
        # Check if there are monitored channels
        if not monitored_channels or len(monitored_channels) == 0:
            await interaction.followup.send(
                "No channels are currently being monitored.", ephemeral=True
            )
            return

        # Start creating the embed
        embed = discord.Embed(title="Monitored YouTube Channels", color=EMBED_COLOR)
        # embed.set_thumbnail(url="URL_TO_A_RELEVANT_IMAGE")  # Optional: Set a thumbnail image for the embed
        # Iterate over monitored channels and add their information to the embed
        for index, channel_id in enumerate(monitored_channels):
            channel_name = get_channel_name(self.youtube, channel_id)
            embed.add_field(
                name=f"{index+1}. {channel_name}",
                value=f"ID: `{channel_id}`",
                inline=False,
            )
        # Send the embed in the response
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def config(
        self, interaction: discord.Interaction, 
        channel: discord.TextChannel = None,
        openai_key: str = None
    ):
        guild_id = interaction.guild.id
        #Check to see if the server entry exists
        if not self.mongo.server_exists(guild_id):
            # Throw fatal error
            await interaction.response.send_message(
                "Fatal error: server entry does not exist. Please contact the bot owner.", 
                ephemeral=True
            )
        if channel is None and openai_key is None:
            # Grab the current server config and send it
            server = self.mongo.get_server(guild_id)
            update_channel = server['update_channel']
            openai_key_set = server['openai_key'] is not None and server['openai_key'] != "None"
            embed = discord.Embed(title="Server Configuration", color=EMBED_COLOR)
            embed.add_field(
                name="Summary Channel",
                value=f"{update_channel}",
                inline=False,
            )
            # only show the first 5 characters of the key
            embed.add_field(
                name="OpenAI Key",
                value=f"{'`' + server['openai_key'][:6] + ('*') * 13 + '`' if openai_key_set else 'None'}",
                inline=False,
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)

            
            return
        # Update the server configuration in the database
        update_data = {}
        if channel is not None:
            update_data['update_channel'] = channel.id
        if openai_key is not None:
            update_data['openai_key'] = openai_key
        # Assuming the server entry already exists
        self.mongo.servers.update_one(
            {'guild_id': guild_id},
            {'$set': update_data}
        )
        response_message = "Configuration updated."
        if channel:
            response_message += f" Summaries will be posted in {channel.mention}."
        if openai_key:
            response_message += " OpenAI key updated."
        await interaction.response.send_message(response_message, ephemeral=True)


    @app_commands.describe(channel_identifier="Name or ID of the YouTube Channel")
    async def removechannel(
        self, interaction: discord.Interaction, channel_identifier: str
    ):
        # Get server object
        guild_id = interaction.guild.id
        if not self.mongo.server_exists(guild_id):
            # Throw fatal error
            await interaction.response.send_message(
                "Fatal error: server entry does not exist. Please contact the bot owner.", 
                ephemeral=True
            )
            return
        server = self.mongo.get_server(guild_id)
        if channel_identifier in server['monitored_channels']:
            channel_name = get_channel_name(self.youtube, channel_identifier)
            server['monitored_channels'].remove(channel_identifier)
            # update the mongo db
            self.mongo.servers.replace_one({'_id': ObjectId(server['_id'])}, server)
        else:
            # Check if the identifier is a digit (index)
            if channel_identifier.isdigit():
                index = (
                    int(channel_identifier) - 1
                )  # Subtract one for zero-based indexing
                if 0 <= index < len(server['monitored_channels']):
                    channel_id = server['monitored_channels'][index]
                    channel_name = get_channel_name(self.youtube, channel_id)
                    server['monitored_channels'].pop(index)
                    # sync with mongo
                    self.mongo.servers.replace_one({'_id': ObjectId(server['_id'])}, server)
                else:
                    await interaction.response.send_message(
                        "Invalid index provided.", ephemeral=True
                    )
                    return
            else:
                found = False
                for channel_id in server['monitored_channels']:
                    name = get_channel_name(self.youtube, channel_id)
                    if channel_identifier == name:
                        server['monitored_channels'].remove(channel_id)
                        # sync with mongo
                        self.mongo.servers.replace_one({'_id': ObjectId(server['_id'])}, server)
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
    parser.add_argument(
        "--discord-token", required=True, type=str, help="Discord Bot Token"
    )
    args = parser.parse_args()

    bot = Quicktube(args.api_key, args.discord_token)
    asyncio.run(bot.start())


if __name__ == "__main__":
    main()
