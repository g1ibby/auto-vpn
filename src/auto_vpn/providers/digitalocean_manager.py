from typing import Any

import pulumi
import pulumi_digitalocean as digitalocean
from pulumi import automation as auto

from auto_vpn.core.utils import setup_logger
from auto_vpn.providers.infra_manager import InfrastructureManager

logger = setup_logger("providers.digitalocean_manager")


class DigitalOceanManager(InfrastructureManager):
    """
    InfrastructureManager subclass for managing DigitalOcean resources.
    """

    def __init__(
        self,
        digitalocean_api_key: str,
        ssh_public_key: str,
        project_name: str | None = None,
        stack_state: dict[str, Any] | None = None,
    ):
        """
        Initialize the DigitalOceanManager.

        :param digitalocean_api_key: API token for DigitalOcean.
        :param ssh_public_key: SSH public key content for droplet access.
        :param project_name: Optional name for the Pulumi project.
        :param stack_state: Optional dictionary containing previously exported stack state.
        """
        self.digitalocean_api_key = digitalocean_api_key
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
        Define the Pulumi program to create a DigitalOcean droplet with SSH access.
        """
        # Create an SSH key resource in DigitalOcean
        ssh_key = digitalocean.SshKey(
            f"{self.project_name}-ssh-key",
            name=f"{self.project_name}-ssh-key",
            public_key=self.ssh_public_key,
        )

        # Create a DigitalOcean droplet
        droplet = digitalocean.Droplet(
            f"{self.project_name}-vpn",
            size=self.server_type,  # e.g., 's-1vcpu-1gb'
            region=self.location,  # e.g., 'nyc3'
            name=f"{self.project_name}-vpn",
            image="debian-12-x64",  # Debian 12
            ssh_keys=[ssh_key.id],
            monitoring=True,
            ipv6=True,
            backups=False,  # Disable backups to save cost
            private_networking=False,
        )

        logger.debug(f"Created DigitalOcean droplet with details: {droplet.__dict__}")

        # Export necessary droplet information
        pulumi.export("instance_ip", droplet.ipv4_address)
        pulumi.export("instance_id", droplet.id)

    def set_stack_config(self):
        """
        Set the necessary configurations for the DigitalOcean stack.
        """
        config_settings = {
            "digitalocean:token": auto.ConfigValue(
                value=self.digitalocean_api_key, secret=True
            ),
        }

        for key, value in config_settings.items():
            try:
                self.stack.set_config(key, value)
            except Exception as e:
                logger.warning(f"Error setting config '{key}': {e}")
                raise

    def required_plugins(self):
        """
        Specify the required Pulumi plugins for DigitalOcean.

        :return: A dictionary with provider names as keys and versions as values.
        """
        return {"digitalocean": "4.45.0"}
