from abc import ABC, abstractmethod
from typing import List, Optional
from auto_vpn.providers.provider_types import Region, InstanceType

class CloudProvider(ABC):
    """Abstract base class for cloud providers"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    @abstractmethod
    def requires_api_key(self) -> bool:
        """Whether this provider requires an API key"""
        pass
        
    @abstractmethod
    def get_regions(self) -> List[Region]:
        """Get all available regions"""
        pass
        
    @abstractmethod
    def get_instance_types(self, region_id: Optional[str] = None) -> List[InstanceType]:
        """Get all available instance types for a region"""
        pass
        
    @abstractmethod
    def get_smallest_instance(self, region_id: Optional[str] = None) -> Optional[InstanceType]:
        """Get the smallest (cheapest) instance type for a region"""
        pass

    @abstractmethod
    def search_smallest(self, search_term: str) -> List[tuple[Region, InstanceType]]:
        """
        Search for smallest instance types by country or city name
        
        Args:
            search_term: Country or city name to search for
            
        Returns:
            List of tuples containing matching (Region, InstanceType) pairs
        """
        pass
