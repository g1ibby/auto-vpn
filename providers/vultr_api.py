import os
from dotenv import load_dotenv
import requests
import pycountry
from functools import lru_cache

class VultrAPI:
    def __init__(self, api_key=None):
        """
        Initializes the VultrAPI class, loading the API key from the environment variables.
        """
        self.api_key = api_key

    def get_headers(self):
        """
        Constructs headers for the API request.

        Returns:
            dict: The headers including authorization.
        """
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def get_vultr_regions(self):
        """
        Retrieves the list of regions from the Vultr API.

        Returns:
            list: A list of region dictionaries.
        """
        url = "https://api.vultr.com/v2/regions"
        response = requests.get(url, headers=self.get_headers())
        response.raise_for_status()
        data = response.json()
        return data["regions"]

    def get_available_plans_for_region(self, region_id):
        """
        Retrieves the list of available plans for a specific region from the Vultr API.

        Args:
            region_id (str): The ID of the region to retrieve plans for.

        Returns:
            list: A list of available plan identifiers.
        """
        url = f"https://api.vultr.com/v2/regions/{region_id}/availability"
        response = requests.get(url, headers=self.get_headers())
        response.raise_for_status()
        data = response.json()
        return data["available_plans"]

    @staticmethod
    def get_country_name(country_code):
        """
        Converts a country code to a full country name using pycountry.

        Args:
            country_code (str): The ISO country code.

        Returns:
            str: The full country name, or 'Unknown' if not found.
        """
        try:
            country = pycountry.countries.get(alpha_2=country_code)
            return country.name if country else "Unknown"
        except KeyError:
            return "Unknown"

    @lru_cache(maxsize=1)
    def get_regions_with_plan(self, plan_id="vc2-1c-1gb"):
        """
        Finds and returns all regions that have the specified plan available.

        Args:
            plan_id (str): The plan ID to check for availability.

        Returns:
            list: A list of dictionaries with region 'id', 'city', 'country_code', and 'country' for regions where the plan is available.
        """
        regions_with_plan = []
        regions = self.get_vultr_regions()

        for region in regions:
            region_id = region["id"]
            available_plans = self.get_available_plans_for_region(region_id)

            if plan_id in available_plans:
                country_code = region["country"]
                country_name = self.get_country_name(country_code)

                regions_with_plan.append({
                    "id": region["id"],
                    "city": region["city"],
                    "country_code": country_code,
                    "country": country_name
                })

        return regions_with_plan

    def search(self, search_term, plan_id="vc2-1c-1gb"):
        """
        Searches for regions by city or country name or country code within the cached regions with the specified plan.

        Args:
            search_term (str): The term to search for in city or country.
            plan_id (str): The plan ID to check for availability (default is 'vc2-1c-1gb').

        Returns:
            list: A list of dictionaries with matching regions.
        """
        search_term = search_term.lower()
        regions_with_plan = self.get_regions_with_plan(plan_id)
        return [
            region for region in regions_with_plan
            if search_term in region["city"].lower() or search_term in region["country"].lower() or search_term in region["country_code"].lower()
        ]


if __name__ == "__main__":
    load_dotenv()
    API_KEY = os.getenv("VULTR_API_KEY")
    if not API_KEY:
        raise ValueError("API key not found. Please set the 'VULTR_API_KEY' environment variable.")
    # Create an instance of VultrAPI and test the functionality
    vultr_api = VultrAPI(API_KEY)

    # Find regions with the 'vc2-1c-1gb' plan available
    regions_with_specific_plan = vultr_api.get_regions_with_plan("vc2-1c-1gb")
    print("Regions with vc2-1c-1gb available:", regions_with_specific_plan)

    # Search for regions by city or country name
    search_result = vultr_api.search("Tokyo", "vc2-1c-1gb")
    print("Search results for 'Tokyo':", search_result)

    search_result = vultr_api.search("us", "vc2-1c-1gb")
    print("Search results for 'us':", search_result)

