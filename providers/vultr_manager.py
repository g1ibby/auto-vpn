import os
from pulumi import automation as auto
import pulumi
import ediri_vultr as vultr

from .infra_manager import InfrastructureManager

class VultrManager(InfrastructureManager):
    """
    InfrastructureManager subclass for managing Vultr resources.
    """

    def __init__(self, pulumi_config_passphrase, vultr_api_key, project_name=None):
        """
        Initialize the VultrManager.

        :param pulumi_config_passphrase: Passphrase for Pulumi config encryption.
        :param vultr_api_key: API key for Vultr.
        :param project_name: Optional name for the Pulumi project.
        """
        self.vultr_api_key = vultr_api_key
        super().__init__(pulumi_config_passphrase, project_name)

    def pulumi_program(self):
        """
        Define the Pulumi program to create a Vultr server with SSH access.
        """
        config = pulumi.Config()
        ssh_public_key_path = config.get("sshPublicKeyPath") or "~/.ssh/id_rsa.pub"

        # Expand the path if it contains ~
        ssh_public_key_path = os.path.expanduser(ssh_public_key_path)

        # Read the SSH public key
        try:
            with open(ssh_public_key_path, "r") as f:
                ssh_public_key = f.read().strip()
        except FileNotFoundError:
            pulumi.log.error(f"SSH public key not found at {ssh_public_key_path}. Please provide a valid path.")
            raise FileNotFoundError(f"SSH public key not found at {ssh_public_key_path}.")

        # Create an SSH key resource in Vultr
        ssh_key = vultr.SSHKey(f"{self.project_name}-ssh-key",
                               name=f"{self.project_name}-ssh-key",
                               ssh_key=ssh_public_key)

        # Create a Vultr instance
        server = vultr.Instance(f"{self.project_name}-vpn",
                                 os_id=1743,         # Ubuntu 22.04 x64
                                 plan=self.server_type,
                                 region=self.location,
                                 label=f"{self.project_name}-vpn",
                                 ssh_key_ids=[ssh_key.id],
                                 backups="disabled",
                                 enable_ipv6=True)
        print(f"Created Vultr instance with details: {server.__dict__}")

        # Construct the SSH connection string
        ssh_connection_string = pulumi.Output.concat("ssh root@", server.main_ip)

        # Export the server's IP address, ID, and SSH connection string
        pulumi.export('instance_ip', server.main_ip)
        pulumi.export('instance_id', server.id)
        pulumi.export('ssh_connection_string', ssh_connection_string)

    def set_stack_config(self):
        """
        Set the necessary configurations for the Vultr stack.
        """
        config_settings = {
            "vultr:apiKey": auto.ConfigValue(
                value=self.vultr_api_key,
                secret=True  # Mark the API key as a secret
            ),
            "sshPublicKeyPath": auto.ConfigValue(
                value=os.path.expanduser("~/.ssh/id_rsa.pub"),
                secret=False
            )
        }

        for key, value in config_settings.items():
            try:
                self.stack.set_config(key, value)
                print(f"Set config '{key}' successfully.")
            except Exception as e:
                print(f"Error setting config '{key}': {e}")
                raise

    def required_plugins(self):
        """
        Specify the required Pulumi plugins for Vultr.

        :return: A dictionary with provider names as keys and versions as values.
        """
        return {"vultr": "2.20.1"}  # Replace with the correct version if needed

    def get_outputs(self, up_result):
        """
        Retrieve and process the outputs from the stack update.

        :param up_result: The result object from stack.up().
        :return: Dictionary of outputs.
        """
        outputs = up_result.outputs
        processed_outputs = {}
        for key, output in outputs.items():
            processed_outputs[key] = output.value
        return processed_outputs

