from peewee import (
    CharField,
    ForeignKeyField,
    TextField,
    FloatField,
    DateTimeField,
    Model,
)
from datetime import datetime
import pytz
from .db import db_instance

class BaseModel(Model):
    class Meta:
        database = db_instance.proxy 

class Setting(BaseModel):
    key = CharField(unique=True)
    value = TextField()
    type = CharField()  # Type of the value (e.g., "int", "float", "bool", "json", "str")

class Server(BaseModel):
    provider = CharField() 
    project_name = CharField()
    ip_address = CharField(unique=True)
    username = CharField()
    ssh_private_key = TextField()
    location = CharField()
    stack_state = TextField()
    server_type = CharField()
    country = CharField()
    price_per_month = FloatField(null=True)
    created_at = DateTimeField(
        default=lambda: datetime.now(pytz.UTC),
        formats=['%Y-%m-%d %H:%M:%S.%f%z', '%Y-%m-%d %H:%M:%S%z']
    )

class VPNPeer(BaseModel):
    server = ForeignKeyField(Server, backref='peers', on_delete='CASCADE')
    peer_name = CharField()
    public_key = TextField()
    wireguard_config = TextField()
    created_at = DateTimeField(
        default=lambda: datetime.now(pytz.UTC),
        formats=['%Y-%m-%d %H:%M:%S.%f%z', '%Y-%m-%d %H:%M:%S%z']
    )

    class Meta:
        indexes = (
            (('server', 'peer_name'), True),  # Unique constraint on server and peer_name
        )

