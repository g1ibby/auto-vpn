import json
from datetime import timedelta

from peewee import (
    DoesNotExist,
    IntegrityError,
)

from .db import db_instance
from .models import Server, Setting, VPNPeer


class Repository:
    # Server Methods
    def create_server(
        self,
        provider: str,
        project_name: str,
        ip_address: str,
        username: str,
        ssh_private_key: str,
        location: str,
        stack_state: str,
        server_type: str,
        country: str,
        price_per_month: float | None = None,
    ) -> Server:
        """Create a new server."""
        with db_instance.connection():
            try:
                server = Server.create(
                    provider=provider,
                    project_name=project_name,
                    ip_address=ip_address,
                    username=username,
                    ssh_private_key=ssh_private_key,
                    location=location,
                    stack_state=stack_state,
                    server_type=server_type,
                    country=country,
                    price_per_month=price_per_month,
                )
                return server
            except IntegrityError as e:
                raise ValueError(
                    f"Server with IP '{ip_address}' already exists."
                ) from e

    def list_servers(self, provider: str | None = None) -> list[Server]:
        """List all servers or servers for a specific provider."""
        with db_instance.connection():
            if provider is not None:
                return list(Server.select().where(Server.provider == provider))
            return list(Server.select())

    def delete_server(self, server_id: int) -> None:
        """Delete a server and all its associated VPN peers."""
        with db_instance.connection():
            server = self.get_server_by_id(server_id)
            with db_instance.db.atomic():
                # Peewee with on_delete='CASCADE' should handle deleting peers
                server.delete_instance()

    def get_server_by_id(self, server_id: int) -> Server:
        """Retrieve a server by its ID."""
        with db_instance.connection():
            try:
                return Server.get_by_id(server_id)
            except DoesNotExist as e:
                raise ValueError(f"Server with ID {server_id} does not exist.") from e

    # VPN Peer Methods
    def create_peer(
        self, server_id: int, peer_name: str, public_key: str, wireguard_config: str
    ) -> VPNPeer:
        """Create a new VPN peer for a server."""
        with db_instance.connection():
            server = self.get_server_by_id(server_id)
            try:
                peer = VPNPeer.create(
                    server=server,
                    peer_name=peer_name,
                    public_key=public_key,
                    wireguard_config=wireguard_config,
                )
                return peer
            except IntegrityError as e:
                raise ValueError(
                    f"Peer with name '{peer_name}' already exists for this server."
                ) from e

    def list_peers(self) -> list[VPNPeer]:
        """List all VPN peers with server information."""
        with db_instance.connection():
            return list(VPNPeer.select(VPNPeer, Server).join(Server))

    def get_wireguard_config(self, peer_id: int) -> str:
        """Retrieve the WireGuard configuration for a specific peer."""
        with db_instance.connection():
            peer = self.get_peer_by_id(peer_id)
            return peer.wireguard_config

    def delete_peer(self, peer_id: int) -> None:
        """Delete a specific VPN peer."""
        with db_instance.connection():
            peer = self.get_peer_by_id(peer_id)
            peer.delete_instance()

    def get_peer_by_id(self, peer_id: int) -> VPNPeer:
        """Retrieve a VPN peer by its ID."""
        with db_instance.connection():
            try:
                return VPNPeer.get_by_id(peer_id)
            except DoesNotExist as e:
                raise ValueError(f"VPN Peer with ID {peer_id} does not exist.") from e

    # Additional Utility Methods
    def list_servers_with_peers(self) -> list[dict]:
        """List all servers with their associated peers."""
        with db_instance.connection():
            servers = Server.select().prefetch(VPNPeer)
            result = []
            for server in servers:
                server_info = {"server": server, "peers": list(server.peers)}
                result.append(server_info)
            return result

    def set_setting(self, key: str, value):
        """Add or update a setting."""
        type_map = {
            int: "int",
            float: "float",
            bool: "bool",
            dict: "json",
            list: "json",
            str: "str",
            timedelta: "timedelta",
        }
        value_type = type(value)

        # Determine type and serialize value
        if value_type in type_map:
            type_str = type_map[value_type]
            if type_str == "json":
                value = json.dumps(value)
            elif type_str == "bool":
                value = str(int(value))  # Convert True/False to 1/0
            elif type_str == "timedelta":
                value = str(
                    int(value.total_seconds())
                )  # Store timedelta as total seconds
            else:
                value = str(value)
        else:
            raise ValueError(f"Unsupported type: {value_type}")

        with db_instance.connection():
            try:
                Setting.insert(key=key, value=value, type=type_str).on_conflict(
                    conflict_target=[Setting.key],
                    preserve=[Setting.value, Setting.type],
                ).execute()
            except IntegrityError as e:
                raise ValueError(f"Error saving setting '{key}'.") from e

    def get_setting(self, key: str):
        """Retrieve a setting by its key."""
        with db_instance.connection():
            try:
                setting = Setting.get(Setting.key == key)
                value, type_str = setting.value, setting.type
                # Deserialize value based on type
                if type_str == "int":
                    return int(value)
                elif type_str == "float":
                    return float(value)
                elif type_str == "bool":
                    return bool(int(value))
                elif type_str == "json":
                    return json.loads(value)
                elif type_str == "str":
                    return value
                elif type_str == "timedelta":
                    return timedelta(seconds=int(value))
                else:
                    raise ValueError(f"Unknown type '{type_str}' for key '{key}'.")
            except DoesNotExist:
                raise ValueError(f"Setting with key '{key}' does not exist.")
