import uuid
import json
import platform
import tarfile
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod
import tempfile
from pathlib import Path
from pulumi import automation as auto
from auto_vpn.core.utils import setup_logger

logger = setup_logger(name="providers.infra_manager")

class InfrastructureManager(ABC):
    """
    Abstract base class for managing infrastructure with Pulumi.
    Provides common functionalities for different cloud providers.
    """

    def __init__(self, project_name=None, stack_state: Optional[str] = None):
        """
        Initialize the InfrastructureManager.
        """
        self.project_name = project_name or f"project-{uuid.uuid4()}"
        self.stack_name = "dev"  # Default stack name; can be made configurable if needed

        # Create temporary directory for Pulumi files
        self.temp_dir = tempfile.mkdtemp(prefix="pulumi_")

        # Create plugins directory
        self.plugins_dir = Path(self.temp_dir) / ".pulumi" / "plugins"
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

        # Create workspace with project settings
        project_settings = auto.ProjectSettings(
            name=self.project_name,
            runtime="python"
        )

        # Create workspace options with our configuration
        self.workspace = auto.LocalWorkspace(
            work_dir=self.temp_dir,
            pulumi_home=Path(self.temp_dir) / ".pulumi",
            program=self.pulumi_program,
            env_vars={
                "PULUMI_CONFIG_PASSPHRASE": "1",
                "PULUMI_SKIP_UPDATE_CHECK": "true",
                "PULUMI_BACKEND_URL": "file://" + self.temp_dir,
                "PULUMI_DISABLE_CLOUD_INTEGRATION": "true"
            },
            project_settings=project_settings,
            secrets_provider="passphrase"
        )

        # Initialize stack
        if stack_state:
            self.restore_stack_state(stack_state)
        else:
            self.stack = self.create_or_select_stack()

        self.install_plugins()


    def create_or_select_stack(self):
        """Create or select a Pulumi stack."""
        try:
            # Try to create new stack first
            return auto.Stack.create_or_select(
                stack_name=self.stack_name,
                workspace=self.workspace
            )
        except Exception as e:
            logger.warn(f"Stack creation/selection error: {e}")
            raise

    def export_stack_state(self) -> Dict[str, Any]:
        """Export the current stack state as a JSON-serializable dictionary."""
        export_result = self.stack.export_stack()

        # Read stack settings from file
        stack_settings = self._read_stack_settings()
        
        return {
            "deployment": {
                "version": export_result.version,
                "deployment": export_result.deployment
            },
            "config": stack_settings.get("config", {}), 
            "project_name": self.project_name,
            "stack_name": self.stack_name
        }

    def _read_stack_settings(self) -> Dict[str, Any]:
        """Read stack settings from Pulumi.<stack>.yaml file."""
        # Try possible extensions (.yaml, .yml, .json)
        extensions = [".yaml", ".yml", ".json"]
        stack_settings_name = f"Pulumi.{self.stack_name}"
        
        for ext in extensions:
            settings_path = Path(self.workspace.work_dir) / f"{stack_settings_name}{ext}"
            if settings_path.exists():
                with open(settings_path, 'r', encoding='utf-8') as f:
                    if ext == '.json':
                        return json.load(f)
                    else:
                        import yaml
                        return yaml.safe_load(f)
        
        # If no settings file found, return empty settings
        return {"config": {}}

    def restore_stack_state(self, state: Dict[str, Any]):
        """
        Restore a stack from previously exported state.

        :param state: The state dictionary from export_stack_state
        """
        self.project_name = state["project_name"]
        self.stack_name = state["stack_name"]

        # Create new stack instead of selecting existing one
        self.stack = auto.Stack.create(
            stack_name=self.stack_name,
            workspace=self.workspace
        )

        # Save stack settings first
        settings = auto.StackSettings(config=state["config"])
        self.workspace.save_stack_settings(
            self.stack_name,
            settings
        )

        # Create deployment object
        deployment = auto.Deployment(
            version=state["deployment"]["version"],
            deployment=state["deployment"]["deployment"]
        )

        # Then import the deployment
        self.stack.import_stack(deployment)
        logger.info(f"Successfully restored stack '{self.stack_name}' with imported state")

    @staticmethod
    def get_system_arch():
        """Determine the system architecture for plugin selection."""
        system = platform.system().lower()
        machine = platform.machine().lower()

        # Map common architectures
        arch_map = {
            'x86_64': 'amd64',
            'aarch64': 'arm64',
            'arm64': 'arm64'
        }

        # Map system names
        system_map = {
            'darwin': 'darwin',
            'linux': 'linux',
            'windows': 'windows'
        }

        arch = arch_map.get(machine, machine)
        system = system_map.get(system, system)

        return system, arch

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

    def get_plugin_filename(self, provider: str, version: str) -> str:
        """Generate the plugin filename based on system architecture."""
        system, arch = self.get_system_arch()
        return f"pulumi-resource-{provider}-v{version}-{system}-{arch}.tar.gz"

    def get_plugins_root_dir(self) -> Path:
        """Get the root directory where plugin archives are stored."""
        current_dir = Path(__file__).resolve()
        
        # Look for project markers (common files/directories that indicate project root)
        project_markers = ['pytest.ini', 'README.md', 'pulumi_plugins']
        
        # Start from current directory and go up until we find project root
        while current_dir.parent != current_dir:  # Stop at root directory
            if any((current_dir / marker).exists() for marker in project_markers):
                return current_dir / "pulumi_plugins"
            current_dir = current_dir.parent
            
        raise FileNotFoundError(
            "Could not find project root directory containing pulumi_plugins. "
            "Please ensure you're running from within the project directory."
        )

    def install_plugins(self):
        """Install all required plugins from local files."""
        for provider, version in self.required_plugins().items():
            try:
                self.install_local_plugin(provider, version)
            except Exception as e:
                logger.warn(f"Error installing plugin {provider} v{version}: {e}")
                raise

        logger.info("All required plugins are installed.")

    def install_local_plugin(self, provider: str, version: str):
        """Install plugin from local archive."""
        # Generate the expected filename
        plugin_filename = self.get_plugin_filename(provider, version)
        plugin_path = self.get_plugins_root_dir() / plugin_filename

        if not plugin_path.exists():
            raise FileNotFoundError(
                f"Plugin file not found: {plugin_path}\n"
            )

        # Create destination directory following Pulumi's structure
        plugin_dir = self.plugins_dir / f"resource-{provider}-v{version}"
        plugin_dir.mkdir(parents=True, exist_ok=True)

        # Create lock file
        lock_file = self.plugins_dir / f"resource-{provider}-v{version}.lock"
        lock_file.touch()

        # Extract the plugin
        with tarfile.open(plugin_path, "r:gz") as tar:
            tar.extractall(path=plugin_dir)

        logger.info(f"Successfully installed {provider} plugin v{version} from {plugin_path}")


    def up(self, location: str, server_type: str):
        """
        Deploy the Pulumi stack.

        :return: The result of the stack update.
        """
        self.location = location
        self.server_type = server_type

        self.set_stack_config()
        logger.info("Refreshing the stack to get the latest state...")
        self.stack.refresh()
        logger.info("Refreshing complete.")

        logger.info("Updating the stack...")
        up_result = self.stack.up()
        logger.info("Stack update complete.")
        return up_result

    def destroy(self):
        """
        Destroy the Pulumi stack and remove it from the workspace.
        """
        logger.info("Destroying the stack...")
        self.stack.destroy()
        logger.info("Stack destroyed.")

        logger.info(f"Removing stack '{self.stack_name}' from the workspace...")
        self.stack.workspace.remove_stack(self.stack_name)
        logger.info(f"Stack '{self.stack_name}' removed.")
