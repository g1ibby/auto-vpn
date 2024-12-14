from functools import lru_cache
import requests
import pycountry
import os
from decimal import Decimal
from typing import List, Optional, Dict
from auto_vpn.providers.provider_base import CloudProvider
from auto_vpn.providers.provider_types import Region, InstanceType

class VultrProvider(CloudProvider):
    BASE_URL = "https://api.vultr.com/v2"
    
    def __init__(self, api_key: Optional[str] = None):
        super().__init__(api_key)
        if not api_key:
            raise ValueError("Vultr provider requires an API key")
        self._regions_map: Dict[str, Region] = {}
    
    def requires_api_key(self) -> bool:
        return True
    
    def get_headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def _get_country_name(self, country_code: str) -> str:
        """Convert country code to full name"""
        try:
            country = pycountry.countries.get(alpha_2=country_code)
            return country.name if country else "Unknown"
        except (KeyError, AttributeError):
            return "Unknown"
    
    @lru_cache(maxsize=1)
    def get_regions(self) -> List[Region]:
        """
        Fetch all available regions from Vultr API
        """
        url = f"{self.BASE_URL}/regions"
        response = requests.get(url, headers=self.get_headers())
        response.raise_for_status()
        
        regions = []
        for r in response.json()["regions"]:
            region = Region(
                id=r["id"],
                city=r["city"],
                country=self._get_country_name(r["country"]),
                country_code=r["country"],
                provider="vultr",
            )
            regions.append(region)
            self._regions_map[r["id"]] = region
            
        return regions
    
    @lru_cache(maxsize=1)
    def get_instance_types(self, region_id: Optional[str] = None) -> List[InstanceType]:
        """
        Fetch all instance types, optionally filtered by region
        """
        url = f"{self.BASE_URL}/plans"
        response = requests.get(url, headers=self.get_headers())
        response.raise_for_status()
        
        # Ensure regions are loaded
        if not self._regions_map:
            self.get_regions()
        
        plans = []
        for p in response.json()["plans"]:
            # Skip if region_id is specified and plan is not available in that region
            if region_id and region_id not in p.get("locations", []):
                continue
                
            plan = InstanceType(
                id=p["id"],
                vcpus=p["vcpu_count"],
                memory=p["ram"],
                disk=p["disk"],
                transfer=p.get("bandwidth", p.get("monthly_transfer")),  # Handle different field names
                price_monthly=Decimal(str(p["monthly_cost"])),
                provider="vultr"
            )
            
            # If no specific region is requested, or if the plan is available in the requested region
            if not region_id or region_id in p.get("locations", []):
                plans.append(plan)
        
        return plans
    
    def get_smallest_instance(self, region_id: Optional[str] = None) -> Optional[InstanceType]:
        """
        Get the smallest (cheapest) instance type available in the specified region
        """
        instances = self.get_instance_types(region_id)
        if not instances:
            return None

        # Filter out instances with 'free' in their ID
        paid_instances = [inst for inst in instances if 'free' not in inst.id.lower()]
        
        if not paid_instances:
            return None
            
        # First try to find the cheapest instance by monthly cost
        return min(paid_instances, key=lambda x: (x.price_monthly, x.vcpus, x.memory))

    def search_smallest(self, search_term: str) -> List[tuple[Region, InstanceType]]:
        """
        Search for smallest instance types by country or city name
        
        Args:
            search_term: Country or city name to search for
            
        Returns:
            List of tuples containing matching (Region, InstanceType) pairs,
            sorted by price (cheapest first)
        """
        search_term = search_term.lower()
        results = []
        
        # Get all regions first
        regions = self.get_regions()
        
        # Filter regions based on search term
        matching_regions = [
            region for region in regions
            if search_term in region.city.lower() or 
               search_term in region.country.lower() or 
               search_term in region.country_code.lower()
        ]
        
        # For each matching region, get the smallest instance
        for region in matching_regions:
            smallest = self.get_smallest_instance(region.id)
            if smallest:
                results.append((region, smallest))
        
        # Sort results by price
        results.sort(key=lambda x: (x[1].price_monthly, x[1].vcpus, x[1].memory))
        
        return results
