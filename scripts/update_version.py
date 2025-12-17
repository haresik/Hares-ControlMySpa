#!/usr/bin/env python3
"""
Script pro manuální aktualizaci verze v manifest.json z GitHub API.
Načte poslední tag z GitHubu a aktualizuje manifest.json pokud je novější verze dostupná.
"""

import json
import sys
import re
import os
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: requests library is required. Install it with: pip install requests")
    sys.exit(1)


def get_latest_tag():
    """
    Načte poslední tag z GitHub API.
    
    Returns:
        str: Verze z posledního tagu (bez prefixu "v") nebo None při chybě
    """
    repo = "haresik/Hares-ControlMySpa"
    api_url = f"https://api.github.com/repos/{repo}/tags"
    
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        
        tags = response.json()
        if not tags:
            print("No tags found in repository")
            return None
        
        # Najdeme první tag (API vrací tagy seřazené podle data vytvoření)
        latest_tag = tags[0].get('name', '')
        
        # Odstranění prefixu "v" pokud existuje
        version = latest_tag.lstrip('v')
        
        return version
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching tags from GitHub API: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None


def get_current_version():
    """
    Načte aktuální verzi z manifest.json.
    
    Returns:
        str: Aktuální verze nebo None při chybě
    """
    manifest_path = Path(__file__).parent.parent / 'custom_components' / 'control_my_spa' / 'manifest.json'
    
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        
        return manifest.get('version')
        
    except FileNotFoundError:
        print(f"Error: manifest.json not found at {manifest_path}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in manifest.json: {e}")
        return None
    except Exception as e:
        print(f"Error reading manifest.json: {e}")
        return None


def validate_version(version):
    """
    Validuje formát verze (semantic versioning).
    
    Args:
        version: Verze k validaci
        
    Returns:
        bool: True pokud je formát platný
    """
    pattern = r'^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9]+)?(\+[a-zA-Z0-9]+)?$'
    return bool(re.match(pattern, version))


def compare_versions(current, latest):
    """
    Porovná dvě verze a vrátí True pokud je latest novější.
    
    Args:
        current: Aktuální verze
        latest: Nová verze
        
    Returns:
        bool: True pokud je latest novější než current
    """
    def version_tuple(v):
        # Odstranění pre-release a build metadata pro porovnání
        base_version = v.split('-')[0].split('+')[0]
        return tuple(map(int, base_version.split('.')))
    
    try:
        current_tuple = version_tuple(current)
        latest_tuple = version_tuple(latest)
        return latest_tuple > current_tuple
    except ValueError:
        # Pokud nelze porovnat, považujeme za novější
        return True


def update_manifest(version):
    """
    Aktualizuje manifest.json s novou verzí.
    
    Args:
        version: Nová verze
        
    Returns:
        bool: True pokud byla aktualizace úspěšná
    """
    manifest_path = Path(__file__).parent.parent / 'custom_components' / 'control_my_spa' / 'manifest.json'
    
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        
        old_version = manifest.get('version', 'unknown')
        manifest['version'] = version
        
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
            f.write('\n')
        
        print(f"✓ Updated version from {old_version} to {version}")
        return True
        
    except Exception as e:
        print(f"Error updating manifest.json: {e}")
        return False


def main():
    """Hlavní funkce scriptu."""
    print("Checking for latest version from GitHub...")
    
    # Načtení posledního tagu z GitHubu
    latest_version = get_latest_tag()
    if not latest_version:
        print("Failed to get latest version from GitHub")
        sys.exit(1)
    
    # Validace formátu verze
    if not validate_version(latest_version):
        print(f"Error: Invalid version format: {latest_version}")
        sys.exit(1)
    
    print(f"Latest tag version: {latest_version}")
    
    # Načtení aktuální verze z manifest.json
    current_version = get_current_version()
    if not current_version:
        print("Failed to get current version from manifest.json")
        sys.exit(1)
    
    print(f"Current version in manifest.json: {current_version}")
    
    # Porovnání verzí
    if latest_version == current_version:
        print("✓ Version is already up to date")
        return
    
    if not compare_versions(current_version, latest_version):
        print(f"Warning: Latest tag ({latest_version}) is not newer than current version ({current_version})")
        response = input("Do you want to update anyway? (y/N): ")
        if response.lower() != 'y':
            print("Update cancelled")
            return
    
    # Aktualizace manifest.json
    if update_manifest(latest_version):
        print(f"\n✓ Successfully updated manifest.json to version {latest_version}")
        print("Don't forget to commit the changes!")
    else:
        print("Failed to update manifest.json")
        sys.exit(1)


if __name__ == '__main__':
    main()
