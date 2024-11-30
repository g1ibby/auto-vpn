import paramiko
import time
import sys
import re
import socket
from datetime import datetime
from paramiko import SSHException, AuthenticationException
from typing import Optional, Dict
from paramiko.rsakey import RSAKey


class WireGuardManager:
    def __init__(self, hostname, username, private_key: RSAKey, max_retries=50, retry_delay=1):
        """
        Initializes the WireGuardManager with SSH connection details and establishes the connection.
        Implements retry logic and handles host key verification.

        :param hostname: The IP address or hostname of the SSH server.
        :param username: The SSH username.
        :param ssh_key_path: Path to the private SSH key.
        :param max_retries: Maximum number of connection attempts.
        :param retry_delay: Delay (in seconds) between retries.
        """
        self.hostname = hostname
        self.username = username
        self.client = paramiko.SSHClient()
        self.client.load_system_host_keys()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.sftp = None

        # Attempt to connect with retry logic
        for attempt in range(1, max_retries + 1):
            try:
                print(f"Attempting to connect to {self.hostname} (Attempt {attempt}/{max_retries})...")
                self.client.connect(
                    hostname=self.hostname,
                    username=self.username,
                    pkey=private_key,
                    timeout=10
                )
                print("SSH connection established.")
                break  # Exit the retry loop on success
            except (AuthenticationException, SSHException, socket.error) as e:
                print(f"Connection attempt {attempt} failed: {e}")
                if attempt < max_retries:
                    print(f"Retrying in {retry_delay} second(s)...")
                    time.sleep(retry_delay)
                else:
                    print("Maximum connection attempts reached. Exiting.")
                    sys.exit(1)
            except Exception as e:
                print(f"An unexpected error occurred: {e}")
                sys.exit(1)

        # Open SFTP client
        try:
            self.sftp = self.client.open_sftp()
            print("SFTP session established.")
        except SSHException as e:
            print(f"Failed to establish SFTP session: {e}")
            self.client.close()
            sys.exit(1)

    def execute_command_with_responses(self, command, responses, completion_indicator=None, timeout=600):
        """
        Executes a command on the remote server and sends predefined responses to prompts.

        :param command: The command to execute.
        :param responses: A list of tuples containing (regex_pattern, response).
        :param completion_indicator: A string that indicates the completion of the command.
        :param timeout: Maximum time to wait for the command to complete.
        :return: None
        """
        try:
            shell = self.client.invoke_shell()
            time.sleep(1)  # Wait for the shell to be ready

            # Clear any initial data
            if shell.recv_ready():
                initial_output = shell.recv(65535).decode('utf-8', errors='ignore')
                print(initial_output)

            # Send the command
            shell.send(command + '\n')
            print(f"Executing command: {command}")

            buffer = ''
            response_index = 0
            start_time = time.time()

            while True:
                if shell.recv_ready():
                    recv = shell.recv(1024).decode('utf-8', errors='ignore')
                    buffer += recv
                    print(recv, end='')  # Optional: print server output

                    # Check for each prompt and send response
                    if response_index < len(responses):
                        prompt_pattern, response = responses[response_index]
                        if re.search(prompt_pattern, buffer, re.IGNORECASE | re.MULTILINE):
                            print(f"\nDetected prompt: '{prompt_pattern.strip()}', sending response: '{response.strip()}'")
                            shell.send(response)
                            response_index += 1
                            # Clear buffer to prevent re-matching
                            buffer = ''

                # Check for completion indicator
                if completion_indicator and completion_indicator in buffer:
                    print(f"\nDetected completion indicator: '{completion_indicator}'")
                    break

                # Check for timeout
                if time.time() - start_time > timeout:
                    print("\nCommand execution timed out.")
                    break

                time.sleep(0.5)

        except Exception as e:
            print(f"Error during command execution: {e}")

    def list_clients(self):
        """
        Lists all existing WireGuard clients by parsing the wg0.conf file.

        :return: A list of client names.
        """
        try:
            wg_conf_path = '/etc/wireguard/wg0.conf'
            with self.sftp.open(wg_conf_path, 'r') as f:
                wg_conf = f.read().decode('utf-8')

            # Extract client names between # BEGIN_PEER and # END_PEER
            clients = re.findall(r'# BEGIN_PEER (\S+)', wg_conf)
            return clients

        except IOError:
            print("WireGuard configuration file not found.")
            return []

    def show_clients(self):
        """
        Retrieves and displays the list of existing WireGuard clients.
        """
        clients = self.list_clients()
        if not clients:
            print("No existing clients found.")
        else:
            print("\n=== Existing WireGuard Clients ===")
            for idx, client in enumerate(clients, start=1):
                print(f"{idx}) {client}")
            print("=== End of Clients List ===\n")

    def add_client(self, client_name) -> tuple[str, str]:
        """
        Adds a new WireGuard client. If WireGuard is not installed, it installs it first.

        :param client_name: The desired name for the WireGuard client.
        :return: None
        """
        # Check length of client name should not be more than 15 characters
        if len(client_name) > 15:
            raise ValueError("Client name should not exceed 15 characters.")

        # First, check if WireGuard is installed by checking for wg0.conf
        wg_conf_exists = False
        try:
            self.sftp.stat('/etc/wireguard/wg0.conf')
            wg_conf_exists = True
        except IOError:
            wg_conf_exists = False

        if not wg_conf_exists:
            print("WireGuard is not installed. Proceeding with installation.")
            # Define the responses for installation
            responses = [
                (r'Port \[51820\]:\s*$', '\n'),                         # Accept default port
                (r'Name \[client\]:\s*$', f'{client_name}\n'),          # Enter client name
                (r'DNS server \[1\]:\s*$', '3\n'),                      # Select DNS option 3
                (r'Press any key to continue\.\.\.\s*$', '\n'),          # Press any key
            ]

            # Combined installation command
            install_command = 'wget https://git.io/wireguard -O wireguard-install.sh && bash wireguard-install.sh'

            # Execute the installation command with responses
            self.execute_command_with_responses(
                command=install_command,
                responses=responses,
                completion_indicator='Finished!',
                timeout=900  # 15 minutes
            )

            # Retrieve and display client.conf
            client_conf_path = f'/root/{client_name}.conf'
            config_str = self.retrieve_and_display_conf(client_conf_path)
            private_key = extract_private_key(config_str)
            return config_str, private_key
        else:
            print("WireGuard is already installed. Proceeding to add a new client.")
            # Define the responses for adding a new client
            responses = [
                (r'Option:\s*$', '1\n'),                                # Select option 1 to add a new client
                (r'Name:\s*$', f'{client_name}\n'),                     # Enter client name
                (r'DNS server \[1\]:\s*$', '3\n'),                      # Select DNS option 3
                (r'Press any key to continue\.\.\.\s*$', '\n'),          # Press any key
            ]

            # Command to run the WireGuard install script to add a client
            add_client_command = 'bash wireguard-install.sh'

            # Execute the add client command with responses
            self.execute_command_with_responses(
                command=add_client_command,
                responses=responses,
                completion_indicator=f'{client_name} added.',
                timeout=600  # 10 minutes
            )

            # Retrieve and display the new client.conf
            client_conf_path = f'/root/{client_name}.conf'
            config_str = self.retrieve_and_display_conf(client_conf_path)
            private_key = extract_private_key(config_str)
            return config_str, private_key

    def remove_client(self, client_name):
        """
        Removes an existing WireGuard client.

        :param client_name: The name of the WireGuard client to remove.
        :return: None
        """
        # First, list existing clients
        clients = self.list_clients()
        if not clients:
            print("No clients available to remove.")
            return

        if client_name not in clients:
            print(f"Client '{client_name}' does not exist.")
            return

        # Determine the client's number
        client_number = clients.index(client_name) + 1

        # Define the responses for removing a client
        responses = [
            (r'Option:\s*$', '2\n'),                                # Select option 2 to remove a client
            (r'Client:\s*$', f'{client_number}\n'),                # Select the client number to remove
            (r'Confirm .* removal\? \[y/N\]:\s*$', 'y\n'),         # Confirm removal
            (r'Press any key to continue\.\.\.\s*$', '\n'),         # Press any key
        ]

        # Command to run the WireGuard install script to remove a client
        remove_client_command = 'bash wireguard-install.sh'

        # Execute the remove client command with responses
        self.execute_command_with_responses(
            command=remove_client_command,
            responses=responses,
            completion_indicator=f'{client_name} removed!',
            timeout=600  # 10 minutes
        )

    def retrieve_and_display_conf(self, client_conf_path):
        """
        Retrieves the client configuration file and displays its content.

        :param client_conf_path: The path to the client.conf file on the server.
        :return: None
        """
        try:
            print(f"Retrieving {client_conf_path}...")
            with self.sftp.open(client_conf_path, 'r') as f:
                client_conf = f.read().decode('utf-8')
                print("\n=== client.conf Content ===\n")
                print(client_conf)
                print("\n=== End of client.conf ===\n")
                return client_conf
        except IOError:
            print(f"Error: {client_conf_path} not found.")

    def list_clients_menu(self):
        """
        Displays the list of existing WireGuard clients.
        """
        self.show_clients()

    def get_latest_handshakes(self) -> Dict[str, Optional[datetime]]:
        """
        Retrieves the latest handshake times for all WireGuard peers.

        :return: A dictionary mapping peer public keys to their latest handshake time as datetime objects in UTC.
                 If a handshake has never occurred, the value is None.
        """
        command = 'wg show all latest-handshakes'
        try:
            stdin, stdout, stderr = self.client.exec_command(command)
            output = stdout.read().decode('utf-8')
            error = stderr.read().decode('utf-8')
            if error:
                print(f"Error executing command: {error}")
                return {}

            handshakes = {}
            for line in output.strip().split('\n'):
                parts = line.split()
                if len(parts) != 3:
                    continue  # Skip malformed lines
                _, peer_public_key, timestamp_str = parts
                try:
                    timestamp = int(timestamp_str)
                    if timestamp == 0:
                        handshake_time = None  # Indicates that the handshake has never occurred
                    else:
                        handshake_time = datetime.utcfromtimestamp(timestamp)
                except ValueError:
                    handshake_time = None  # Treat invalid timestamps as never

                handshakes[peer_public_key] = handshake_time

            return handshakes

        except Exception as e:
            print(f"Failed to retrieve latest handshakes: {e}")
            return {}

    def close(self):
        """
        Closes the SSH and SFTP connections.
        """
        if self.sftp:
            self.sftp.close()
            print("SFTP session closed.")
        self.client.close()
        print("SSH connection closed.")

def extract_private_key(config: str) -> str:
    """
    Extracts the PrivateKey value from a WireGuard configuration string.

    Parameters:
        config (str): The WireGuard configuration string.

    Returns:
        str: The PrivateKey value if found, otherwise an empty string.
    """
    # Use regular expression to find the PublicKey
    match = re.search(r"PrivateKey\s*=\s*([\w+/=]+)", config)
    if match:
        return match.group(1)
    return ""

def main():
    # Server and SSH details
    hostname = '95.179.164.49'
    username = 'root'
    ssh_key_path = '~/.ssh/id_rsa'  # Path to your private SSH key

    # Initialize the WireGuardManager
    wg_manager = WireGuardManager(hostname, username, ssh_key_path)

    try:
        while True:
            print("\n=== WireGuard Manager ===")
            print("1) Install WireGuard / Add Client")
            print("2) Remove an Existing Client")
            print("3) List Existing Clients")
            print("4) Show Latest Handshakes")  # New Menu Option
            print("5) Exit")
            choice = input("Select an option: ").strip()

            if choice == '1':
                # Add a New Client
                client_name = input("Enter the name for the new client: ").strip()
                if client_name:
                    wg_manager.add_client(client_name)
                else:
                    print("Client name cannot be empty.")
            elif choice == '2':
                # Remove an Existing Client
                client_name = input("Enter the name of the client to remove: ").strip()
                if client_name:
                    wg_manager.remove_client(client_name)
                else:
                    print("Client name cannot be empty.")
            elif choice == '3':
                # List Existing Clients
                wg_manager.list_clients_menu()
            elif choice == '4':
                # Show Latest Handshakes
                handshakes = wg_manager.get_latest_handshakes()
                if not handshakes:
                    print("No handshake data available.")
                else:
                    print("\n=== Latest Handshakes ===")
                    for public_key, handshake_time in handshakes.items():
                        if handshake_time:
                            print(f"Peer Public Key: {public_key}")
                            print(f"Latest Handshake: {handshake_time.strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
                        else:
                            print(f"Peer Public Key: {public_key}")
                            print("Latest Handshake: Never\n")
                    print("=== End of Handshakes ===\n")
            elif choice == '5':
                print("Exiting WireGuard Manager.")
                break
            else:
                print("Invalid option. Please select a valid number (1-4).")

    finally:
        wg_manager.close()


if __name__ == "__main__":
    main()

