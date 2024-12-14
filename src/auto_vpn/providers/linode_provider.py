from functools import lru_cache
import requests
import pycountry
from decimal import Decimal
from typing import List, Optional, Dict, Tuple
from auto_vpn.providers.provider_base import CloudProvider
from auto_vpn.providers.provider_types import Region, InstanceType

class LinodeProvider(CloudProvider):
    BASE_URL = "https://api.linode.com/v4"
    
    def __init__(self, api_key: Optional[str] = None):
        super().__init__(api_key)
        self._regions_map: Dict[str, Region] = {}

    def requires_api_key(self) -> bool:
        return False

    def get_headers(self):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _parse_location_label(self, label: str) -> Tuple[Optional[str], str]:
        """
        Parse location label to extract city and country
        Example: "Tokyo 2, JP" -> ("Tokyo", "JP")
        """
        try:
            location, _ = label.rsplit(',', 1)
            return location.strip()
        except ValueError:
            return None

    def _get_country_name(self, country_code: str) -> str:
        """Convert country code to full name"""
        try:
            country = pycountry.countries.get(alpha_2=country_code)
            return country.name if country else "Unknown"
        except (KeyError, AttributeError):
            return "Unknown"

    @lru_cache(maxsize=1)
    def get_regions(self) -> List[Region]:
        url = f"{self.BASE_URL}/regions"
        response = requests.get(url, headers=self.get_headers())
        response.raise_for_status()
        
        regions = []
        for r in response.json()["data"]:
            city = self._parse_location_label(r["label"])
            country_code = r['country'].upper()
            region = Region(
                id=r["id"],
                city=city,
                country=self._get_country_name(country_code),
                country_code=r["country"].upper(),
                provider="linode",
            )
            regions.append(region)
            self._regions_map[r["id"]] = region
            
        return regions

    @lru_cache(maxsize=1)
    def get_instance_types(self, region_id: Optional[str] = None) -> List[InstanceType]:
        url = f"{self.BASE_URL}/linode/types"
        response = requests.get(url, headers=self.get_headers())
        response.raise_for_status()

        types = []
        for t in response.json()["data"]:
            # Get base price
            base_monthly_price = Decimal(str(t["price"]["monthly"])) 
            # Check for region-specific pricing
            region_price = None
            if region_id:
                region_price = next(
                    (rp for rp in t.get("region_prices", []) if rp["id"] == region_id),
                    None
                ) 
            # Use region-specific price if available
            monthly_price = (
                Decimal(str(region_price["monthly"]))
                if region_price
                else base_monthly_price
            )

            instance_type = InstanceType(
                id=t["id"],
                vcpus=t["vcpus"],
                memory=t["memory"],
                disk=t["disk"],
                transfer=t["transfer"],
                price_monthly=monthly_price,
                provider="linode"
            )
            types.append(instance_type)

        return types

    def get_smallest_instance(self, region_id: Optional[str] = None) -> Optional[InstanceType]:
        instances = self.get_instance_types(region_id)
        if not instances:
            return None
        return min(instances, key=lambda x: (x.price_monthly, x.vcpus, x.memory))

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
            if (region.city and search_term in region.city.lower()) or 
               search_term in region.country.lower() or 
               search_term in region.country_code.lower()
        ]
        
        # For each matching region, get the smallest instance
        for region in matching_regions:
            smallest = self.get_smallest_instance()
            if smallest:
                results.append((region, smallest))
        
        # Sort results by price
        results.sort(key=lambda x: (x[1].price_monthly, x[1].vcpus, x[1].memory))
        
        return results
