from datetime import timedelta
import streamlit as st
import atexit
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
from auto_vpn.core.app import App
from auto_vpn.core.periodic_task import PeriodicTask
from auto_vpn.core.vpn_monitor import VPNMonitor, VPNStateManager

# Load config file
config = yaml.load(st.secrets['authentication']['credentials'], Loader=SafeLoader)

st.set_page_config(
    page_title="VPN Peer Manager",
    page_icon="🔒",
    layout="wide"
)

# Create an authentication object
authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days'],
    auto_hash=True
)

# Initialize state manager
vpn_state_manager = VPNStateManager()

# Initialize session state
if 'app_instance' not in st.session_state:
    # Get API keys from secrets
    vultr_api_key = st.secrets.get("vultr_api_key", None)
    linode_api_key = st.secrets.get("linode_api_key", None)
 
    if not any([vultr_api_key, linode_api_key]):
        st.error("⚠️ No provider API keys configured. Please set at least one provider API key in .streamlit/secrets.toml")
        st.stop()
  
    st.session_state.app_instance = App(
        vultr_api_key=vultr_api_key,
        linode_api_key=linode_api_key
    )
if 'vpn_peers' not in st.session_state:
    st.session_state.vpn_peers = []

def get_available_locations():
    """Cache available locations to improve performance"""
    @st.cache_data(ttl=3600)
    def _fetch_locations():
        # Get first available provider from configured providers
        available_providers = [
            provider for provider, api_key in st.session_state.app_instance.provider_credentials.items() 
            if api_key is not None
        ]
        
        if not available_providers:
            st.error("No providers configured with valid API keys")
            st.stop()
            
        provider = available_providers[0]
        regions = st.session_state.app_instance.get_available_regions(provider=provider)
        return [f"{region['city']}, {region['country']}" for region in regions]    

    return _fetch_locations()

def refresh_peers():
    """Refresh the list of VPN peers"""
    servers_with_peers = st.session_state.app_instance.list_servers_with_peers()
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
    st.session_state.vpn_peers = peers_data

def create_vpn_peer(location: str):
    """Create a new VPN peer and download config"""
    try:
        with st.spinner('Creating VPN peer...'):
            vpn_peer = st.session_state.app_instance.vpn_peer_quick(location)
            refresh_peers()
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

def delete_peer(peer_id: int):
    """Delete a VPN peer"""
    try:
        with st.spinner('Deleting VPN peer...'):
            st.session_state.app_instance.delete_vpn_peer(peer_id)
            refresh_peers()
            st.rerun()
    except Exception as e:
        st.error(f"Error deleting VPN peer: {e}")

def display_status_sidebar():
    """Display VPN status information in the sidebar"""
    st.sidebar.subheader("VPN Status")

    # Add monitoring status indicator
    if 'periodic_task' in st.session_state and st.session_state.periodic_task.running:
        st.sidebar.success("Monitoring: Active")
    else:
        st.sidebar.error("Monitoring: Inactive")

    # Add inactivity threshold settings
    st.sidebar.subheader("Settings")
    
    # Define threshold options
    threshold_options = {
        "30 minutes": timedelta(minutes=30),
        "1 hour": timedelta(hours=1),
        "2 hours": timedelta(hours=2),
        "4 hours": timedelta(hours=4)
    }
    
    # Get current threshold and find its label
    current_threshold = st.session_state.app_instance.get_inactivity_threshold()
    current_minutes = int(current_threshold.total_seconds() / 60)
    current_label = next(
        (label for label, td in threshold_options.items() 
         if td.total_seconds() == current_threshold.total_seconds()),
        "Custom"
    )
    
    st.sidebar.write("Inactivity threshold:")
    
    # Create columns for buttons
    col1, col2 = st.sidebar.columns(2)
    
    # Function to handle button click
    def change_threshold(new_threshold_label):
        new_threshold = threshold_options[new_threshold_label]
        st.session_state.app_instance.set_inactivity_threshold(new_threshold)
        st.session_state.custom_minutes = int(new_threshold.total_seconds() / 60)
        st.session_state.threshold_changed = True

    # Create buttons for each threshold option
    for idx, (label, threshold) in enumerate(threshold_options.items()):
        if idx % 2 == 0:
            button_col = col1
        else:
            button_col = col2
            
        button_style = "primary" if label == current_label else "secondary"
        button_col.button(
            label,
            key=f"threshold_{label}",
            type=button_style,
            on_click=change_threshold,
            args=(label,),
            use_container_width=True
        )

    # Add custom time input
    st.sidebar.write("Or set custom time:")
    
    # Initialize custom minutes in session state if not present
    if 'custom_minutes' not in st.session_state:
        st.session_state.custom_minutes = current_minutes

    # Function to handle custom time change
    def custom_time_changed():
        new_threshold = timedelta(minutes=st.session_state.custom_minutes)
        st.session_state.app_instance.set_inactivity_threshold(new_threshold)
        st.session_state.threshold_changed = True

    custom_minutes = st.sidebar.number_input(
        "Minutes",
        min_value=1,
        max_value=1440,  # 24 hours
        value=st.session_state.custom_minutes,
        step=5,
        key="custom_minutes",
        help="Set custom inactivity threshold (1-1440 minutes)",
        on_change=custom_time_changed,
        label_visibility="collapsed"
    )

    # Check if threshold was changed and trigger rerun
    if 'threshold_changed' in st.session_state and st.session_state.threshold_changed:
        del st.session_state.threshold_changed
        st.rerun()

    st.sidebar.divider()

    status, last_check_time = vpn_state_manager.get_status()

    if last_check_time:
        st.sidebar.info(f"Last check: {last_check_time.strftime('%Y-%m-%d %H:%M:%S')}")

    if status:
        st.sidebar.metric("Active Peers", status.get('active_peers', 0))
        st.sidebar.metric("Active Servers", status.get('server_count', 0))

        if 'error' in status:
            st.sidebar.error(f"Last check error: {status['error']}")

def main():
    # Authentication
    try:
        authenticator.login(location='main', key='Login')
    except Exception as e:
        st.error(e)
        st.stop()

    if st.session_state["authentication_status"] is False:
        st.error('Username/password is incorrect')
        st.stop()
    elif st.session_state["authentication_status"] is None:
        st.warning('Please enter your username and password')
        st.stop()

    # If we get here, user is authenticated
    with st.sidebar:
        authenticator.logout()
        st.write(f'Welcome *{st.session_state["name"]}*')
        st.divider()

    # Initialize VPN monitor and periodic task if not already initialized
    if 'vpn_monitor' not in st.session_state:
        st.session_state.vpn_monitor = VPNMonitor(st.session_state.app_instance)
        
    # Only create periodic task if it doesn't exist or if it's not running
    if ('periodic_task' not in st.session_state or 
        not st.session_state.periodic_task.running):
        monitor = st.session_state.vpn_monitor
        periodic_task = PeriodicTask(
            interval_seconds=60 * 10,
            task_function=monitor.check_vpn_status,
        )
        st.session_state.periodic_task = periodic_task
        periodic_task.start()

    st.title("🌍 VPN Peer Manager")

    # Display status in sidebar
    display_status_sidebar()

    # Create new VPN peer section
    locations = get_available_locations()
    container = st.container()
    with container:
        selected_location = st.selectbox(
            "Select location",
            locations,
            index=None,
            placeholder="Choose a location...",
            label_visibility="collapsed"
        )
        st.button(
            "Create VPN",
            type="primary",
            disabled=not selected_location,
            key="create_vpn_button",
            on_click=lambda: create_vpn_peer(selected_location.split(',')[0].strip()) if selected_location else None
        )
    # Display existing peers
    st.subheader("Existing VPN Peers")
    refresh_peers()
    
    if not st.session_state.vpn_peers:
        st.info("No VPN peers available. Create one above!")
    else:
        for peer in st.session_state.vpn_peers:
            with st.container():
                cols = st.columns([3, 2, 1])
                with cols[0]:
                    st.write(f"**{peer['peer_name']}**")
                    st.write(f"🌍 {peer['location']} | 🖥️ {peer['ip_address']}")
                with cols[1]:
                    st.download_button(
                        "📥 Config",
                        data=peer['config'],
                        file_name=f"{peer['peer_name']}.conf",
                        mime="text/plain",
                        key=f"download_{peer['peer_id']}",
                        use_container_width=True
                    )
                with cols[2]:
                    if st.button(
                        "🗑️ Delete",
                        key=f"delete_{peer['peer_id']}",
                        use_container_width=True
                    ):
                        delete_peer(peer['peer_id'])
                st.divider()

def cleanup():
    """Cleanup function to stop periodic task"""
    if 'periodic_task' in st.session_state:
        st.session_state.periodic_task.stop()

# Register cleanup handler
atexit.register(cleanup)

if __name__ == "__main__":
    main()
