#!/usr/bin/env python3
"""
Script to update Pulumi plugins to their latest versions.
Downloads the latest versions of Linode, Vultr, and DigitalOcean plugins for Linux and Darwin platforms,
supporting both amd64 and arm64 architectures when available.
"""

import json
import re
import sys
import urllib.request
from pathlib import Path

PLUGINS_DIR = Path("pulumi_plugins")
GITHUB_API_BASE = "https://api.github.com/repos"

PLUGIN_CONFIGS = {
    "linode": {
        "repo": "pulumi/pulumi-linode",
        "prefix": "pulumi-resource-linode-v",
        "platforms": ["darwin-amd64", "darwin-arm64", "linux-amd64", "linux-arm64"],
    },
    "vultr": {
        "repo": "dirien/pulumi-vultr",
        "prefix": "pulumi-resource-vultr-v",
        "platforms": ["darwin-amd64", "darwin-arm64", "linux-amd64", "linux-arm64"],
    },
    "digitalocean": {
        "repo": "pulumi/pulumi-digitalocean",
        "prefix": "pulumi-resource-digitalocean-v",
        "platforms": ["darwin-amd64", "darwin-arm64", "linux-amd64", "linux-arm64"],
    },
}


def get_latest_release(repo: str) -> dict:
    """Get the latest release info from GitHub API."""
    url = f"{GITHUB_API_BASE}/{repo}/releases/latest"
    try:
        with urllib.request.urlopen(url) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"Error fetching latest release for {repo}: {e}")
        sys.exit(1)


def get_current_version(prefix: str) -> str:
    """Get the current version of a plugin from existing files."""
    pattern = re.compile(rf"{re.escape(prefix)}(\d+\.\d+\.\d+)-.+\.tar\.gz")
    for file in PLUGINS_DIR.glob(f"{prefix}*"):
        match = pattern.match(file.name)
        if match:
            return match.group(1)
    return "0.0.0"


def get_current_platforms(prefix: str, version: str) -> set:
    """Get the current platforms available for a specific version."""
    pattern = re.compile(rf"{re.escape(prefix)}{re.escape(version)}-(.+)\.tar\.gz")
    platforms = set()
    for file in PLUGINS_DIR.glob(f"{prefix}{version}-*"):
        match = pattern.match(file.name)
        if match:
            platforms.add(match.group(1))
    return platforms


def download_file(url: str, filepath: Path) -> None:
    """Download a file from URL to filepath."""
    print(f"Downloading {filepath.name}...")
    try:
        urllib.request.urlretrieve(url, filepath)
        print(f"✓ Downloaded {filepath.name}")
    except Exception as e:
        print(f"✗ Error downloading {filepath.name}: {e}")
        raise


def remove_old_versions(prefix: str, keep_version: str) -> None:
    """Remove old plugin versions, keeping only the specified version."""
    pattern = re.compile(rf"{re.escape(prefix)}(\d+\.\d+\.\d+)-.+\.tar\.gz")
    for file in PLUGINS_DIR.glob(f"{prefix}*"):
        match = pattern.match(file.name)
        if match and match.group(1) != keep_version:
            print(f"Removing old version: {file.name}")
            file.unlink()


def update_plugin(plugin_name: str, config: dict) -> bool:
    """Update a single plugin to its latest version and download missing platforms."""
    print(f"\n=== Updating {plugin_name} plugin ===")

    release = get_latest_release(config["repo"])
    latest_version = release["tag_name"].lstrip("v")
    current_version = get_current_version(config["prefix"])
    current_platforms = get_current_platforms(config["prefix"], latest_version)

    print(f"Current version: {current_version}")
    print(f"Latest version: {latest_version}")
    print(
        f"Current platforms: {sorted(current_platforms) if current_platforms else 'none'}"
    )

    version_updated = current_version != latest_version

    # Find available assets
    available_assets = {asset["name"]: asset for asset in release["assets"]}

    # Find and download assets
    assets_downloaded = []
    assets_missing = []

    for platform in config["platforms"]:
        expected_name = f"{config['prefix']}{latest_version}-{platform}.tar.gz"

        # Skip if we already have this platform for the latest version
        if not version_updated and platform in current_platforms:
            continue

        if expected_name in available_assets:
            asset = available_assets[expected_name]
            filepath = PLUGINS_DIR / asset["name"]
            download_file(asset["browser_download_url"], filepath)
            assets_downloaded.append(expected_name)
        else:
            assets_missing.append(expected_name)

    # Report download results
    if assets_downloaded:
        print(
            f"✓ Downloaded {len(assets_downloaded)} asset(s): {', '.join([name.split('/')[-1] for name in assets_downloaded])}"
        )

    if assets_missing:
        print(
            f"⚠ Missing {len(assets_missing)} asset(s): {', '.join([name.split('/')[-1] for name in assets_missing])}"
        )

    # Check if we're completely up to date
    if (
        not assets_downloaded
        and not assets_missing
        and current_version == latest_version
    ):
        print(f"✓ {plugin_name} is already up to date with all available platforms")
        return False

    # Only proceed with cleanup if we downloaded at least one asset or had a version update
    if not assets_downloaded and not version_updated:
        if assets_missing:
            print(
                f"⚠ {plugin_name} has missing platforms but they're not available in the latest release"
            )
        return False

    # Remove old versions only if we had a version update
    if version_updated:
        remove_old_versions(config["prefix"], latest_version)
        print(f"✓ {plugin_name} updated from {current_version} to {latest_version}")
    else:
        print(f"✓ {plugin_name} platforms updated for version {latest_version}")

    return True


def main():
    """Main function to update all plugins."""
    print("Pulumi Plugin Updater")
    print("====================")

    # Ensure plugins directory exists
    PLUGINS_DIR.mkdir(exist_ok=True)

    updated_count = 0
    for plugin_name, config in PLUGIN_CONFIGS.items():
        try:
            if update_plugin(plugin_name, config):
                updated_count += 1
        except Exception as e:
            print(f"✗ Failed to update {plugin_name}: {e}")

    print("\n=== Summary ===")
    print(f"Updated {updated_count} plugin(s)")

    if updated_count > 0:
        print("\nPlugin update completed successfully!")
    else:
        print("\nAll plugins are already up to date.")


if __name__ == "__main__":
    main()
