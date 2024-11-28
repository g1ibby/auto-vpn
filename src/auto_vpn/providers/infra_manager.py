import uuid
import os
from abc import ABC, abstractmethod

from pulumi import automation as auto


class InfrastructureManager(ABC):
    """
    Abstract base class for managing infrastructure with Pulumi.
    Provides common functionalities for different cloud providers.
    """

    def __init__(self, pulumi_config_passphrase, project_name=None):
        """
        Initialize the InfrastructureManager.

        :param pulumi_config_passphrase: Passphrase for Pulumi config encryption.
        :param project_name: Optional name for the Pulumi project. If not provided, a unique name is generated.
        """
        self.pulumi_config_passphrase = pulumi_config_passphrase
        self.project_name = project_name or f"project-{uuid.uuid4()}"
        self.stack_name = "dev"  # Default stack name; can be made configurable if needed

        # **Set the Pulumi passphrase in the environment before creating/selecting the stack**
        os.environ["PULUMI_CONFIG_PASSPHRASE"] = self.pulumi_config_passphrase

        self.stack = self.create_or_select_stack()
        self.location = "ewr" 
        self.server_type ="vc2-1c-1gb" 

    def create_or_select_stack(self):
        """
        Create or select an existing Pulumi stack.

        :return: The selected or created Pulumi stack.
        """
        return auto.create_or_select_stack(
            stack_name=self.stack_name,
            project_name=self.project_name,
            program=self.pulumi_program
        )

    @abstractmethod
    def pulumi_program(self):
        """
        Define the Pulumi program for the specific provider.
        Must be implemented by subclasses.
        """
        pass

    @abstractmethod
    def set_stack_config(self):
        """
        Set the necessary stack configurations specific to the provider.
        Must be implemented by subclasses.
        """
        pass

    @abstractmethod
    def required_plugins(self):
        """
        Define the required Pulumi plugins for the provider.

        :return: A dictionary with provider names as keys and versions as values.
        """
        pass

    def install_plugins(self):
        """
        Install the required Pulumi plugins for the provider.
        """
        print("Installing required Pulumi plugins...")
        for provider, version in self.required_plugins().items():
            try:
                self.stack.workspace.install_plugin(provider, version)
                print(f"Installed plugin: {provider} v{version}")
            except auto.exceptions.PluginAlreadyInstalled:
                print(f"Plugin already installed: {provider} v{version}")
            except Exception as e:
                print(f"Error installing plugin {provider} v{version}: {e}")
                raise
        print("All required plugins are installed.")

    def up(self, location: str, server_type: str):
        """
        Deploy the Pulumi stack.

        :return: The result of the stack update.
        """
        self.location = location
        self.server_type = server_type

        self.set_stack_config()
        self.install_plugins()
        print("Refreshing the stack to get the latest state...")
        self.stack.refresh(on_output=print)
        print("Refreshing complete.")

        print("Updating the stack...")
        up_result = self.stack.up(on_output=print)
        print("Stack update complete.")
        return up_result

    def destroy(self):
        """
        Destroy the Pulumi stack and remove it from the workspace.
        """
        print("Destroying the stack...")
        self.stack.destroy(on_output=print)
        print("Stack destroyed.")

        print(f"Removing stack '{self.stack_name}' from the workspace...")
        self.stack.workspace.remove_stack(self.stack_name)
        print(f"Stack '{self.stack_name}' removed.")

    @abstractmethod
    def get_outputs(self, up_result):
        """
        Retrieve and process the outputs from the stack update.

        :param up_result: The result object from stack.up().
        :return: Processed outputs.
        """
        pass
