import pytest
from datetime import datetime

from auto_vpn.db.repository import Repository

class TestRepository:
    def test_create_and_list_servers(self, repository: Repository):
        # Create servers
        server1 = repository.create_server(
            provider='linode',
            project_name='Project A',
            ip_address='192.168.1.1',
            username='user1',
            ssh_private_key='key1',
            ssh_public_key='pubkey1',
            location='us-west-1',
            server_type='g6-nanode-1'
        )

        server2 = repository.create_server(
            provider='linode',
            project_name='Project B',
            ip_address='192.168.1.2',
            username='user2',
            ssh_private_key='key2',
            ssh_public_key='pubkey2',
            location='us-west-2',
            server_type='g6-standard-1'
        )

        # List all servers
        servers = repository.list_servers()
        assert len(servers) == 2
        assert {s.id for s in servers} == {server1.id, server2.id}

        # List servers for the specific provider
        provider_servers = repository.list_servers(provider='linode')
        assert len(provider_servers) == 2

    def test_server_created_at(self, repository: Repository):
        # Create a server
        server = repository.create_server(
            provider='vultr',
            project_name='Project Timestamp',
            ip_address='10.10.10.10',
            username='timestamp_user',
            ssh_private_key='timestamp_priv',
            ssh_public_key='timestamp_pub',
            location='eu-central',
            server_type='vc2-1c-1gb'
        )

        # Retrieve the server
        retrieved_server = repository.get_server_by_id(server.id)
        assert isinstance(retrieved_server.created_at, datetime)
        assert str(retrieved_server.created_at.tzinfo) == 'UTC'

    def test_delete_server_cascades_peers(self, repository: Repository):
        # Create a server
        server = repository.create_server(
            provider='aws',
            project_name='Cascade Project',
            ip_address='172.16.0.1',
            username='cascade_user',
            ssh_private_key='cascade_priv',
            ssh_public_key='cascade_pub',
            location='ap-southeast',
            server_type='t3.small'
        )

        # Create VPN peers
        peer1 = repository.create_peer(
            server_id=server.id,
            peer_name='Peer1',
            public_key='peer1_pub',
            wireguard_config='peer1_config'
        )
        peer2 = repository.create_peer(
            server_id=server.id,
            peer_name='Peer2',
            public_key='peer2_pub',
            wireguard_config='peer2_config'
        )

        # Ensure peers are created
        peers = repository.list_peers()
        assert len(peers) == 2

        # Delete the server
        repository.delete_server(server.id)

        # Ensure the server is deleted
        with pytest.raises(ValueError):
            repository.get_server_by_id(server.id)

        # Ensure peers are deleted
        peers_after = repository.list_peers()
        assert len(peers_after) == 0

    def test_delete_last_peer_deletes_server(self, repository: Repository):
        # Create a server
        server = repository.create_server(
            provider='linode',
            project_name='Last Peer Project',
            ip_address='192.168.100.1',
            username='last_peer_user',
            ssh_private_key='last_peer_priv',
            ssh_public_key='last_peer_pub',
            location='us-central',
            server_type='g6-standard-2'
        )

        # Create a single VPN peer
        peer = repository.create_peer(
            server_id=server.id,
            peer_name='SoloPeer',
            public_key='solo_pub',
            wireguard_config='solo_config'
        )

        # Ensure the peer is created
        peers = repository.list_peers()
        assert len(peers) == 1

        # Delete the peer
        repository.delete_peer(peer.id)

        # Ensure the peer is deleted
        with pytest.raises(ValueError):
            repository.get_peer_by_id(peer.id)

        repository.delete_server(server.id)

    def test_vpn_peer_created_at(self, repository: Repository):
        # Create a server
        server = repository.create_server(
            provider='aws',
            project_name='Peer Timestamp Project',
            ip_address='10.0.0.2',
            username='peer_timestamp_user',
            ssh_private_key='peer_timestamp_priv',
            ssh_public_key='peer_timestamp_pub',
            location='sa-east',
            server_type='t3.medium'
        )

        # Create a VPN peer
        peer = repository.create_peer(
            server_id=server.id,
            peer_name='TimestampPeer',
            public_key='timestamp_peer_pub',
            wireguard_config='timestamp_peer_config'
        )

        # Retrieve the peer
        retrieved_peer = repository.get_peer_by_id(peer.id)
        assert isinstance(retrieved_peer.created_at, datetime)
        assert retrieved_peer.created_at.tzinfo is not None
        assert str(retrieved_peer.created_at.tzinfo) == 'UTC'

    def test_wireguard_config_retrieval(self, repository: Repository):
        # Create a server
        server = repository.create_server(
            provider='vultr',
            project_name='WG Config Project',
            ip_address='10.10.10.11',
            username='wg_user',
            ssh_private_key='wg_priv',
            ssh_public_key='wg_pub',
            location='us-west',
            server_type='vc2-2c-4gb'
        )

        # Create a VPN peer
        peer = repository.create_peer(
            server_id=server.id,
            peer_name='WGPeer',
            public_key='wg_peer_pub',
            wireguard_config='wg_peer_config'
        )

        # Retrieve WireGuard config
        wg_config = repository.get_wireguard_config(peer.id)
        assert wg_config == 'wg_peer_config'

    def test_prevent_duplicate_vpn_peer_names(self, repository: Repository):
        # Create a server
        server = repository.create_server(
            provider='aws',
            project_name='Duplicate Peer Project',
            ip_address='10.0.0.3',
            username='duplicate_peer_user',
            ssh_private_key='dup_peer_priv',
            ssh_public_key='dup_peer_pub',
            location='eu-west',
            server_type='t3.large'
        )

        # Create a VPN peer
        repository.create_peer(
            server_id=server.id,
            peer_name='DuplicatePeer',
            public_key='dup_peer_pub1',
            wireguard_config='dup_peer_config1'
        )

        # Attempt to create another VPN peer with the same name on the same server
        with pytest.raises(ValueError) as exc_info:
            repository.create_peer(
                server_id=server.id,
                peer_name='DuplicatePeer',
                public_key='dup_peer_pub2',
                wireguard_config='dup_peer_config2'
            )
        assert "already exists for this server" in str(exc_info.value)

    def test_list_servers_with_peers(self, repository: Repository):
        # Create servers
        server1 = repository.create_server(
            provider='linode',
            project_name='List Project 1',
            ip_address='192.168.50.1',
            username='list_user1',
            ssh_private_key='list_priv1',
            ssh_public_key='list_pub1',
            location='us-east-2',
            server_type='g6-nanode-1'
        )

        server2 = repository.create_server(
            provider='linode',
            project_name='List Project 2',
            ip_address='192.168.50.2',
            username='list_user2',
            ssh_private_key='list_priv2',
            ssh_public_key='list_pub2',
            location='us-west-2',
            server_type='g6-standard-1'
        )

        # Create VPN peers
        peer1 = repository.create_peer(
            server_id=server1.id,
            peer_name='ListPeer1',
            public_key='list_peer1_pub',
            wireguard_config='list_peer1_config'
        )

        peer2 = repository.create_peer(
            server_id=server1.id,
            peer_name='ListPeer2',
            public_key='list_peer2_pub',
            wireguard_config='list_peer2_config'
        )

        # List servers with peers
        servers_with_peers = repository.list_servers_with_peers()
        assert len(servers_with_peers) == 2

        # Verify server1 has 2 peers
        server1_info = next(item for item in servers_with_peers if item['server'].id == server1.id)
        assert len(server1_info['peers']) == 2

        # Verify server2 has no peers
        server2_info = next(item for item in servers_with_peers if item['server'].id == server2.id)
        assert len(server2_info['peers']) == 0

    def test_reuse_ip_address_not_allowed(self, repository: Repository):
        # Create a server with a specific IP
        server1 = repository.create_server(
            provider='aws',
            project_name='IP Test Project1',
            ip_address='203.0.113.1',
            username='ip_user1',
            ssh_private_key='ip_priv1',
            ssh_public_key='ip_pub1',
            location='us-west',
            server_type='t3.micro'
        )

        # Attempt to create another server with the same IP
        with pytest.raises(ValueError) as exc_info:
            repository.create_server(
                provider='aws',
                project_name='IP Test Project2',
                ip_address='203.0.113.1',  # Duplicate IP
                username='ip_user2',
                ssh_private_key='ip_priv2',
                ssh_public_key='ip_pub2',
                location='us-east',
                server_type='t3.small'
            )
        assert "already exists" in str(exc_info.value)

    def test_delete_peer_individual(self, repository: Repository):
        # Create a server
        server = repository.create_server(
            provider='aws',
            project_name='Delete Peer Project',
            ip_address='10.0.5.1',
            username='delete_peer_user',
            ssh_private_key='delete_peer_priv',
            ssh_public_key='delete_peer_pub',
            location='us-central',
            server_type='t3.medium'
        )

        # Create two VPN peers
        peer1 = repository.create_peer(
            server_id=server.id,
            peer_name='DeletePeer1',
            public_key='del_peer1_pub',
            wireguard_config='del_peer1_config'
        )
        peer2 = repository.create_peer(
            server_id=server.id,
            peer_name='DeletePeer2',
            public_key='del_peer2_pub',
            wireguard_config='del_peer2_config'
        )

        # Delete one peer
        repository.delete_peer(peer1.id)

        # Ensure peer1 is deleted and peer2 exists
        with pytest.raises(ValueError):
            repository.get_peer_by_id(peer1.id)
        existing_peer = repository.get_peer_by_id(peer2.id)
        assert existing_peer.peer_name == 'DeletePeer2'

        # Ensure the server still exists
        existing_server = repository.get_server_by_id(server.id)
        assert existing_server.id == server.id

    def test_wireguard_config_is_stored_correctly(self, repository: Repository):
        """
        Ensure that the wireguard_config is stored and retrieved correctly.
        """
        # Create a server
        server = repository.create_server(
            provider='aws',
            project_name='WG Config Project',
            ip_address='10.0.8.1',
            username='wg_config_user',
            ssh_private_key='wg_config_priv',
            ssh_public_key='wg_config_pub',
            location='us-west-2',
            server_type='t3.2xlarge'
        )

        # WireGuard configuration
        wg_config = """
        [Interface]
        PrivateKey = someprivatekey
        Address = 10.0.0.2/24
        ListenPort = 51820

        [Peer]
        PublicKey = peerpublickey
        Endpoint = peer.endpoint.com:51820
        AllowedIPs = 0.0.0.0/0
        """

        # Create a VPN peer with the WireGuard config
        peer = repository.create_peer(
            server_id=server.id,
            peer_name='WGConfigPeer',
            public_key='wg_config_peer_pub',
            wireguard_config=wg_config.strip()
        )

        # Retrieve the WireGuard config
        retrieved_wg_config = repository.get_wireguard_config(peer.id)
        assert retrieved_wg_config == wg_config.strip()
