#!/bin/sh
set -e

# Define the path to the secrets file
SECRETS_FILE=/app/.streamlit/secrets.toml

# Function to log messages
log() {
    echo "[ENTRYPOINT] $1"
}

# Check if secrets.toml already exists
if [ -f "$SECRETS_FILE" ]; then
    log "secrets.toml already exists. Skipping generation."
else
    log "secrets.toml not found. Generating from environment variables."

    # List of required environment variables (space-separated)
    REQUIRED_VARS="VULTR_API_KEY USERNAME PASSWORD"

    # Check if all required environment variables are set
    for var in $REQUIRED_VARS; do
        eval "value=\$$var"
        if [ -z "$value" ]; then
            echo "[ERROR] Environment variable '$var' is not set. Exiting."
            exit 1
        fi
    done

    # Generate the secrets.toml file
    cat <<EOF > "$SECRETS_FILE"
vultr_api_key = "${VULTR_API_KEY}"
#linode_api_key = ""

[authentication]
credentials = """
credentials:
  usernames:
    ${USERNAME}:
      email: jsmith@gmail.com
      failed_login_attempts: 0
      first_name: John
      last_name: Smith
      logged_in: False
      password: ${PASSWORD}
      roles:
        - admin
cookie:
  expiry_days: 30
  key: 'some_signature_key'
  name: 'vpn_auth_cookie'
"""
EOF

    log "Generated $SECRETS_FILE successfully."
fi

# Execute the main process
exec streamlit run auto_vpn/web/streamlit_app.py 

