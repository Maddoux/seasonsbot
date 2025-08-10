import json
import os
from datetime import datetime
from typing import Dict, List, Optional
import aiofiles

class LicenseManager:
    def __init__(self, db_path: str = "licenses.json"):
        self.db_path = db_path
        self._ensure_db_exists()
    
    def _ensure_db_exists(self):
        """Ensure the license database file exists with proper structure"""
        if not os.path.exists(self.db_path):
            initial_data = {
                "user_licenses": {},  # user_id -> license_info
                "license_users": {},  # license -> user_info
                "license_history": []  # history of license changes
            }
            with open(self.db_path, 'w') as f:
                json.dump(initial_data, f, indent=2)
    
    async def load_data(self) -> dict:
        """Load data from the JSON file"""
        try:
            async with aiofiles.open(self.db_path, 'r') as f:
                content = await f.read()
                return json.loads(content)
        except Exception:
            return {"user_licenses": {}, "license_users": {}, "license_history": []}
    
    async def save_data(self, data: dict):
        """Save data to the JSON file"""
        async with aiofiles.open(self.db_path, 'w') as f:
            await f.write(json.dumps(data, indent=2, default=str))
    
    async def add_license(self, user_id: int, license_key: str, moderator_id: int, note: str = "") -> bool:
        """Add or update a license for a user"""
        data = await self.load_data()
        
        user_id_str = str(user_id)
        
        # Check if license is already assigned to another user
        if license_key in data["license_users"]:
            existing_user = data["license_users"][license_key]["user_id"]
            if existing_user != user_id:
                return False  # License already assigned to someone else
        
        # Remove old license if user had one
        if user_id_str in data["user_licenses"]:
            old_license = data["user_licenses"][user_id_str]["license"]
            if old_license in data["license_users"]:
                del data["license_users"][old_license]
        
        # Add new license
        license_info = {
            "license": license_key,
            "user_id": user_id,
            "added_by": moderator_id,
            "added_at": datetime.now().isoformat(),
            "note": note
        }
        
        data["user_licenses"][user_id_str] = license_info
        data["license_users"][license_key] = license_info
        
        # Add to history
        history_entry = {
            "action": "add",
            "user_id": user_id,
            "license": license_key,
            "moderator_id": moderator_id,
            "timestamp": datetime.now().isoformat(),
            "note": note
        }
        data["license_history"].append(history_entry)
        
        await self.save_data(data)
        return True
    
    async def remove_license(self, user_id: int, moderator_id: int, reason: str = "") -> bool:
        """Remove a license from a user"""
        data = await self.load_data()
        
        user_id_str = str(user_id)
        
        if user_id_str not in data["user_licenses"]:
            return False
        
        license_info = data["user_licenses"][user_id_str]
        license_key = license_info["license"]
        
        # Remove from both mappings
        del data["user_licenses"][user_id_str]
        if license_key in data["license_users"]:
            del data["license_users"][license_key]
        
        # Add to history
        history_entry = {
            "action": "remove",
            "user_id": user_id,
            "license": license_key,
            "moderator_id": moderator_id,
            "timestamp": datetime.now().isoformat(),
            "reason": reason
        }
        data["license_history"].append(history_entry)
        
        await self.save_data(data)
        return True
    
    async def get_user_license(self, user_id: int) -> Optional[dict]:
        """Get the license info for a user"""
        data = await self.load_data()
        user_id_str = str(user_id)
        
        return data["user_licenses"].get(user_id_str)
    
    async def get_license_user(self, license_key: str) -> Optional[dict]:
        """Get the user info for a license"""
        data = await self.load_data()
        
        return data["license_users"].get(license_key)
    
    async def search_licenses(self, query: str) -> List[dict]:
        """Search for licenses or users by partial match"""
        data = await self.load_data()
        results = []
        
        query_lower = query.lower()
        
        # Search in licenses
        for license_key, info in data["license_users"].items():
            if query_lower in license_key.lower():
                results.append({
                    "type": "license",
                    "license": license_key,
                    "user_id": info["user_id"],
                    "added_at": info["added_at"],
                    "note": info.get("note", "")
                })
        
        return results
    
    async def get_license_history(self, user_id: int = None, license_key: str = None, limit: int = 50) -> List[dict]:
        """Get license history, optionally filtered by user or license"""
        data = await self.load_data()
        
        history = data["license_history"]
        
        # Filter if needed
        if user_id is not None:
            history = [h for h in history if h["user_id"] == user_id]
        
        if license_key is not None:
            history = [h for h in history if h["license"] == license_key]
        
        # Sort by timestamp (newest first) and limit
        history = sorted(history, key=lambda x: x["timestamp"], reverse=True)
        
        return history[:limit]
