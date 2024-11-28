import pytz
import requests
from datetime import datetime, timedelta
from typing import List, Optional, Dict

from auto_vpn.db.models import Server, VPNPeer
from auto_vpn.db.db import db_instance
from auto_vpn.db.repository import Repository
from auto_vpn.providers.infra_manager import InfrastructureManager
from auto_vpn.providers.vultr_manager import VultrManager
from auto_vpn.providers.vultr_api import VultrAPI
from .wg_manager import WireGuardManager
from .utils import generate_projectname, generate_peername, setup_logger, generate_public_key

logger = setup_logger(name="auto_vpn.app")

# Define a default Pulumi config passphrase constant
DEFAULT_PULUMI_CONFIG_PASSPHRASE = "1"

class App:
    """
    Application Layer that orchestrates interactions between DataLayer, Provider Managers,
    and VPN Managers to manage cloud providers, servers, and VPN peers.
    """
    
    SUPPORTED_PROVIDERS = {'vultr', 'linode'}
    INACTIVITY_THRESHOLD_KEY = "inactivity_threshold"
    DEFAULT_INACTIVITY_THRESHOLD = timedelta(hours=1)

    def __init__(self, 
             db_path: str = 'data_layer.db', 
             inactivity_threshold: Optional[timedelta] = None,
             vultr_api_key: Optional[str] = None,
             linode_api_key: Optional[str] = None):
        """
        Initialize the Application Layer with database connection.
        
        :param db_path: Path to the SQLite database file.
        """
        db_instance.init_db(database_path=db_path)

        self.data_layer = Repository()
        self._vultr_api_cache = {}
        self.minimum_server_age = timedelta(minutes=15)
        self.ssh_key_path = '~/.ssh/id_rsa'

        # Store API keys
        self.provider_credentials = {
            'vultr': vultr_api_key,
            'linode': linode_api_key
        }

        # Initialize inactivity threshold setting if it doesn't exist
        try:
            self.data_layer.get_setting(self.INACTIVITY_THRESHOLD_KEY)
        except ValueError:
            self.data_layer.set_setting(self.INACTIVITY_THRESHOLD_KEY, self.DEFAULT_INACTIVITY_THRESHOLD)
        
        # If inactivity_threshold is provided, update the setting
        if inactivity_threshold is not None:
            self.set_inactivity_threshold(inactivity_threshold)

    def get_inactivity_threshold(self) -> timedelta:
        """
        Get the current inactivity threshold setting.
        
        :return: Current inactivity threshold as timedelta
        """
        return self.data_layer.get_setting(self.INACTIVITY_THRESHOLD_KEY)

    def set_inactivity_threshold(self, threshold: timedelta) -> None:
        """
        Set a new inactivity threshold.
        
        :param threshold: New threshold value as timedelta
        """
        if not isinstance(threshold, timedelta):
            raise ValueError("Threshold must be a timedelta instance")
        self.data_layer.set_setting(self.INACTIVITY_THRESHOLD_KEY, threshold)

        # Reset the cache
        if hasattr(self, '_cached_threshold'):
            delattr(self, '_cached_threshold')
        if hasattr(self, '_threshold_cache_time'):
            delattr(self, '_threshold_cache_time')

    @property
    def inactivity_threshold(self) -> timedelta:
        """
        Property to access the current inactivity threshold.
        Cached for 10 minutes to avoid frequent database access.
        
        :return: Current inactivity threshold as timedelta
        """
        if not hasattr(self, '_cached_threshold') or \
           not hasattr(self, '_threshold_cache_time') or \
           datetime.now() - self._threshold_cache_time > timedelta(minutes=10):
            self._cached_threshold = self.get_inactivity_threshold()
            self._threshold_cache_time = datetime.now()
        return self._cached_threshold

    # ----------------- Server Methods ----------------- #

    def create_server(self, provider: str, location: str) -> Server:
        """
        Create a new server on the specified provider.
        :param provider: Name of the provider.
        :param location: Server location or region.
        :param server_type: Type of the server (e.g., 't2.medium').
        :return: The created Server object.
        :raises ValueError: If the provider does not exist or server creation fails.
        """
        provider = provider.lower()
        if provider not in self.SUPPORTED_PROVIDERS:
            raise ValueError(f"Unsupported provider: {provider}")
        
        if not self.provider_credentials.get(provider):
            raise ValueError(f"No API key provided for {provider}")

        server_type = 'vc2-1c-1gb'

        # Generate project name
        project_name = generate_projectname()

        # Initialize the appropriate InfrastructureManager based on provider type
        provider_manager = self._initialize_provider_manager(provider, project_name)
        if not provider_manager:
            raise ValueError(f"No manager available for provider type: {provider.provider_type}")

        # Deploy the Pulumi stack to create the server
        up_result = provider_manager.up(location=location, server_type=server_type)

        # Extract outputs from Pulumi stack
        instance_ip = up_result.outputs.get('instance_ip').value

        # Add server to the database
        server = self.data_layer.create_server(
            provider=provider,
            project_name=project_name,
            ip_address=instance_ip,
            username='root',  # Enforce 'root' as the SSH username
            ssh_private_key="",  # Placeholder, as SSH key management is removed
            ssh_public_key="",   # Placeholder
            location=location,
            server_type=server_type,
        )
        return server

    def get_all_servers(self) -> List[Server]:
        """
        Retrieve all servers or servers for a specific provider.
        :return: List of Server objects.
        """
        return self.data_layer.list_servers()

    def delete_server(self, server_id: int) -> None:
        """
        Delete a server and its associated VPN peers.
        :param server_id: ID of the server to delete.
        :raises ValueError: If the server does not exist.
        """
        server = self.data_layer.get_server_by_id(server_id)
        if not server:
            raise ValueError(f"Server with ID {server_id} does not exist.")

        provider_manager = self._initialize_provider_manager(server.provider, server.project_name)
        if not provider_manager:
            raise ValueError(f"No manager available for provider: {server.provider}")

        # Destroy the Pulumi stack to delete the server
        provider_manager.destroy()

        # Delete server from the database
        self.data_layer.delete_server(server_id)

    def delete_all_servers(self) -> None:
        """
        Delete all servers along with their associated VPN peers.
        """
        servers = self.get_all_servers()
        for server in servers:
            try:
                self.delete_server(server.id)
            except Exception as e:
                print(f"Error deleting server {server}: {e}")

    # ----------------- VPN Peer Methods ----------------- #

    def vpn_peer_quick(self, location: str) -> VPNPeer:
        """
        Quickly create a VPN peer in the specified location.
        If a server in that location does not exist, create one.

        :param location: String indicating the desired location (e.g., 'germany').
        :return: The created VPNPeer object with WireGuard configuration.
        :raises ValueError: If no providers are available or operations fail.
        """
        # Use first available configured provider
        available_providers = [
            provider for provider, api_key in self.provider_credentials.items() 
            if api_key is not None
        ]
        if not available_providers:
            raise ValueError("No providers configured. Please provide API keys during initialization.")

        # For simplicity, use the first available provider
        provider = available_providers[0]
        # Search for regions matching the location
        try:
            search_results = self.search_regions(provider=provider, search_term=location)
        except ValueError as e:
            raise ValueError(f"Error searching regions: {e}")

        if not search_results:
            raise ValueError(f"No regions found matching the location '{location}'")

        # Use the first matching region
        region_id = search_results[0]['id']
        region_name = f"{search_results[0]['city']}, {search_results[0]['country']}"

        # Check if a server in this region already exists
        # TODO: need to to get all server only for specific provider
        servers = self.get_all_servers()
        server = None
        for srv in servers:
            if srv.location == region_id:
                # Found a server in the desired region
                server = srv
                break

        if not server:
            # No server in the desired region, create one
            try:
                server = self.create_server(provider=provider, location=region_id)
                print(f"Created server in region {region_name} - {region_id} with IP {server.ip_address}")
            except Exception as e:
                raise ValueError(f"Error creating server: {e}")
        else:
            print(f"Using existing server in region {region_name} with IP {server.ip_address}")

        # Create a VPN peer on the server
        try:
            vpn_peer = self.add_vpn_peer(server_id=server.id)
            print(f"Added VPN peer: {vpn_peer.peer_name}")
        except Exception as e:
            raise ValueError(f"Error adding VPN peer: {e}")

        # Retrieve the WireGuard configuration
        try:
            config = self.get_peer_config(vpn_peer.peer_name)
            vpn_peer.wireguard_config = config  # Ensure the config is set
        except Exception as e:
            raise ValueError(f"Error retrieving VPN peer config: {e}")

        return vpn_peer

    def clear_unused_servers(self) -> None:
        """
        Clears unused servers based on WireGuard peer handshakes.
        
        This function performs the following steps:
        1. Retrieves all servers along with their associated VPN peers.
        2. Skips servers younger than minimum_server_age.
        3. For each eligible server:
            a. Fetches the latest handshake times for each peer using WireGuardManager.
            b. Determines if all peers have either:
                - Last handshake older than inactivity_threshold, or
                - No handshake and were created over inactivity_threshold ago.
        4. Deletes the server if the above conditions are met.
        
        All time calculations are performed in UTC.
        """
        servers_with_peers = self.list_servers_with_peers()
        current_time = datetime.utcnow().replace(tzinfo=pytz.UTC)
        activity_threshold_time = current_time - self.inactivity_threshold
        minimum_age_time = current_time - self.minimum_server_age

        for server_entry in servers_with_peers:
            server = server_entry['server']
            peers = server_entry['peers']

            # Skip young servers
            server_age = server.created_at.replace(tzinfo=pytz.UTC)
            if server_age > minimum_age_time:
                logger.debug(f"Skipping server {server.ip_address} - too young (age: {current_time - server_age})")
                continue

            try:
                # Initialize WireGuardManager for the server
                wireguard_manager = WireGuardManager(
                    hostname=server.ip_address,
                    username=server.username,
                    ssh_key_path=self.ssh_key_path,
                )

                # Get the latest handshakes for all peers on the server
                handshakes = wireguard_manager.get_latest_handshakes()

                if self._should_delete_server(peers, handshakes, activity_threshold_time):
                    try:
                        self.delete_server(server.id)
                        logger.info(
                            f"Deleted server {server.ip_address} due to inactivity "
                            f"(server age: {current_time - server_age})"
                        )
                    except Exception as e:
                        logger.error(f"Error deleting server {server.ip_address}: {e}")
            except Exception as e:
                logger.error(f"Error processing server {server.ip_address}: {e}")

    def _should_delete_server(self, peers, handshakes, activity_threshold_time) -> bool:
        """
        Determines if a server should be deleted based on peer activity.
        
        Args:
            peers: List of VPNPeer objects
            handshakes: Dictionary of public_key -> last_handshake_time
            activity_threshold_time: datetime marking the threshold for inactivity
            
        Returns:
            bool: True if the server should be deleted, False otherwise
        """
        if not peers:
            return True  # Delete servers with no peers

        for peer in peers:
            handshake_time = handshakes.get(peer.public_key)
            logger.debug(f"Peer {peer.peer_name} - Last Handshake: {handshake_time}")
            
            if handshake_time:
                # Ensure handshake_time is timezone-aware
                if handshake_time.tzinfo is None:
                    handshake_time = handshake_time.replace(tzinfo=pytz.UTC)
                    
                # Check if the last handshake was within the activity threshold
                if handshake_time >= activity_threshold_time:
                    return False
            else:
                # No handshake has occurred; check the peer's creation time
                peer_creation_time = peer.created_at.replace(tzinfo=pytz.UTC)
                if peer_creation_time >= activity_threshold_time:
                    return False

        return True  # All peers are inactive

    def add_vpn_peer(self, server_id: int) -> VPNPeer:
        """
        Add a new VPN peer to a specified server.
        :param server_id: ID of the server.
        :return: The created VPNPeer object.
        :raises ValueError: If the server does not exist or peer creation fails.
        """
        server = self.data_layer.get_server_by_id(server_id)
        if not server:
            raise ValueError(f"Server with ID {server_id} does not exist.")

        # Initialize WireGuardManager for the server
        wireguard_manager = WireGuardManager(
            hostname=server.ip_address,
            username=server.username,
            ssh_key_path='~/.ssh/id_rsa',  # Placeholder, as SSH key management is removed
        )

        # Generate a unique peer name
        peer_name = generate_peername(server.project_name)

        # Add the VPN peer
        try:
            wg_config, private_key = wireguard_manager.add_client(peer_name)
        except Exception as e:
            raise ValueError(f"Error adding VPN peer: {e}")

        public_key = generate_public_key(private_key)

        # Add VPN peer to the database
        vpn_peer = self.data_layer.create_peer(
            server_id=server_id,
            peer_name=peer_name,
            public_key=public_key,
            wireguard_config=wg_config,
        )
        return vpn_peer

    def delete_vpn_peer(self, peer_id: int) -> None:
        """
        Delete a VPN peer. If it's the last peer on the server, delete the server as well.
        :param peer_id: ID of the VPN peer to delete.
        :raises ValueError: If the VPN peer does not exist.
        """
        peer = self.data_layer.get_peer_by_id(peer_id)
        if not peer:
            raise ValueError(f"VPN Peer with ID {peer_id} does not exist.")

        server = peer.server
        wireguard_manager = WireGuardManager(
            hostname=server.ip_address,
            username='root',
            ssh_key_path='~/.ssh/id_rsa',
        )

        # Remove the VPN peer
        wireguard_manager.remove_client(peer.peer_name)

        # Delete the VPN peer from the database
        self.data_layer.delete_peer(peer_id)

        # Check if it's the last peer on the server
        remaining_peers = self.data_layer.list_peers()
        if not any(p.server.id == server.id for p in remaining_peers):
            # No remaining peers, delete the server
            self.delete_server(server.id)

    def delete_all_peers(self) -> None:
        """
        Delete all VPN peers. If a server has no remaining peers, delete the server as well.
        """
        peers = self.data_layer.list_peers()
        for peer in peers:
            try:
                self.delete_vpn_peer(peer.id)
            except Exception as e:
                print(f"Error deleting VPN peer {peer.peer_name}: {e}")

    def get_peer_config(self, peer_name: str) -> str:
        """
        Retrieve WireGuard configuration for a peer by its name.
        :param peer_name: Name of the VPN peer.
        :return: WireGuard configuration string.
        :raises ValueError: If the VPN peer does not exist.
        """
        peers = self.data_layer.list_peers()
        peer = next((p for p in peers if p.peer_name == peer_name), None)
        if not peer:
            raise ValueError(f"VPN Peer with name '{peer_name}' does not exist.")
        return peer.wireguard_config

    # ----------------- Utility Methods ----------------- #

    def _initialize_provider_manager(self, provider: str, project_name: str) -> Optional[InfrastructureManager]:
        """
        Initialize the InfrastructureManager for a given provider.
        :param provider: Provider type ('vultr' or 'linode')
        :param project_name: Name of the project
        :return: An instance of InfrastructureManager or its subclass
        """
        provider = provider.lower()
        if provider == 'vultr':
            return VultrManager(
                pulumi_config_passphrase=DEFAULT_PULUMI_CONFIG_PASSPHRASE,
                vultr_api_key=self.provider_credentials['vultr'],
                project_name=project_name
            )
        elif provider == 'linode':
            # Add Linode manager implementation when needed
            return None
        return None

    def _get_provider_api(self, provider: str) -> VultrAPI:
        """
        Initialize and return a cached VultrAPI instance.
        :param provider: Provider type ('vultr')
        :return: An instance of VultrAPI
        :raises ValueError: If the provider is not supported or no API key is available
        """
        provider = provider.lower()
        if provider != 'vultr':
            raise ValueError(f"Provider {provider} is not supported for API operations")

        if provider not in self._vultr_api_cache:
            if not self.provider_credentials.get(provider):
                raise ValueError(f"No API key provided for {provider}")
            
            self._vultr_api_cache[provider] = VultrAPI(
                api_key=self.provider_credentials[provider]
            )
        
        return self._vultr_api_cache[provider]

    def get_available_regions(self, provider: str, plan_id: str = "vc2-1c-1gb") -> List[Dict]:
        """
        Retrieve available regions for a specific provider and plan using VultrAPI.
        :param provider_id: ID of the Vultr provider.
        :param plan_id: The plan ID to check for availability (default is 'vc2-1c-1gb').
        :return: A list of dictionaries containing region details.
        :raises ValueError: If the provider is invalid or API call fails.
        """
        vultr_api = self._get_provider_api(provider)
        try:
            regions = vultr_api.get_regions_with_plan(plan_id)
            return regions
        except requests.HTTPError as e:
            raise ValueError(f"Failed to retrieve regions: {e}")

    def search_regions(self, provider: str, search_term: str, plan_id: str = "vc2-1c-1gb") -> List[Dict]:
        """
        Search for regions by city or country name/code within the cached regions with the specified plan.
        
        :param provider_id: ID of the Vultr provider.
        :param search_term: The term to search for in city or country.
        :param plan_id: The plan ID to check for availability (default is 'vc2-1c-1gb').
        :return: A list of dictionaries containing matching regions.
        :raises ValueError: If the provider is invalid or API call fails.
        """
        vultr_api = self._get_provider_api(provider)
        try:
            results = vultr_api.search(search_term, plan_id)
            return results
        except requests.HTTPError as e:
            raise ValueError(f"Failed to search regions: {e}")


    # ----------------- Additional Methods ----------------- #

    def list_servers_with_peers(self) -> List[Dict]:
        """
        List servers along with their associated VPN peers.
        :return: List of dictionaries containing server and its peers.
        """
        return self.data_layer.list_servers_with_peers()
