import json
from datetime import datetime, timedelta
from typing import Any, ClassVar

import pytz
import requests

from auto_vpn.db.db import db_instance
from auto_vpn.db.models import Server, VPNPeer
from auto_vpn.db.repository import Repository
from auto_vpn.providers.infra_manager import InfrastructureManager
from auto_vpn.providers.linode_manager import LinodeManager
from auto_vpn.providers.provider_base import CloudProvider
from auto_vpn.providers.provider_factory import CloudProviderFactory
from auto_vpn.providers.provider_types import InstanceType, Region
from auto_vpn.providers.vultr_manager import VultrManager

from .utils import (
    deserialize_private_key,
    generate_peername,
    generate_projectname,
    generate_public_key,
    generate_ssh_keypair,
    get_public_key_text,
    serialize_private_key,
    setup_logger,
)
from .wg_manager import WireGuardManager

logger = setup_logger(name="core.app")


class App:
    """
    Application Layer that orchestrates interactions between DataLayer, Provider Managers,
    and VPN Managers to manage cloud providers, servers, and VPN peers.
    """

    SUPPORTED_PROVIDERS: ClassVar[set[str]] = {"vultr", "linode"}
    INACTIVITY_THRESHOLD_KEY = "inactivity_threshold"
    DEFAULT_INACTIVITY_THRESHOLD = timedelta(hours=1)

    def __init__(
        self,
        db_url: str,
        inactivity_threshold: timedelta | None = None,
        vultr_api_key: str | None = None,
        linode_api_key: str | None = None,
    ):
        db_instance.init_db(db_url=db_url)

        self.data_layer = Repository()
        self.minimum_server_age = timedelta(minutes=15)

        # Store API keys
        self.provider_credentials = {"vultr": vultr_api_key, "linode": linode_api_key}

        # Initialize inactivity threshold setting if it doesn't exist
        try:
            self.data_layer.get_setting(self.INACTIVITY_THRESHOLD_KEY)
        except ValueError:
            self.data_layer.set_setting(
                self.INACTIVITY_THRESHOLD_KEY, self.DEFAULT_INACTIVITY_THRESHOLD
            )

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
        if hasattr(self, "_cached_threshold"):
            delattr(self, "_cached_threshold")
        if hasattr(self, "_threshold_cache_time"):
            delattr(self, "_threshold_cache_time")

    @property
    def inactivity_threshold(self) -> timedelta:
        """
        Property to access the current inactivity threshold.
        Cached for 10 minutes to avoid frequent database access.

        :return: Current inactivity threshold as timedelta
        """
        if (
            not hasattr(self, "_cached_threshold")
            or not hasattr(self, "_threshold_cache_time")
            or datetime.now() - self._threshold_cache_time > timedelta(minutes=10)
        ):
            self._cached_threshold = self.get_inactivity_threshold()
            self._threshold_cache_time = datetime.now()
        return self._cached_threshold

    # ----------------- Server Methods ----------------- #

    def create_server(self, region: Region, type: InstanceType) -> Server:
        """
        Create a new server on the specified provider.
        :return: The created Server object.
        :raises ValueError: If the provider does not exist or server creation fails.
        """
        provider = region.provider.lower()
        if provider not in self.SUPPORTED_PROVIDERS:
            raise ValueError(f"Unsupported provider: {provider}")

        if not self.provider_credentials.get(provider):
            raise ValueError(f"No API key provided for {provider}")

        # Generate project name
        project_name = generate_projectname()

        private_key, public_key_text = generate_ssh_keypair()

        # Initialize the appropriate InfrastructureManager based on provider type
        provider_manager = self._initialize_provider_manager(
            provider, project_name, public_key_text
        )
        if not provider_manager:
            raise ValueError(
                f"No manager available for provider type: {provider.provider_type}"
            )

        # Deploy the Pulumi stack to create the server
        up_result = provider_manager.up(location=region.id, server_type=type.id)

        stack_state = provider_manager.export_stack_state()

        # Extract outputs from Pulumi stack
        instance_ip = up_result.outputs.get("instance_ip").value

        # Add server to the database
        server = self.data_layer.create_server(
            provider=provider,
            project_name=project_name,
            ip_address=instance_ip,
            username="root",  # Enforce 'root' as the SSH username
            ssh_private_key=serialize_private_key(
                private_key
            ),  # Placeholder, as SSH key management is removed
            location=region.id,
            stack_state=json.dumps(stack_state, indent=2),
            server_type=type.id,
            country=region.country,
            price_per_month=float(type.price_monthly),
        )
        return server

    def get_all_servers(self) -> list[Server]:
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

        stack_state_loaded: dict[str, Any] | None = json.loads(server.stack_state)

        private_key = deserialize_private_key(server.ssh_private_key)
        public_key_text = get_public_key_text(private_key)

        provider_manager = self._initialize_provider_manager(
            server.provider, server.project_name, public_key_text, stack_state_loaded
        )
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
                logger.warn(f"Error deleting server {server}: {e}")

    # ----------------- VPN Peer Methods ----------------- #

    def vpn_peer_quick(self, location: str) -> VPNPeer:
        """
        Quickly create a VPN peer in the specified location.
        If a server in that location does not exist, create one.

        :param location: String indicating the desired location (e.g., 'germany').
        :return: The created VPNPeer object with WireGuard configuration.
        :raises ValueError: If no providers are available or operations fail.
        """
        # Search for regions matching the location
        try:
            search_results = self.search_regions(search_term=location)
        except ValueError as e:
            raise ValueError(f"Error searching regions: {e}")
        if not search_results:
            raise ValueError(f"No regions found matching the location '{location}'")

        # Get all existing servers
        servers = self.get_all_servers()

        # Try to find a region where we already have a server
        server = None
        selected_region = None
        selected_instance = None

        for region, instance in search_results:
            if any(srv.location == region.id for srv in servers):
                selected_region = region
                selected_instance = instance
                server = next(srv for srv in servers if srv.location == region.id)
                break

        # If no existing server found, use the first result
        if not selected_region:
            selected_region, selected_instance = search_results[0]

        region_id = selected_region.id
        region_name = (
            f"{selected_region.city}, {selected_region.country}"
            if selected_region.city
            else selected_region.country
        )

        logger.debug(
            f"Selected region: {region_name} ({region_id}), {selected_region.provider}"
        )
        logger.debug(
            f"Selected instance: {selected_instance.id} ({selected_instance.price_monthly}/mo)"
        )

        if not server:
            # No server in the desired region, create one
            try:
                server = self.create_server(selected_region, selected_instance)
                logger.info(
                    f"Created server in region {region_name} - {region_id} with IP {server.ip_address}"
                )
            except Exception as e:
                raise ValueError(f"Error creating server: {e}")
        else:
            logger.info(
                f"Using existing server in region {region_name} with IP {server.ip_address}"
            )

        # Create a VPN peer on the server
        try:
            vpn_peer = self.add_vpn_peer(server_id=server.id)
            logger.info(f"Added VPN peer: {vpn_peer.peer_name}")
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
            server = server_entry["server"]
            peers = server_entry["peers"]

            # Skip young servers
            server_age = server.created_at.replace(tzinfo=pytz.UTC)
            if server_age > minimum_age_time:
                logger.debug(
                    f"Skipping server {server.ip_address} - too young (age: {current_time - server_age})"
                )
                continue

            ssh_private_key = deserialize_private_key(server.ssh_private_key)

            try:
                # Initialize WireGuardManager for the server
                wireguard_manager = WireGuardManager(
                    hostname=server.ip_address,
                    username=server.username,
                    private_key=ssh_private_key,
                )

                # Get the latest handshakes for all peers on the server
                handshakes = wireguard_manager.get_latest_handshakes()

                if self._should_delete_server(
                    peers, handshakes, activity_threshold_time
                ):
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

        ssh_private_key = deserialize_private_key(server.ssh_private_key)

        # Initialize WireGuardManager for the server
        wireguard_manager = WireGuardManager(
            hostname=server.ip_address,
            username=server.username,
            private_key=ssh_private_key,
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
        ssh_private_key = deserialize_private_key(server.ssh_private_key)
        wireguard_manager = WireGuardManager(
            hostname=server.ip_address, username="root", private_key=ssh_private_key
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
                logger.warn(f"Error deleting VPN peer {peer.peer_name}: {e}")

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

    def _initialize_provider_manager(
        self,
        provider: str,
        project_name: str,
        ssh_public_key: str,
        stack_state: dict[str, Any] | None = None,
    ) -> InfrastructureManager | None:
        """
        Initialize the InfrastructureManager for a given provider.
        :param provider: Provider type ('vultr' or 'linode')
        :param project_name: Name of the project
        :return: An instance of InfrastructureManager or its subclass
        """
        provider = provider.lower()
        if provider == "vultr":
            return VultrManager(
                vultr_api_key=self.provider_credentials["vultr"],
                ssh_public_key=ssh_public_key,
                project_name=project_name,
                stack_state=stack_state,
            )
        elif provider == "linode":
            return LinodeManager(
                linode_api_key=self.provider_credentials["linode"],
                ssh_public_key=ssh_public_key,
                project_name=project_name,
                stack_state=stack_state,
            )
        return None

    def _get_all_providers(self) -> list[CloudProvider]:
        """
        Initialize and return providers that have valid credentials configured
        :return: List of CloudProvider instances
        """
        providers = []
        for provider_name, credentials in self.provider_credentials.items():
            if provider_name in self.SUPPORTED_PROVIDERS and credentials is not None:
                try:
                    provider = CloudProviderFactory.get_provider(
                        provider_name, credentials
                    )
                    if provider:
                        providers.append(provider)
                except ValueError as e:
                    logger.warn(f"Could not initialize {provider_name}: {e}")
        return providers

    def get_available_regions(self) -> list[Region]:
        """
        Retrieve available regions from all configured providers.
        :return: A list of Region objects from all providers
        :raises ValueError: If no providers are available or all API calls fail
        """
        all_regions = []
        errors = []

        for provider in self._get_all_providers():
            try:
                regions = provider.get_regions()
                all_regions.extend(regions)
            except requests.HTTPError as e:
                errors.append(f"{provider.__class__.__name__}: {e}")

        if not all_regions and errors:
            raise ValueError(
                f"Failed to retrieve regions from any provider: {'; '.join(errors)}"
            )

        # Remove duplicates based on city and country
        unique_regions = {}
        for region in all_regions:
            # Extract base city name (remove numbers and extra spaces)
            city = region.city if region.city else ""
            base_city = " ".join(
                word
                for word in city.split()
                if not any(char.isdigit() for char in word)
            )
            base_city = base_city.strip()

            key = (region.country, base_city)

            # If we haven't seen this city before, or if this is the "primary" version
            # (no numbers in name), use this region
            if key not in unique_regions or (
                any(char.isdigit() for char in unique_regions[key].city)
                and not any(char.isdigit() for char in city)
            ):
                unique_regions[key] = region

        return sorted(unique_regions.values(), key=lambda r: (r.country, r.city or ""))

    def search_regions(
        self, search_term: str
    ) -> list[tuple[Region, InstanceType | None]]:
        """
        Search for regions by city or country name/code across all providers,
        including the smallest instance type available in each region.

        :param search_term: The term to search for in city or country
        :return: List of tuples containing (Region, smallest InstanceType or None)
        :raises ValueError: If no providers are available or all API calls fail
        """
        search_term = search_term.lower()
        results = []

        for provider in self._get_all_providers():
            try:
                provider_results = provider.search_smallest(search_term)
                results.extend(provider_results)
            except requests.HTTPError as e:
                logger.warn(f"Failed to search {provider.__class__.__name__}: {e}")

        # Sort results by instance price (if available), then location
        return sorted(
            results,
            key=lambda x: (
                x[1].price_monthly if x[1] else float("inf"),
                x[0].country,
                x[0].city or "",
            ),
        )

    # ----------------- Additional Methods ----------------- #

    def list_servers_with_peers(self) -> list[dict]:
        """
        List servers along with their associated VPN peers.
        :return: List of dictionaries containing server and its peers.
        """
        return self.data_layer.list_servers_with_peers()
