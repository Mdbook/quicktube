from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, Integer, String, PickleType
from sqlalchemy.ext.declarative import declarative_base
init = False


class SQLWorker:
    def __init__(self, yt_api_key, discord_token):
        self.yt_api_key = yt_api_key
        self.discord_token = discord_token
        self.db_url = 'sqlite:///server_database.db'
        self.engine = create_engine(self.db_url)
        self.Session = sessionmaker(bind=self.engine)
        self.Base = declarative_base()
        
    def server_exists(self, guild_id):
        session = Session()
        server = session.query(ServerModel).filter_by(guild_id=guild_id).first()
        session.close()
        return server is not None

    def get_server(self, guild_id):
        session = Session()
        server = session.query(ServerModel).filter_by(guild_id=guild_id).first()
        session.close()
        return server

    def create_server(self, server: ServerModel):
        session = Session()
        session.add(server)
        session.commit()
        session.close()

    def get_openai_key(self, guild_id):
        session = Session()
        server = session.query(ServerModel).filter_by(guild_id=guild_id).first()
        session.close()
        return server.openai_key

    def new_server(self, guild_id):
        session = Session()
        server = ServerModel(guild_id=guild_id, check_interval=600, monitored_channels=[], update_channel=None, openai_key=None, yt_api_key=)
        session.add(server)
        session.commit()


class ServerModel(SQLWorker.Base):
    __tablename__ = 'QuicktubeServers'
    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(Integer, unique=True)
    openai_key = Column(String)
    yt_api_key = Column(String)
    check_interval = Column(Integer)
    monitored_channels = Column(PickleType)
    update_channel = Column(Integer)
    Base.metadata.create_all(engine)


# class Server:
#     def __init__(self, guild_id):
#         self.guild_id = guild_id
#         self.openai_key = None
#         self.discord_token = None
#         self.api_key = None
#         self.check_interval = 600
#         self.monitored_channels = []
#         self.update_channel = None







    session.close()