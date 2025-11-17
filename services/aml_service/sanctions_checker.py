"""
Sanctions checker - checks if customer name matches sanctioned entities.
Provides thread-safe file access and normalized name matching.
"""

import os
import json
import fcntl
from typing import Optional, Dict, List
from services.aml_service.config import SANCTIONS_FILE_PATH


def load_sanctions_file_safe(filepath: str) -> Optional[Dict]:
    """
    Load sanctions data from JSON file with shared lock (thread-safe read).

    Args:
        filepath: Path to sanctions JSON file

    Returns:
        Sanctions data dict with 'entities' list, or None if file doesn't exist or read failed
    """
    if not os.path.exists(filepath):
        print(f"[AML] WARNING: Sanctions file not found: {filepath}")
        return None

    try:
        with open(filepath, "r") as f:
            # Shared lock (multiple readers allowed simultaneously)
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                data = json.load(f)
                return data
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    except Exception as e:
        print(f"[AML] ERROR: Failed to load sanctions file: {type(e).__name__}: {str(e)}")
        return None


def normalize_name(name: str) -> str:
    """
    Normalize name for comparison (lowercase, strip whitespace).

    Args:
        name: Customer or sanctioned entity name

    Returns:
        Normalized name string
    """
    return name.lower().strip()


def check_customer_in_sanctions(customer_name: str, sanctions_data: Dict) -> Optional[str]:
    """
    Check if customer name matches any sanctioned entity wholeName.

    LIMITATION: Uses normalized exact matching only (case-insensitive, whitespace-trimmed).
    Production systems require fuzzy matching (Levenshtein distance, phonetic algorithms).

    Args:
        customer_name: Name of customer to check
        sanctions_data: Loaded sanctions data dict from load_sanctions_file_safe()

    Returns:
        Matched wholeName from sanctions list if found, None otherwise
    """
    if not sanctions_data or "entities" not in sanctions_data:
        print("[AML] WARNING: Invalid sanctions data structure")
        return None

    normalized_customer = normalize_name(customer_name)
    entities = sanctions_data.get("entities", [])

    print(f"[AML] Checking '{customer_name}' against {len(entities)} sanctioned entities")

    for entity in entities:
        name_aliases = entity.get("name_aliases", [])

        for name_alias in name_aliases:
            whole_name = name_alias.get("wholeName", "")
            if not whole_name:
                continue

            normalized_sanctioned = normalize_name(whole_name)

            # Exact match after normalization
            if normalized_customer == normalized_sanctioned:
                print(f"[AML] MATCH FOUND: '{customer_name}' matches sanctioned entity '{whole_name}'")
                return whole_name

    print(f"[AML] No match found for '{customer_name}'")
    return None


def perform_sanctions_check(customer_name: str) -> tuple[bool, Optional[str]]:
    """
    Perform full sanctions check: load file and check customer name.

    Args:
        customer_name: Name of customer to check

    Returns:
        Tuple (is_blocked, matched_name):
            - is_blocked: True if customer found in sanctions list
            - matched_name: Sanctioned entity wholeName if blocked, None otherwise
    """
    # Load sanctions data with thread-safe read
    sanctions_data = load_sanctions_file_safe(SANCTIONS_FILE_PATH)

    if not sanctions_data:
        print("[AML] ERROR: Cannot perform sanctions check - file unavailable")
        # Fail-open: Don't block customer if sanctions list unavailable
        # In production, this should fail-closed or trigger manual review
        return False, None

    # Check for match
    matched_name = check_customer_in_sanctions(customer_name, sanctions_data)

    if matched_name:
        return True, matched_name
    else:
        return False, None


if __name__ == "__main__":
    # Test script
    print("Testing sanctions checker...")

    # Test with known sanctioned name (if sanctions file exists)
    test_name = "Qusay Saddam Hussein Al-Tikriti"
    is_blocked, matched = perform_sanctions_check(test_name)
    print(f"Test result for '{test_name}': blocked={is_blocked}, matched='{matched}'")

    # Test with clean name
    test_name = "John Smith"
    is_blocked, matched = perform_sanctions_check(test_name)
    print(f"Test result for '{test_name}': blocked={is_blocked}, matched='{matched}'")
