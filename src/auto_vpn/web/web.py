import streamlit as st
import os
import atexit
from datetime import timedelta
import requests
from typing import Optional
from auto_vpn.core.app import App
from auto_vpn.core.periodic_task import PeriodicTask
from auto_vpn.core.vpn_monitor import VPNMonitor, VPNStateManager
from auto_vpn.core.utils import setup_logger
from auto_vpn.core.settings import Settings
from auto_vpn.web.auth_manager import AuthManager
from auto_vpn.web.vpn_manager import VPNManager

logger = setup_logger(name="web")

class VPNApplication:
    """Main application class"""

    THRESHOLD_OPTIONS = {
        "30 minutes": timedelta(minutes=30),
        "1 hour": timedelta(hours=1),
        "2 hours": timedelta(hours=2),
        "4 hours": timedelta(hours=4)
    }
    
    def __init__(self):
        st.set_page_config(
            page_title="VPN Manager",
            page_icon="🔒",
            layout="wide"
        )
        self.settings: Settings = self._init_settings()
        self.auth_manager: AuthManager = AuthManager(self.settings)
        self.vpn_state_manager: VPNStateManager = VPNStateManager()
        self._init_session_state()
        
    def _init_settings(self) -> Settings:
        """Initialize application settings"""
        try:
            settings = Settings()
            settings.validate_api_keys()
            return settings
        except Exception as e:
            logger.error("Configuration Error: Missing or invalid environment variables")
            for error in e.errors():
                field = error["loc"][0]
                message = error["msg"]
                logger.error(f"{field}: {message}")
            os._exit(1)
    
    def _init_session_state(self):
        """Initialize session state variables"""
        if 'app_instance' not in st.session_state:
            st.session_state.app_instance = App(
                db_url=self.settings.DATABASE_URL,
                vultr_api_key=self.settings.VULTR_API_KEY,
                linode_api_key=self.settings.LINODE_API_KEY
            )
            
        if 'vpn_manager' not in st.session_state:
            st.session_state.vpn_manager = VPNManager(st.session_state.app_instance)
            
        if 'vpn_peers' not in st.session_state:
            st.session_state.vpn_peers = []
    
    def _init_monitoring(self):
        """Initialize VPN monitoring"""
        if 'vpn_monitor' not in st.session_state:
            st.session_state.vpn_monitor = VPNMonitor(st.session_state.app_instance)
            
        if ('periodic_task' not in st.session_state or 
            not st.session_state.periodic_task.running):
            monitor = st.session_state.vpn_monitor
            periodic_task = PeriodicTask(
                interval_seconds=60 * 10,
                task_function=monitor.check_vpn_status,
            )
            st.session_state.periodic_task = periodic_task
            periodic_task.start()
    
    def _init_self_ping(self):
        """Initialize self-ping task if configured"""
        if not self.settings.SELF_URL:
            return
            
        if ('periodic_task_ping' not in st.session_state or 
            not st.session_state.periodic_task_ping.running):
            
            def ping_self():
                try:
                    response = requests.get(self.settings.SELF_URL, timeout=10)
                    logger.info(f"Self-ping completed with status {response.status_code}")
                    return response.status_code
                except Exception as e:
                    logger.warn(f"Self-ping failed: {str(e)}")
                    return None

            periodic_task_ping = PeriodicTask(
                interval_seconds=60 * 10,
                task_function=ping_self,
            )
            st.session_state.periodic_task_ping = periodic_task_ping
            periodic_task_ping.start()

    def run(self):
        """Run the application"""

        # Handle authentication
        self.auth_manager.authenticator.login(location='main', key='Login')
        
        if st.session_state["authentication_status"] is False:
            st.error('Username/password is incorrect')
            st.stop()
        elif st.session_state["authentication_status"] is None:
            st.warning('Please enter your username and password')
            st.stop()

        # Initialize monitoring and self-ping
        self._init_monitoring()
        self._init_self_ping()

        # Display authenticated interface
        self._render_authenticated_interface()
    
    def _render_authenticated_interface(self):
        """Render the main interface for authenticated users"""
        with st.sidebar:
            self.auth_manager.authenticator.logout()
            st.divider()
            self._render_threshold_settings()

        st.title("🌍 VPN Manager")
        
        # Create new VPN peer section
        self._render_vpn_creation()
        
        # Display existing peers
        self._render_existing_peers()

    def _render_existing_peers(self):
        """Render the list of existing VPN peers"""
        st.subheader("Existing VPN Peers")
        
        # Refresh peers list
        st.session_state.vpn_peers = st.session_state.vpn_manager.refresh_peers()
        
        if not st.session_state.vpn_peers:
            st.info("No VPN peers available. Create one above! 👆")
            return

        self._render_peer_list()

    def _render_peer_list(self):
        """Render the list of peers with their details and actions"""
        for peer in st.session_state.vpn_peers:
            self._render_peer_card(peer)

    def _render_peer_card(self, peer: dict):
        """Render a single peer card with its details and actions"""
        with st.container():
            cols = st.columns([3, 2, 1])
            with cols[0]:
                self._render_peer_details(peer)
            with cols[1]:
                self._render_config_download(peer)
            with cols[2]:
                self._render_delete_button(peer)
            st.divider()

    def _render_peer_details(self, peer: dict):
        """Render peer details (name, location, IP)"""
        st.write(f"**{peer['peer_name']}**")
        st.write(f"🌍 {peer['location']} | 🖥️ {peer['ip_address']}")

    def _render_config_download(self, peer: dict):
        """Render config download button"""
        st.download_button(
            "📥 Config",
            data=peer['config'],
            file_name=f"{peer['peer_name']}.conf",
            mime="text/plain",
            key=f"download_{peer['peer_id']}",
            use_container_width=True
        )

    def _render_delete_button(self, peer: dict):
        """Render delete button with confirmation"""
        if st.button(
            "🗑️ Delete",
            key=f"delete_{peer['peer_id']}",
            use_container_width=True
        ):
            try:
                with st.spinner('Deleting VPN peer...'):
                    st.session_state.vpn_manager.delete_peer(peer['peer_id'])
                    st.success("Peer deleted successfully!")
                    st.rerun()
            except Exception as e:
                st.error(f"Error deleting peer: {str(e)}")
    
    def _get_current_threshold_info(self):
        """Get current threshold information"""
        current_threshold = st.session_state.app_instance.get_inactivity_threshold()
        current_minutes = int(current_threshold.total_seconds() / 60)
        current_label = next(
            (label for label, td in self.THRESHOLD_OPTIONS.items() 
             if td.total_seconds() == current_threshold.total_seconds()),
            "Custom"
        )
        return current_threshold, current_minutes, current_label

    def _handle_threshold_change(self, new_threshold_label: str):
        """Handle threshold change from button click"""
        new_threshold = self.THRESHOLD_OPTIONS[new_threshold_label]
        st.session_state.app_instance.set_inactivity_threshold(new_threshold)
        st.session_state.custom_minutes = int(new_threshold.total_seconds() / 60)
        st.session_state.threshold_changed = True

    def _handle_custom_threshold_change(self):
        """Handle custom threshold change"""
        if 'custom_minutes' in st.session_state:
            new_threshold = timedelta(minutes=st.session_state.custom_minutes)
            st.session_state.app_instance.set_inactivity_threshold(new_threshold)
            st.session_state.threshold_changed = True

    def _render_threshold_buttons(self, current_label: str):
        """Render threshold selection buttons"""
        col1, col2 = st.sidebar.columns(2)
        
        for idx, (label, _) in enumerate(self.THRESHOLD_OPTIONS.items()):
            button_col = col1 if idx % 2 == 0 else col2
            button_style = "primary" if label == current_label else "secondary"
            button_col.button(
                label,
                key=f"threshold_{label}",
                type=button_style,
                on_click=self._handle_threshold_change,
                args=(label,),
                use_container_width=True
            )

    def _render_custom_threshold_input(self, current_minutes: int):
        """Render custom threshold input"""
        st.sidebar.write("Or set custom time:")
        
        if 'custom_minutes' not in st.session_state:
            st.session_state.custom_minutes = current_minutes

        st.sidebar.number_input(
            "Minutes",
            min_value=1,
            max_value=1440,  # 24 hours
            step=5,
            key="custom_minutes",
            help="Set custom inactivity threshold (1-1440 minutes)",
            on_change=self._handle_custom_threshold_change,
            label_visibility="collapsed"
        )

    def _render_threshold_settings(self):
        """Render threshold settings section"""
        st.sidebar.subheader("Settings")
        st.sidebar.write("Inactivity threshold:")
        
        _, current_minutes, current_label = self._get_current_threshold_info()
        
        self._render_threshold_buttons(current_label)
        self._render_custom_threshold_input(current_minutes)
        
        if 'threshold_changed' in st.session_state and st.session_state.threshold_changed:
            del st.session_state.threshold_changed
            st.rerun()

    def _render_vpn_creation(self):
        """Render the VPN creation section"""
        locations = st.session_state.vpn_manager.get_available_locations()
        container = st.container()
        with container:
            selected_location = st.selectbox(
                "Select location",
                locations,
                index=None,
                placeholder="Choose a location...",
                label_visibility="collapsed"
            )
            if st.button(
                "Create VPN",
                type="primary",
                disabled=not selected_location,
                key="create_vpn_button"
            ):
                self._handle_vpn_creation(selected_location)
    
    def _handle_vpn_creation(self, location: str):
        """Handle VPN peer creation"""
        try:
            with st.spinner('Creating VPN peer...'):
                location_city = location.split(',')[0].strip()
                vpn_peer = st.session_state.vpn_manager.create_vpn_peer(location_city)
                st.session_state.vpn_peers = st.session_state.vpn_manager.refresh_peers()
                st.success(f"VPN peer created successfully in {location}!")
                st.download_button(
                    label="📥 Download WireGuard Configuration",
                    data=vpn_peer.wireguard_config,
                    file_name=f"{vpn_peer.peer_name}.conf",
                    mime="text/plain",
                    key=f"download_{vpn_peer.peer_name}"
                )
        except Exception as e:
            st.error(f"Error creating VPN peer: {e}")

def cleanup():
    """Cleanup function to stop periodic tasks"""
    if 'periodic_task' in st.session_state:
        st.session_state.periodic_task.stop()
    if 'periodic_task_ping' in st.session_state:
        st.session_state.periodic_task_ping.stop()

# Register cleanup handler
atexit.register(cleanup)

if __name__ == "__main__":
    app = VPNApplication()
    app.run()
