"""
CORPCODE Storage Module
=======================
This module provides persistent storage and efficient retrieval of corporation codes
following Google ADK session/memory patterns for the DART Analytics system.

Features:
- In-memory caching with file-based persistence
- Fast search and retrieval of corporation codes
- Session management for tracking usage patterns
- Support for fuzzy matching and partial searches
"""

import json
import os
import pickle
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
import logging
from pathlib import Path
from functools import lru_cache

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class Corporation:
    """Data class for corporation information"""
    corp_code: str
    corp_name: str
    corp_eng_name: str
    stock_code: str
    modify_date: str
    last_accessed: Optional[datetime] = None
    access_count: int = 0


@dataclass
class SearchSession:
    """Data class for tracking search sessions"""
    session_id: str
    timestamp: datetime
    query: str
    results: List[str]
    success: bool


class CorpCodeStorage:
    """
    Manages persistent storage and retrieval of corporation codes.
    Implements caching and session tracking for improved performance.
    """
    
    def __init__(self, base_dir: str = None):
        """
        Initialize the CorpCodeStorage with specified base directory.
        
        Args:
            base_dir: Base directory for storage files. Defaults to dart_analytics directory.
        """
        if base_dir is None:
            base_dir = Path(__file__).parent.parent
        
        self.base_dir = Path(base_dir)
        self.storage_dir = self.base_dir / "storage"
        self.storage_dir.mkdir(exist_ok=True)
        
        # File paths
        self.db_path = self.storage_dir / "corpcode.db"
        self.cache_path = self.storage_dir / "corpcode_cache.pkl"
        self.session_path = self.storage_dir / "sessions.json"
        self.index_path = self.storage_dir / "corpcode_index.json"
        
        # Initialize database
        self._init_database()
        
        # Load cache
        self.cache = self._load_cache()
        
        # Load sessions
        self.sessions = self._load_sessions()
    
    def _init_database(self):
        """Initialize SQLite database for corporation data"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create corporations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS corporations (
                corp_code TEXT PRIMARY KEY,
                corp_name TEXT NOT NULL,
                corp_eng_name TEXT,
                stock_code TEXT,
                modify_date TEXT,
                last_accessed TEXT,
                access_count INTEGER DEFAULT 0
            )
        ''')
        
        # Create search index
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_corp_name 
            ON corporations(corp_name)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_stock_code 
            ON corporations(stock_code)
        ''')
        
        # Create sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS search_sessions (
                session_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                query TEXT NOT NULL,
                results TEXT NOT NULL,
                success INTEGER NOT NULL
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def _load_cache(self) -> Dict[str, Corporation]:
        """Load cache from pickle file"""
        if self.cache_path.exists():
            try:
                with open(self.cache_path, 'rb') as f:
                    return pickle.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
        return {}
    
    def _save_cache(self):
        """Save cache to pickle file"""
        try:
            with open(self.cache_path, 'wb') as f:
                pickle.dump(self.cache, f)
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")
    
    def _load_sessions(self) -> List[SearchSession]:
        """Load search sessions from JSON file"""
        if self.session_path.exists():
            try:
                with open(self.session_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    sessions = []
                    for session_data in data:
                        # Convert timestamp string to datetime if needed
                        if isinstance(session_data.get('timestamp'), str):
                            try:
                                session_data['timestamp'] = datetime.fromisoformat(session_data['timestamp'])
                            except:
                                session_data['timestamp'] = datetime.now()
                        sessions.append(SearchSession(**session_data))
                    return sessions
            except Exception as e:
                logger.warning(f"Failed to load sessions: {e}")
        return []
    
    def _save_sessions(self):
        """Save search sessions to JSON file"""
        try:
            sessions_data = []
            for session in self.sessions[-1000:]:  # Keep last 1000 sessions
                session_dict = asdict(session)
                # Handle both datetime objects and strings
                if hasattr(session.timestamp, 'isoformat'):
                    session_dict['timestamp'] = session.timestamp.isoformat()
                else:
                    session_dict['timestamp'] = str(session.timestamp)
                sessions_data.append(session_dict)
            
            with open(self.session_path, 'w', encoding='utf-8') as f:
                json.dump(sessions_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save sessions: {e}")
    
    def import_from_xml(self, xml_path: str, force_reload: bool = False) -> int:
        """
        Import corporation data from CORPCODE.xml file.
        
        Args:
            xml_path: Path to CORPCODE.xml file
            force_reload: Force reload even if data exists
            
        Returns:
            Number of corporations imported
        """
        # Check if data already exists
        if not force_reload:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM corporations")
            count = cursor.fetchone()[0]
            conn.close()
            
            if count > 0:
                logger.info(f"Data already exists ({count} corporations). Use force_reload=True to reimport.")
                return 0
        
        # Parse XML
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Clear existing data if force reload
        if force_reload:
            cursor.execute("DELETE FROM corporations")
        
        # Import data
        count = 0
        for corp in root.findall('.//list'):
            corp_code = corp.findtext('corp_code', '').strip()
            corp_name = corp.findtext('corp_name', '').strip()
            corp_eng_name = corp.findtext('corp_eng_name', '').strip()
            stock_code = corp.findtext('stock_code', '').strip()
            modify_date = corp.findtext('modify_date', '').strip()
            
            if corp_code and corp_name:
                cursor.execute('''
                    INSERT OR REPLACE INTO corporations 
                    (corp_code, corp_name, corp_eng_name, stock_code, modify_date)
                    VALUES (?, ?, ?, ?, ?)
                ''', (corp_code, corp_name, corp_eng_name, stock_code, modify_date))
                count += 1
        
        conn.commit()
        conn.close()
        
        # Clear cache after import
        self.cache.clear()
        self._save_cache()
        
        logger.info(f"Imported {count} corporations from {xml_path}")
        return count
    
    @lru_cache(maxsize=1000)
    def get_corp_code(self, corp_name: str) -> Optional[str]:
        """
        Get corporation code by exact name match.
        
        Args:
            corp_name: Corporation name to search
            
        Returns:
            Corporation code if found, None otherwise
        """
        # Check cache first
        cache_key = f"exact_{corp_name}"
        if cache_key in self.cache:
            corp = self.cache[cache_key]
            self._update_access_stats(corp.corp_code)
            return corp.corp_code
        
        # Query database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT corp_code, corp_name, corp_eng_name, stock_code, modify_date
            FROM corporations
            WHERE corp_name = ?
        ''', (corp_name,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            corp = Corporation(*result)
            self.cache[cache_key] = corp
            self._save_cache()
            self._update_access_stats(corp.corp_code)
            self._record_session(corp_name, [corp.corp_code], True)
            return corp.corp_code
        
        self._record_session(corp_name, [], False)
        return None
    
    def search_corporations(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        """
        Search corporations with partial matching.
        
        Args:
            query: Search query (partial name or code)
            limit: Maximum number of results
            
        Returns:
            List of matching corporations
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Search by name or code
        cursor.execute('''
            SELECT corp_code, corp_name, corp_eng_name, stock_code, modify_date
            FROM corporations
            WHERE corp_name LIKE ? OR corp_code LIKE ? OR stock_code LIKE ?
            ORDER BY 
                CASE 
                    WHEN corp_name = ? THEN 1
                    WHEN corp_name LIKE ? THEN 2
                    ELSE 3
                END,
                access_count DESC
            LIMIT ?
        ''', (f'%{query}%', f'%{query}%', f'%{query}%', query, f'{query}%', limit))
        
        results = []
        corp_codes = []
        
        for row in cursor.fetchall():
            corp = Corporation(*row)
            results.append({
                'corp_code': corp.corp_code,
                'corp_name': corp.corp_name,
                'corp_eng_name': corp.corp_eng_name,
                'stock_code': corp.stock_code,
                'modify_date': corp.modify_date
            })
            corp_codes.append(corp.corp_code)
        
        conn.close()
        
        # Record session
        self._record_session(query, corp_codes, len(results) > 0)
        
        return results
    
    def get_corporation_info(self, corp_code: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed corporation information by code.
        
        Args:
            corp_code: Corporation code
            
        Returns:
            Corporation information dictionary if found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT corp_code, corp_name, corp_eng_name, stock_code, 
                   modify_date, last_accessed, access_count
            FROM corporations
            WHERE corp_code = ?
        ''', (corp_code,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            self._update_access_stats(corp_code)
            return {
                'corp_code': result[0],
                'corp_name': result[1],
                'corp_eng_name': result[2],
                'stock_code': result[3],
                'modify_date': result[4],
                'last_accessed': result[5],
                'access_count': result[6]
            }
        
        return None
    
    def _update_access_stats(self, corp_code: str):
        """Update access statistics for a corporation"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE corporations
            SET last_accessed = ?, access_count = access_count + 1
            WHERE corp_code = ?
        ''', (datetime.now().isoformat(), corp_code))
        
        conn.commit()
        conn.close()
    
    def _record_session(self, query: str, results: List[str], success: bool):
        """Record a search session"""
        session = SearchSession(
            session_id=f"{datetime.now().timestamp()}_{query[:10]}",
            timestamp=datetime.now(),
            query=query,
            results=results[:10],  # Store only first 10 results
            success=success
        )
        
        self.sessions.append(session)
        
        # Save to database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO search_sessions (session_id, timestamp, query, results, success)
            VALUES (?, ?, ?, ?, ?)
        ''', (session.session_id, session.timestamp.isoformat(), 
              session.query, json.dumps(session.results), int(session.success)))
        
        conn.commit()
        conn.close()
        
        # Save sessions to file
        self._save_sessions()
    
    def get_popular_corporations(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get most frequently accessed corporations"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT corp_code, corp_name, stock_code, access_count
            FROM corporations
            WHERE access_count > 0
            ORDER BY access_count DESC
            LIMIT ?
        ''', (limit,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'corp_code': row[0],
                'corp_name': row[1],
                'stock_code': row[2],
                'access_count': row[3]
            })
        
        conn.close()
        return results
    
    def get_recent_searches(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent search sessions"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT timestamp, query, results, success
            FROM search_sessions
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'timestamp': row[0],
                'query': row[1],
                'results': json.loads(row[2]),
                'success': bool(row[3])
            })
        
        conn.close()
        return results
    
    def export_index(self):
        """Export a lightweight index for quick lookups"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT corp_code, corp_name, stock_code
            FROM corporations
            WHERE stock_code != '' AND stock_code != ' '
        ''')
        
        index = {}
        for row in cursor.fetchall():
            corp_code, corp_name, stock_code = row
            index[corp_name] = {
                'code': corp_code,
                'stock': stock_code
            }
        
        conn.close()
        
        # Save index
        with open(self.index_path, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Exported index with {len(index)} entries to {self.index_path}")
        return len(index)
    
    def clear_cache(self):
        """Clear in-memory cache"""
        self.cache.clear()
        self._save_cache()
        self.get_corp_code.cache_clear()
        logger.info("Cache cleared")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get storage statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Total corporations
        cursor.execute("SELECT COUNT(*) FROM corporations")
        total_corps = cursor.fetchone()[0]
        
        # Corporations with stock codes
        cursor.execute("SELECT COUNT(*) FROM corporations WHERE stock_code != '' AND stock_code != ' '")
        listed_corps = cursor.fetchone()[0]
        
        # Total searches
        cursor.execute("SELECT COUNT(*) FROM search_sessions")
        total_searches = cursor.fetchone()[0]
        
        # Successful searches
        cursor.execute("SELECT COUNT(*) FROM search_sessions WHERE success = 1")
        successful_searches = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_corporations': total_corps,
            'listed_corporations': listed_corps,
            'total_searches': total_searches,
            'successful_searches': successful_searches,
            'success_rate': successful_searches / total_searches if total_searches > 0 else 0,
            'cache_size': len(self.cache),
            'storage_size_mb': {
                'database': self.db_path.stat().st_size / 1024 / 1024 if self.db_path.exists() else 0,
                'cache': self.cache_path.stat().st_size / 1024 / 1024 if self.cache_path.exists() else 0,
                'sessions': self.session_path.stat().st_size / 1024 / 1024 if self.session_path.exists() else 0
            }
        }


# Singleton instance
_storage_instance = None


def get_storage() -> CorpCodeStorage:
    """Get or create the singleton storage instance"""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = CorpCodeStorage()
    return _storage_instance


def initialize_storage(xml_path: str = None, force_reload: bool = False):
    """
    Initialize the storage with CORPCODE.xml data.
    
    Args:
        xml_path: Path to CORPCODE.xml file. If None, uses default location.
        force_reload: Force reload even if data exists
    """
    storage = get_storage()
    
    if xml_path is None:
        xml_path = Path(__file__).parent.parent / "CORPCODE.xml"
    
    if Path(xml_path).exists():
        count = storage.import_from_xml(xml_path, force_reload)
        if count > 0:
            storage.export_index()
        return count
    else:
        logger.error(f"CORPCODE.xml not found at {xml_path}")
        return 0


def quick_search(query: str) -> List[Dict[str, str]]:
    """Quick search for corporations"""
    storage = get_storage()
    return storage.search_corporations(query)


def get_corp_code_quick(corp_name: str) -> Optional[str]:
    """Quick lookup for corporation code"""
    storage = get_storage()
    return storage.get_corp_code(corp_name)