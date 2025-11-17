"""
Sanctions downloader - fetches and parses EU sanctions list.
Downloads XML from EU Financial Sanctions Database and converts to JSON for faster access.
"""

import os
import json
import fcntl
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, date
from typing import Dict, List, Optional
from services.aml_service.config import SANCTIONS_SOURCE_URL, SANCTIONS_FILE_PATH, SANCTIONS_DATA_DIR


def check_file_updated_today(filepath: str) -> bool:
    """
    Check if sanctions file was updated today.

    Args:
        filepath: Path to sanctions JSON file

    Returns:
        True if file exists and was modified today, False otherwise
    """
    if not os.path.exists(filepath):
        return False

    file_mtime = os.path.getmtime(filepath)
    file_date = datetime.fromtimestamp(file_mtime).date()
    today = date.today()

    return file_date == today


def download_sanctions_xml() -> Optional[str]:
    """
    Download EU sanctions XML from public source.

    Returns:
        XML content as string, or None if download failed
    """
    try:
        print(f"[AML] Downloading sanctions list from {SANCTIONS_SOURCE_URL}")
        response = requests.get(SANCTIONS_SOURCE_URL, timeout=30)
        response.raise_for_status()

        print(f"[AML] Downloaded {len(response.content)} bytes")
        return response.text

    except Exception as e:
        print(f"[AML] ERROR: Failed to download sanctions list: {type(e).__name__}: {str(e)}")
        return None


def parse_sanctions_xml(xml_content: str) -> List[Dict]:
    """
    Parse EU sanctions XML and extract sanctioned entities with name aliases.

    Args:
        xml_content: Raw XML string from EU sanctions database

    Returns:
        List of sanctioned entities with structure:
        [
            {
                "eu_reference_number": "EU.39.56",
                "subject_type": "person",
                "name_aliases": [
                    {"wholeName": "Qoussaï Saddam Hussein Al-Tikriti", "firstName": "Qoussaï", ...},
                    {"wholeName": "Qusay Saddam Hussein Al-Tikriti", "firstName": "Qusay", ...}
                ],
                "citizenship": ["IQ"],
                "birthdates": ["1965", "1966"]
            },
            ...
        ]
    """
    try:
        # Parse XML and register namespace
        root = ET.fromstring(xml_content)

        # Define namespace (from XSD: xmlns:fsdexport="http://eu.europa.ec/fpi/fsd/export")
        ns = {"fsd": "http://eu.europa.ec/fpi/fsd/export"}

        entities = []

        # Find all sanctionEntity elements using namespace
        for entity_elem in root.findall(".//fsd:sanctionEntity", ns):
            entity = {
                "eu_reference_number": entity_elem.get("euReferenceNumber", ""),
                "subject_type": "",
                "name_aliases": [],
                "citizenship": [],
                "birthdates": [],
            }

            # Extract subject type (person, entity, etc.)
            for child in entity_elem:
                if child.tag.endswith("subjectType"):
                    entity["subject_type"] = child.get("code", "")

            # Extract all name aliases
            for child in entity_elem:
                if not child.tag.endswith("nameAlias"):
                    continue
                name_elem = child
                name_alias = {
                    "wholeName": name_elem.get("wholeName", ""),
                    "firstName": name_elem.get("firstName", ""),
                    "middleName": name_elem.get("middleName", ""),
                    "lastName": name_elem.get("lastName", ""),
                    "gender": name_elem.get("gender", ""),
                    "title": name_elem.get("title", ""),
                }
                entity["name_aliases"].append(name_alias)

            # Extract citizenship
            for child in entity_elem:
                if child.tag.endswith("citizenship"):
                    country_code = child.get("countryIso2Code", "")
                    if country_code and country_code != "00":  # Exclude UNKNOWN
                        entity["citizenship"].append(country_code)

            # Extract birthdates
            for child in entity_elem:
                if child.tag.endswith("birthdate"):
                    year = child.get("year", "")
                    if year:
                        entity["birthdates"].append(year)

            entities.append(entity)

        print(f"[AML] Parsed {len(entities)} sanctioned entities from XML")
        return entities

    except Exception as e:
        print(f"[AML] ERROR: Failed to parse sanctions XML: {type(e).__name__}: {str(e)}")
        return []


def save_sanctions_to_file(entities: List[Dict], filepath: str):
    """
    Save sanctions entities to JSON file with exclusive lock.

    Args:
        entities: List of sanctioned entities
        filepath: Path to save JSON file
    """
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        sanctions_data = {
            "last_updated": datetime.utcnow().isoformat(),
            "entity_count": len(entities),
            "entities": entities,
        }

        # Write with exclusive lock (blocks readers until complete)
        with open(filepath, "w") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                json.dump(sanctions_data, f, indent=2)
                print(f"[AML] Saved {len(entities)} entities to {filepath}")
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    except Exception as e:
        print(f"[AML] ERROR: Failed to save sanctions file: {type(e).__name__}: {str(e)}")


def update_sanctions_list() -> bool:
    """
    Download and update sanctions list if not updated today.

    Returns:
        True if sanctions list is up-to-date (either already updated today or just updated),
        False if update failed
    """
    # Check if already updated today
    if check_file_updated_today(SANCTIONS_FILE_PATH):
        print(f"[AML] Sanctions list already updated today: {SANCTIONS_FILE_PATH}")
        return True

    # Download XML
    xml_content = download_sanctions_xml()
    if not xml_content:
        print("[AML] WARNING: Failed to download sanctions list, using existing file if available")
        return os.path.exists(SANCTIONS_FILE_PATH)  # Return True if we have a cached version

    # Parse XML
    entities = parse_sanctions_xml(xml_content)
    if not entities:
        print("[AML] WARNING: Failed to parse sanctions list, using existing file if available")
        return os.path.exists(SANCTIONS_FILE_PATH)

    # Save to file
    save_sanctions_to_file(entities, SANCTIONS_FILE_PATH)

    return True


if __name__ == "__main__":
    # Test script
    print("Testing sanctions downloader...")
    success = update_sanctions_list()
    print(f"Update successful: {success}")
