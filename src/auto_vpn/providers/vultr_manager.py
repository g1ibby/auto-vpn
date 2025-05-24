from typing import Any

import ediri_vultr as vultr
import pulumi
from pulumi import automation as auto

from auto_vpn.core.utils import setup_logger

from .infra_manager import InfrastructureManager

logger = setup_logger("providers.vultr_manager")


class VultrManager(InfrastructureManager):
    """
    InfrastructureManager subclass for managing Vultr resources.
    """

    def __init__(
        self,
        vultr_api_key,
        ssh_public_key,
        project_name=None,
        stack_state: dict[str, Any] | None = None,
    ):
        """
        Initialize the VultrManager.

        :param vultr_api_key: API key for Vultr.
        :param project_name: Optional name for the Pulumi project.
        :param stack_state: Optional dictionary containing previously exported stack state.
        """
        self.vultr_api_key = vultr_api_key
        self._stack_state_dict = stack_state
        self.ssh_public_key = ssh_public_key

        super().__init__(project_name, stack_state=stack_state)

    def pulumi_program(self):
        """
        Define the Pulumi program to create a Vultr server with SSH access.
        """
        # Create an SSH key resource in Vultr
        ssh_key = vultr.SSHKey(
            f"{self.project_name}-ssh-key",
            name=f"{self.project_name}-ssh-key",
            ssh_key=self.ssh_public_key,
        )

        # Create a Vultr instance
        server = vultr.Instance(
            f"{self.project_name}-vpn",
            os_id=2136,  # Debian 12 x64 (bookworm)
            plan=self.server_type,
            region=self.location,
            label=f"{self.project_name}-vpn",
            ssh_key_ids=[ssh_key.id],
            backups="disabled",
            enable_ipv6=True,
        )
        logger.debug(f"Created Vultr instance with details: {server.__dict__}")

        pulumi.export("instance_ip", server.main_ip)
        pulumi.export("instance_id", server.id)

    def set_stack_config(self):
        """
        Set the necessary configurations for the Vultr stack.
        """
        config_settings = {
            "vultr:apiKey": auto.ConfigValue(value=self.vultr_api_key, secret=True),
        }

        for key, value in config_settings.items():
            try:
                self.stack.set_config(key, value)
            except Exception as e:
                logger.warn(f"Error setting config '{key}': {e}")
                raise

    def required_plugins(self):
        """
        Specify the required Pulumi plugins for Vultr.

        :return: A dictionary with provider names as keys and versions as values.
        """
        return {"vultr": "2.22.1"}
