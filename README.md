# Auto-VPN: On-Demand WireGuard VPN Server Manager 
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://opensource.org/licenses/MIT)

Deploy your personal WireGuard VPN server with just a few clicks. No subscriptions, no complexity, full control.

![Main interface](images/main.png)

This project provides an effortless way to spin up your own temporary, cost-effective WireGuard VPN servers on-demand—no long-term subscriptions or complex manual setups required. By leveraging popular VPS providers like Vultr or Linode, it automatically:

## 🚀 Features

- **On-Demand Deployment**: Launch VPN servers instantly on Vultr or Linode
- **Cost-Effective**: Pay only for actual usage with automatic server cleanup
- **User-Friendly Interface**: Simple GUI for server and profile management
- **Enhanced Privacy**: Full control over your VPN infrastructure
- **Automated Setup**: Pre-configured WireGuard installation
- **Multi-Provider Support**: Works with major VPS providers (Vultr, Linode)

## 🏃‍♂️ Quick Start

### Local Deployment (Docker)

1. Run the container:
```bash
docker run --rm -d --pull always --name auto-vpn \
  -e USERNAME=admin \
  -e PASSWORD=qwerty \
  -e VULTR_API_KEY=<your-vultr-api-key> \
  -v $(pwd)/data_layer:/app/data_layer \
  -p 8501:8501 \
  ghcr.io/g1ibby/auto-vpn
```

2. Access the interface at `http://localhost:8501`

### Free Cloud Deployment (Render.com)

1. **Create New Web Service**
   - Sign in to [Render Dashboard](https://dashboard.render.com)
   - Choose "New Web Service"
   - Select Docker runtime
   - Use image: `ghcr.io/g1ibby/auto-vpn`

2. **Configure Environment Variables**
   
   Required:
   - `USERNAME`: Admin username
   - `PASSWORD`: Admin password
   - `VULTR_API_KEY` or `LINODE_API_KEY`: VPS provider API key
   - `SELF_URL`: Your Render service URL (e.g., https://your-service.onrender.com)

  Database Configuration:
   - `DATABASE_URL`: Database connection string (see details below)

3. **Deploy and Access**
   - Service will be available at your Render URL
   - Auto-ping feature keeps the service active on free tier

### ⚠️ Important Database Considerations

The application supports two database types:

1. **SQLite** (default):
`DATABASE_URL=sqlite:///data_layer/data_layer.db`

⚠️ **WARNING**: Using SQLite on Render's free tier is NOT recommended as:
- Database will be lost on service restarts
- Data doesn't persist between deployments
- Free tier instances can restart randomly

2. **PostgreSQL** (recommended for Render):
`DATABASE_URL=postgresql://user:password@host:5432/database`

✅ **Recommended**: Use external PostgreSQL service:
- [Supabase](https://supabase.com) offers free PostgreSQL databases
- Data persists across deployments and restarts
- More reliable for production use

## 💻 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| USERNAME | Yes | Admin login username |
| PASSWORD | Yes | Admin login password |
| VULTR_API_KEY | * | Vultr API key |
| LINODE_API_KEY | * | Linode API key |
| SELF_URL | No | Service URL for auto-ping |
| DATABASE_URL | No | Database connection string |

\* Either VULTR_API_KEY or LINODE_API_KEY is required

## 🏗️ Architecture

![Flowchart](images/flowchart.png)

The project leverages several powerful technologies:

- **Pulumi**: Infrastructure as Code for VPS management
- **WireGuard**: Secure VPN protocol
- **Streamlit**: Modern web interface
- **Docker**: Containerization and easy deployment

## 🔒 Security Considerations

- All VPN traffic is encrypted using WireGuard
- No logs are kept on VPN servers
- Servers are automatically destroyed after inactivity
- Full control over infrastructure eliminates third-party trust

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 🗺️ Roadmap

### New Cloud Providers
- [ ] DigitalOcean
- [ ] Hetzner
- [ ] AWS

### Enhanced User Experience
- [ ] QR code generation for WireGuard peers
  - Easy mobile device configuration
  - One-click peer sharing

## 🙏 Acknowledgments

- Pulumi: Handles infrastructure provisioning, making it simple to deploy and tear down VPS instances on-demand.
- [Nyr/wireguard-install](https://github.com/Nyr/wireguard-install): Automates the WireGuard installation process, ensuring a seamless setup experience.
- [Streamlit](https://streamlit.io): GUI
