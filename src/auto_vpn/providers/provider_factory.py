from typing import ClassVar

from auto_vpn.providers.linode_provider import LinodeProvider
from auto_vpn.providers.provider_base import CloudProvider
from auto_vpn.providers.vultr_provider import VultrProvider


class CloudProviderFactory:
    _instances: ClassVar[dict[str, CloudProvider]] = {}

    @classmethod
    def get_provider(
        cls, provider_name: str, api_key: str | None = None
    ) -> CloudProvider | None:
        """
        Get a provider instance. Returns cached instance if available.
        Args:
            provider_name: Name of the provider ('vultr' or 'linode')
            api_key: API key for the provider (required for some providers)
        Returns:
            CloudProvider instance or None if provider not found
        """
        provider_name = provider_name.lower()

        # If we already have an instance, return it
        if provider_name in cls._instances:
            return cls._instances[provider_name]

        # Provider class mapping
        providers = {"vultr": VultrProvider, "linode": LinodeProvider}
        provider_class = providers.get(provider_name)
        if not provider_class:
            return None

        try:
            # Create new instance
            provider = provider_class(api_key)

            # Store instance for future use
            cls._instances[provider_name] = provider

            return provider
        except ValueError as e:
            # Handle missing API key for providers that require it
            print(f"Error creating provider: {e}")
            return None

    @classmethod
    def clear_cache(cls):
        """Clear all cached provider instances"""
        cls._instances.clear()
