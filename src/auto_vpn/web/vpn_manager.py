from datetime import datetime

import countryflag
import pytz
import streamlit as st

from auto_vpn.core.app import App


class VPNManager:
    """Handles VPN-related operations"""

    def __init__(self, app_instance: App):
        self.app_instance: App = app_instance

    def get_available_locations(self) -> list[str]:
        """Get available VPN locations"""

        @st.cache_data(ttl=3600)
        def _fetch_locations():
            regions = self.app_instance.get_available_regions()
            return [f"{region.city}, {region.country}" for region in regions]

        # Call the cached function with hashable parameters
        return _fetch_locations()

    def refresh_peers(self) -> list[dict]:
        """Refresh and return the list of VPN peers"""
        servers_with_peers = self.app_instance.list_servers_with_peers()
        peers_data = []
        for server in servers_with_peers:
            for peer in server["peers"]:
                print(peer.created_at)
                peers_data.append(
                    {
                        "peer_name": peer.peer_name,
                        "country": server["server"].country,
                        "country_flag": countryflag.getflag([server["server"].country]),
                        "ip_address": server["server"].ip_address,
                        "config": peer.wireguard_config,
                        "peer_id": peer.id,
                        "created_at": peer.created_at,
                        "age": get_friendly_time_diff(peer.created_at),
                    }
                )
        return peers_data

    def create_vpn_peer(self, location: str):
        """Create a new VPN peer"""
        return self.app_instance.vpn_peer_quick(location)

    def delete_peer(self, peer_id: int):
        """Delete a VPN peer"""
        self.app_instance.delete_vpn_peer(peer_id)


def get_friendly_time_diff(created_at: datetime) -> str:
    """Convert timestamp to user-friendly time difference"""
    # Ensure created_at is timezone-aware and in UTC
    if created_at.tzinfo is None:
        created_at = pytz.UTC.localize(created_at)
    else:
        created_at = created_at.astimezone(pytz.UTC)
    now = datetime.now(pytz.UTC)
    diff = now - created_at

    minutes = int(diff.total_seconds() / 60)
    hours = int(minutes / 60)
    days = int(hours / 24)

    if days > 0:
        return f"{days}d ago"
    elif hours > 0:
        return f"{hours}h ago"
    elif minutes > 0:
        return f"{minutes}m ago"
    else:
        return "just now"
