from typing import Dict, Any
from datetime import datetime
import threading
from .app import App
from .utils import setup_logger

logger = setup_logger(name="core.vpn_monitor")

class VPNStateManager:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance.last_check_time = None
                    cls._instance.last_status = None
                    logger.info("Created new VPNStateManager instance")
        return cls._instance
    
    def update_status(self, status: Dict[str, Any], check_time: datetime):
        with self._lock:
            self.last_status = status
            self.last_check_time = check_time
            logger.debug(f"Updated VPN status at {check_time}")
    
    def get_status(self) -> tuple[Dict[str, Any], datetime]:
        with self._lock:
            logger.debug("Retrieved VPN status")
            return self.last_status, self.last_check_time

class VPNMonitor:
    def __init__(self, app_instance: App):
        """
        Initialize VPN monitor.
        
        Args:
            app_instance: The main application instance that provides VPN functionality
        """
        self.app_instance = app_instance
        self.last_status: Dict[str, Any] = {}
        logger.info("Initialized VPNMonitor")
        
    def check_vpn_status(self) -> Dict[str, Any]:
        """
        Check VPN status and return results.
        
        Returns:
            Dict containing status information
        """
        try:
            # Clear unused servers based on inactivity threshold
            self.app_instance.clear_unused_servers()
            logger.info("Cleared unused servers based on inactivity criteria")

            # Get current status
            servers_with_peers = self.app_instance.list_servers_with_peers()
            logger.debug(f"Retrieved {len(servers_with_peers)} servers with peers")
            
            # Process status information
            active_peers = 0
            server_statuses = []
            
            for server in servers_with_peers:
                peers_count = len(server['peers'])
                active_peers += peers_count
                
                server_statuses.append({
                    'location': server['server'].location,
                    'ip_address': server['server'].ip_address,
                    'peers_count': peers_count,
                })
                logger.debug(f"Processed server {server['server'].location} with {peers_count} peers")
            
            # Create status summary
            status = {
                'timestamp': datetime.now(),
                'active_peers': active_peers,
                'server_count': len(servers_with_peers),
                'server_statuses': server_statuses,
            }
            
            self.last_status = status

            # Update the VPNStateManager directly
            VPNStateManager().update_status(status, status['timestamp'])
            logger.info(f"VPN status updated: {active_peers} active peers across {len(servers_with_peers)} servers")

            return status
            
        except Exception as e:
            error_msg = f"Error checking VPN status: {str(e)}"
            logger.error(error_msg, exc_info=True)

            error_status = {
                'timestamp': datetime.now(),
                'error': str(e),
                'active_peers': 0,
                'server_count': 0,
                'server_statuses': []
            }
            self.last_status = error_status

            # Update the VPNStateManager with the error status
            VPNStateManager().update_status(error_status, error_status['timestamp'])

            return error_status

