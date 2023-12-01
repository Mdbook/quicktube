from pymongo import MongoClient
from bson.objectid import ObjectId

class MongoDBWorker:
    def __init__(self, yt_api_key, discord_token):
        self.yt_api_key = yt_api_key
        self.discord_token = discord_token
        self.client = MongoClient('mongodb://localhost:27017/')
        # create the database if it doesn't exist
        self.db = self.client['QuickTubeServers']  # Change the database name
        self.servers = self.db.servers

    def initial_sync(self, guild_ids):
        for guild_id in guild_ids:
            if not self.server_exists(guild_id):
                self.new_server(guild_id)
        # Check to make sure all servers have current attributes
        for server in self.servers.find():
            if 'yt_api_key' not in server:
                server['yt_api_key'] = self.yt_api_key
                self.servers.replace_one({'_id': ObjectId(server['_id'])}, server)
            if 'discord_token' not in server:
                server['discord_token'] = self.discord_token
                self.servers.replace_one({'_id': ObjectId(server['_id'])}, server)
            if 'update_channel' not in server:
                server['update_channel'] = "None"
                self.servers.replace_one({'_id': ObjectId(server['_id'])}, server)
            if 'openai_key' not in server:
                server['openai_key'] = "None"
                self.servers.replace_one({'_id': ObjectId(server['_id'])}, server)
            if 'monitored_channels' not in server:
                server['monitored_channels'] = []
                self.servers.replace_one({'_id': ObjectId(server['_id'])}, server)
            if 'last_video_ids' not in server:
                server['last_video_ids'] = []
                self.servers.replace_one({'_id': ObjectId(server['_id'])}, server)

    def server_exists(self, guild_id):
        return self.servers.find_one({'guild_id': guild_id}) is not None

    def get_server(self, guild_id):
        return self.servers.find_one({'guild_id': guild_id})

    def create_server(self, server_data):
        server_data['yt_api_key'] = self.yt_api_key
        self.servers.insert_one(server_data)

    def get_openai_key(self, guild_id):
        server = self.servers.find_one({'guild_id': guild_id})
        return server.get('openai_key') if server else None

    def new_server(self, guild_id):
        server_data = {
            'guild_id': guild_id,
            'monitored_channels': [],
            'update_channel': "None",
            'openai_key': "None",
            'yt_api_key': self.yt_api_key,
            'last_video_ids': {},
        }
        self.servers.insert_one(server_data)

# Example usage
# mongo_worker = MongoDBWorker('your_yt_api_key', 'your_discord_token')
# Add other methods as needed


# class Server:
#     def __init__(self, guild_id):
#         self.guild_id = guild_id
#         self.openai_key = None
#         self.discord_token = None
#         self.api_key = None
#         self.check_interval = 600
#         self.monitored_channels = []
#         self.update_channel = None