from typing import Any

import pulumi
import pulumi_linode as linode
from pulumi import automation as auto

from auto_vpn.core.utils import generate_password, setup_logger
from auto_vpn.providers.infra_manager import InfrastructureManager

logger = setup_logger("providers.linode_manager")


class LinodeManager(InfrastructureManager):
    """
    InfrastructureManager subclass for managing Linode resources.
    """

    def __init__(
        self,
        linode_api_key: str,
        ssh_public_key: str,
        project_name: str | None = None,
        stack_state: dict[str, Any] | None = None,
    ):
        """
        Initialize the LinodeManager.
        :param linode_api_key: API token for Linode.
        :param ssh_public_key: SSH public key content for instance access.
        :param project_name: Optional name for the Pulumi project.
        :param stack_state: Optional dictionary containing previously exported stack state.
        """
        self.linode_api_key = linode_api_key
        self._stack_state_dict = stack_state
        self.ssh_public_key = self._clean_ssh_key(ssh_public_key)
        super().__init__(project_name, stack_state=stack_state)

    @staticmethod
    def _clean_ssh_key(ssh_key: str) -> str:
        """
        Clean the SSH key by removing extra whitespace and newlines.
        """
        return " ".join(ssh_key.strip().split())

    def pulumi_program(self):
        """
        Define the Pulumi program to create a Linode instance with SSH access.
        """
        # Create an SSH key resource in Linode
        ssh_key = linode.SshKey(
            f"{self.project_name}-ssh-key",
            label=f"{self.project_name}-ssh-key",
            ssh_key=self.ssh_public_key,
        )

        root_pass = generate_password()

        # Create a Linode instance
        instance = linode.Instance(
            f"{self.project_name}-vpn",
            type=self.server_type,  # e.g., 'g6-nanode-1'
            region=self.location,  # e.g., 'us-east'
            label=f"{self.project_name}-vpn",
            image="linode/debian12",  # Debian 12
            root_pass=root_pass,
            authorized_keys=[ssh_key.ssh_key],
            private_ip=False,
            booted=True,
        )

        logger.debug(f"Created Linode instance with details: {instance.__dict__}")

        # Export necessary instance information
        pulumi.export("instance_ip", instance.ipv4)
        pulumi.export("instance_id", instance.id)

    def set_stack_config(self):
        """
        Set the necessary configurations for the Linode stack.
        """
        config_settings = {
            "linode:token": auto.ConfigValue(value=self.linode_api_key, secret=True),
        }

        for key, value in config_settings.items():
            try:
                self.stack.set_config(key, value)
            except Exception as e:
                logger.warn(f"Error setting config '{key}': {e}")
                raise

    def required_plugins(self):
        """
        Specify the required Pulumi plugins for Linode.
        :return: A dictionary with provider names as keys and versions as values.
        """
        return {"linode": "4.39.0"}  # Use the latest stable version
