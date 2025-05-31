from decimal import Decimal

import requests

from auto_vpn.providers.provider_base import CloudProvider
from auto_vpn.providers.provider_types import InstanceType, Region


class DigitalOceanProvider(CloudProvider):
    BASE_URL = "https://api.digitalocean.com/v2"

    def __init__(self, api_key: str | None = None):
        super().__init__(api_key)
        if not api_key:
            raise ValueError("DigitalOcean provider requires an API key")
        self._regions_map: dict[str, Region] = {}
        self._cached_regions: list[Region] | None = None
        self._cached_instance_types: list[InstanceType] | None = None

    def requires_api_key(self) -> bool:
        return True

    def get_headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _extract_city(self, region_name: str) -> str | None:
        """
        Extract city name from region name.
        Examples: "New York 3" -> "New York", "San Francisco 3" -> "San Francisco"
        """
        # Remove trailing numbers and common suffixes
        name = region_name.strip()
        # Remove trailing numbers like "3", "2", etc.
        while name and name[-1].isdigit():
            name = name[:-1].strip()
        return name if name else None

    def _get_country_from_slug(self, slug: str) -> tuple[str, str]:
        """
        Extract country information from region slug.
        Examples: "nyc3" -> ("United States", "US"), "lon1" -> ("United Kingdom", "GB")
        """
        slug_to_country = {
            "nyc": ("United States", "US"),
            "sfo": ("United States", "US"),
            "ams": ("Netherlands", "NL"),
            "sgp": ("Singapore", "SG"),
            "lon": ("United Kingdom", "GB"),
            "fra": ("Germany", "DE"),
            "tor": ("Canada", "CA"),
            "blr": ("India", "IN"),
            "syd": ("Australia", "AU"),
        }

        # Extract prefix from slug (e.g., "nyc3" -> "nyc")
        prefix = "".join(c for c in slug if c.isalpha())

        return slug_to_country.get(prefix, ("Unknown", "XX"))

    def get_regions(self) -> list[Region]:
        if self._cached_regions is not None:
            return self._cached_regions

        url = f"{self.BASE_URL}/regions"
        response = requests.get(url, headers=self.get_headers(), timeout=10)
        response.raise_for_status()

        regions = []
        for r in response.json()["regions"]:
            if not r["available"]:  # Skip unavailable regions
                continue

            country, country_code = self._get_country_from_slug(r["slug"])
            region = Region(
                id=r["slug"],
                city=self._extract_city(r["name"]),
                country=country,
                country_code=country_code,
                provider="digitalocean",
            )
            regions.append(region)
            self._regions_map[r["slug"]] = region

        self._cached_regions = regions
        return regions

    def get_instance_types(self, region_id: str | None = None) -> list[InstanceType]:
        if self._cached_instance_types is not None:
            return self._cached_instance_types

        url = f"{self.BASE_URL}/sizes"
        response = requests.get(url, headers=self.get_headers())
        response.raise_for_status()

        sizes = []
        for s in response.json()["sizes"]:
            if not s["available"]:  # Skip unavailable sizes
                continue

            # Skip if region_id is specified and size is not available in that region
            if region_id and region_id not in s.get("regions", []):
                continue

            size = InstanceType(
                id=s["slug"],
                vcpus=s["vcpus"],
                memory=s["memory"],
                disk=s["disk"],
                transfer=s["transfer"],
                price_monthly=Decimal(str(s["price_monthly"])),
                provider="digitalocean",
            )
            sizes.append(size)

        self._cached_instance_types = sizes
        return sizes

    def get_smallest_instance(
        self, region_id: str | None = None
    ) -> InstanceType | None:
        instances = self.get_instance_types(region_id)
        if not instances:
            return None

        # Filter out instances that are not suitable for VPN (too small or specialized)
        suitable_instances = [
            inst
            for inst in instances
            if inst.vcpus >= 1 and inst.memory >= 512  # At least 1 vCPU and 512MB RAM
        ]

        if not suitable_instances:
            return None

        # Return the cheapest suitable instance
        return min(
            suitable_instances, key=lambda x: (x.price_monthly, x.vcpus, x.memory)
        )

    def search_smallest(self, search_term: str) -> list[tuple[Region, InstanceType]]:
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
            region
            for region in regions
            if (region.city and search_term in region.city.lower())
            or search_term in region.country.lower()
            or search_term in region.country_code.lower()
        ]

        # For each matching region, get the smallest instance
        for region in matching_regions:
            smallest = self.get_smallest_instance(region.id)
            if smallest:
                results.append((region, smallest))

        # Sort results by price
        results.sort(key=lambda x: (x[1].price_monthly, x[1].vcpus, x[1].memory))

        return results
