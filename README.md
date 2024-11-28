# WireGuard VPN Server Deployer and Manager
## Overview

This project aims to develop an open-source tool for deploying and managing WireGuard VPN servers across multiple cloud providers. The tool will provide a seamless way to:

- Deploy Servers: Create server instances on cloud providers like Vultr and Linode using Pulumi.
- Install WireGuard: Install and configure WireGuard on these servers using SSH-based management and scripts like wireguard-install.
- Manage Users: Create, manage, and delete VPN users on the deployed servers.
- Download Configurations: Provide WireGuard configuration files for each user-server pair.
- User Interfaces: Offer both a command-line interface (CLI) using Typer and a graphical interface using Streamlit.
- Data Storage: Store server and user information in an SQLite database for persistence.


