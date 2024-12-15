from datetime import timedelta
import streamlit as st
from typing import List, Dict
from auto_vpn.core.app import App

class VPNManager:
    """Handles VPN-related operations"""
    
    def __init__(self, app_instance: App):
        self.app_instance: App = app_instance
    
    def get_available_locations(self) -> List[str]:
        """Get available VPN locations"""
        @st.cache_data(ttl=3600)
        def _fetch_locations():
            regions = self.app_instance.get_available_regions()
            for region in regions:
                print(f"Region: {region.city}, {region.country}, {region.id}")
            return [f"{region.city}, {region.country}" for region in regions]
        
        # Call the cached function with hashable parameters
        return _fetch_locations()
    
    def refresh_peers(self) -> List[Dict]:
        """Refresh and return the list of VPN peers"""
        servers_with_peers = self.app_instance.list_servers_with_peers()
        peers_data = []
        for server in servers_with_peers:
            for peer in server['peers']:
                peers_data.append({
                    'peer_name': peer.peer_name,
                    'location': server['server'].location,
                    'ip_address': server['server'].ip_address,
                    'config': peer.wireguard_config,
                    'peer_id': peer.id
                })
        return peers_data
    
    def create_vpn_peer(self, location: str):
        """Create a new VPN peer"""
        return self.app_instance.vpn_peer_quick(location)
    
    def delete_peer(self, peer_id: int):
        """Delete a VPN peer"""
        self.app_instance.delete_vpn_peer(peer_id)
