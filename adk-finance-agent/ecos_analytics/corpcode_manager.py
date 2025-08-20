"""
Corporation Code Manager for ECOS Analytics
=============================================
This module provides corporation code management functions for the ECOS Analytics agent.
It leverages the DART analytics storage system for corporation data.
"""

import sys
import os
from pathlib import Path
from typing import Dict, List, Optional, Any

# Add the parent directory to sys.path to import dart_analytics
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

try:
    from dart_analytics.sub_functions.corpcode_storage import get_storage, initialize_storage
except ImportError as e:
    print(f"Warning: Could not import dart_analytics storage: {e}")
    print("Corporation code functionality will be limited.")
    _storage = None
else:
    # Initialize storage if XML file exists
    xml_path = parent_dir / "dart_analytics" / "CORPCODE.xml"
    if xml_path.exists():
        initialize_storage(str(xml_path))
    _storage = get_storage()


def get_corp_code(corp_name: str) -> Optional[str]:
    """
    Get corporation code by exact name match.
    
    Args:
        corp_name: Corporation name to search
        
    Returns:
        Corporation code if found, None otherwise
    """
    if _storage is None:
        print(f"Storage not available. Cannot get corp code for: {corp_name}")
        return None
    
    try:
        return _storage.get_corp_code(corp_name)
    except Exception as e:
        print(f"Error getting corp code for {corp_name}: {e}")
        return None


def search_corporations(query: str, limit: int = 10) -> List[Dict[str, str]]:
    """
    Search corporations with partial matching.
    
    Args:
        query: Search query (partial name or code)
        limit: Maximum number of results
        
    Returns:
        List of matching corporations
    """
    if _storage is None:
        print(f"Storage not available. Cannot search for: {query}")
        return []
    
    try:
        return _storage.search_corporations(query, limit)
    except Exception as e:
        print(f"Error searching corporations for {query}: {e}")
        return []


def get_corp_info(corp_code: str) -> Optional[Dict[str, Any]]:
    """
    Get detailed corporation information by code.
    
    Args:
        corp_code: Corporation code
        
    Returns:
        Corporation information dictionary if found
    """
    if _storage is None:
        print(f"Storage not available. Cannot get info for corp code: {corp_code}")
        return None
    
    try:
        return _storage.get_corporation_info(corp_code)
    except Exception as e:
        print(f"Error getting corp info for {corp_code}: {e}")
        return None


def get_listed_companies(limit: int = 100) -> List[Dict[str, Any]]:
    """
    Get list of listed companies (companies with stock codes).
    
    Args:
        limit: Maximum number of results
        
    Returns:
        List of listed companies
    """
    if _storage is None:
        print("Storage not available. Cannot get listed companies.")
        return []
    
    try:
        # Search for companies with stock codes
        results = _storage.search_corporations("", limit * 2)  # Get more to filter
        
        # Filter to only include companies with stock codes
        listed_companies = []
        for company in results:
            if company.get('stock_code') and company['stock_code'].strip():
                listed_companies.append(company)
                if len(listed_companies) >= limit:
                    break
        
        return listed_companies
    except Exception as e:
        print(f"Error getting listed companies: {e}")
        return []


def get_storage_statistics() -> Dict[str, Any]:
    """
    Get storage statistics for debugging and monitoring.
    
    Returns:
        Storage statistics dictionary
    """
    if _storage is None:
        return {"error": "Storage not available"}
    
    try:
        return _storage.get_statistics()
    except Exception as e:
        return {"error": f"Error getting statistics: {e}"}