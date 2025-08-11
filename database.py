import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import aiofiles

class DatabaseManager:
    def __init__(self, db_path: str = "warnings.json"):
        self.db_path = db_path
        self._ensure_db_exists()
    
    def _ensure_db_exists(self):
        """Ensure the database file exists with proper structure"""
        if not os.path.exists(self.db_path):
            initial_data = {
                "users": {},
                "warnings": {},
                "bans": {}
            }
            with open(self.db_path, 'w') as f:
                json.dump(initial_data, f, indent=2)
    
    async def load_data(self) -> dict:
        """Load data from the JSON file"""
        try:
            async with aiofiles.open(self.db_path, 'r') as f:
                content = await f.read()
                data = json.loads(content)
                
                # Ensure all required keys exist
                if "users" not in data:
                    data["users"] = {}
                if "warnings" not in data:
                    data["warnings"] = {}
                if "bans" not in data:
                    data["bans"] = {}
                
                return data
        except Exception as e:
            print(f"Error loading database: {e}")
            # Return default structure if file doesn't exist or is corrupted
            return {"users": {}, "warnings": {}, "bans": {}}
    
    async def save_data(self, data: dict):
        """Save data to the JSON file"""
        async with aiofiles.open(self.db_path, 'w') as f:
            await f.write(json.dumps(data, indent=2, default=str))
    
    async def _get_next_warning_id(self, data: dict) -> str:
        """Get the next sequential warning ID"""
        # Find the highest existing ID number
        max_id = 0
        for warning_id in data["warnings"]:
            try:
                # Extract number from warning ID (handle both old format and new format)
                if warning_id.isdigit():
                    id_num = int(warning_id)
                else:
                    # Skip old format IDs that contain underscores
                    continue
                max_id = max(max_id, id_num)
            except (ValueError, AttributeError):
                continue
        
        return str(max_id + 1)

    async def add_warning(self, user_id: int, moderator_id: int, violation_type: str, 
                         points: int, clips: List[str], reason: str) -> dict:
        """Add a warning to the database"""
        data = await self.load_data()
        
        user_id_str = str(user_id)
        # Use sequential numbering for warning IDs
        warning_id = await self._get_next_warning_id(data)
        
        # Initialize user if not exists
        if user_id_str not in data["users"]:
            data["users"][user_id_str] = {
                "total_points": 0,
                "warnings": [],
                "bans": []
            }
        
        # Create warning record
        warning = {
            "id": warning_id,
            "user_id": user_id,
            "moderator_id": moderator_id,
            "violation_type": violation_type,
            "points": points,
            "clips": clips,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
            "expires_at": self._calculate_expiry(violation_type)
        }
        
        # Add to warnings collection
        data["warnings"][warning_id] = warning
        
        # Update user record
        data["users"][user_id_str]["warnings"].append(warning_id)
        data["users"][user_id_str]["total_points"] += points
        
        await self.save_data(data)
        return warning
    
    async def get_user_points(self, user_id: int) -> int:
        """Get current points for a user (excluding expired warnings)"""
        data = await self.load_data()
        user_id_str = str(user_id)
        
        # Ensure users key exists and user exists in users
        if "users" not in data:
            data["users"] = {}
            await self.save_data(data)
        
        if user_id_str not in data["users"]:
            return 0
        
        total_points = 0
        now = datetime.now()
        
        for warning_id in data["users"][user_id_str]["warnings"]:
            if warning_id in data["warnings"]:
                warning = data["warnings"][warning_id]
                expires_at = datetime.fromisoformat(warning["expires_at"])
                
                if now < expires_at:
                    # Check if warning was manually removed
                    if not warning.get("removed", False):
                        total_points += warning["points"]
        
        return total_points
    
    async def get_user_warnings(self, user_id: int) -> List[dict]:
        """Get all active (non-expired) warnings for a user"""
        data = await self.load_data()
        user_id_str = str(user_id)
        
        # Ensure users key exists and user exists in users
        if "users" not in data:
            data["users"] = {}
            await self.save_data(data)
        
        if user_id_str not in data["users"]:
            return []
        
        warnings = []
        now = datetime.now()
        
        for warning_id in data["users"][user_id_str]["warnings"]:
            if warning_id in data["warnings"]:
                warning = data["warnings"][warning_id]
                expires_at = datetime.fromisoformat(warning["expires_at"])
                
                if now < expires_at:
                    # Check if warning was manually removed
                    if not warning.get("removed", False):
                        warnings.append(warning)
        
        return sorted(warnings, key=lambda x: x["timestamp"], reverse=True)
    
    def _calculate_expiry(self, violation_type: str) -> str:
        """Calculate when a warning expires based on violation grade"""
        grade_map = {
            "RDM / VDM": 1,
            "Mass RDM / Mass VDM": 2,
            "NLR": 1,
            "FailRP (NVL, GP>RP, LQRP, etc.)": 1,
            "Cop Baiting": 1,
            "NITRP": 3,
            "Metagaming": 1,
            "Power Gaming": 3,
            "Lack of Initiation": 1,
            "Greenzone Violations": 1,
            "Mic / Chat Spam": 1,
            "LTAP (Avoiding Punishment)": 2,
            "LTARP (Avoiding RP)": 3,
            "Lying to Staff": 3,
            "Racism / Hate Speech": 3,
            "Erotic Roleplay (ERP)": 3
        }
        
        grade = grade_map.get(violation_type, 1)
        now = datetime.now()
        
        if grade == 1:
            expiry = now + timedelta(weeks=2)
        elif grade == 2:
            expiry = now + timedelta(weeks=4)
        else:  # grade == 3
            expiry = now + timedelta(weeks=8)
        
        return expiry.isoformat()
    
    async def add_ban_request(self, user_id: int, total_points: int, action: str, 
                             message_id: int) -> dict:
        """Add a ban request to the database"""
        data = await self.load_data()
        
        ban_request = {
            "user_id": user_id,
            "total_points": total_points,
            "action": action,
            "message_id": message_id,
            "timestamp": datetime.now().isoformat(),
            "status": "pending"
        }
        
        data["bans"][str(message_id)] = ban_request
        await self.save_data(data)
        return ban_request
    
    async def complete_ban_request(self, message_id: int, moderator_id: int) -> dict:
        """Mark a ban request as completed"""
        data = await self.load_data()
        
        if str(message_id) in data["bans"]:
            data["bans"][str(message_id)]["status"] = "completed"
            data["bans"][str(message_id)]["completed_by"] = moderator_id
            data["bans"][str(message_id)]["completed_at"] = datetime.now().isoformat()
            await self.save_data(data)
            return data["bans"][str(message_id)]
        
        return None
    
    async def remove_warning(self, warning_id: str, moderator_id: int, reason: str = "Manual removal") -> bool:
        """Mark a warning as removed (expired) without deleting it"""
        data = await self.load_data()
        
        if warning_id in data["warnings"]:
            # Mark as expired by setting expiry to past date
            data["warnings"][warning_id]["removed"] = True
            data["warnings"][warning_id]["removed_by"] = moderator_id
            data["warnings"][warning_id]["removed_at"] = datetime.now().isoformat()
            data["warnings"][warning_id]["removal_reason"] = reason
            data["warnings"][warning_id]["expires_at"] = (datetime.now() - timedelta(days=1)).isoformat()
            
            await self.save_data(data)
            return True
        
        return False
    
    async def remove_user_warnings(self, user_id: int, moderator_id: int, reason: str = "Manual removal") -> int:
        """Remove all active warnings for a user and return count of removed warnings"""
        data = await self.load_data()
        user_id_str = str(user_id)
        
        # Ensure users key exists and user exists in users
        if "users" not in data:
            data["users"] = {}
            await self.save_data(data)
        
        if user_id_str not in data["users"]:
            return 0
        
        removed_count = 0
        now = datetime.now()
        
        for warning_id in data["users"][user_id_str]["warnings"]:
            if warning_id in data["warnings"]:
                warning = data["warnings"][warning_id]
                expires_at = datetime.fromisoformat(warning["expires_at"])
                
                # Only remove active warnings
                if now < expires_at and not warning.get("removed", False):
                    data["warnings"][warning_id]["removed"] = True
                    data["warnings"][warning_id]["removed_by"] = moderator_id
                    data["warnings"][warning_id]["removed_at"] = now.isoformat()
                    data["warnings"][warning_id]["removal_reason"] = reason
                    data["warnings"][warning_id]["expires_at"] = (now - timedelta(days=1)).isoformat()
                    removed_count += 1
        
        await self.save_data(data)
        return removed_count
    
    async def find_warnings_by_user(self, user_id: int, limit: int = 100) -> List[dict]:
        """Find recent warnings for a user (including removed ones for staff review)"""
        data = await self.load_data()
        user_id_str = str(user_id)
        
        # Ensure users key exists and user exists in users
        if "users" not in data:
            data["users"] = {}
            await self.save_data(data)
        
        if user_id_str not in data["users"]:
            return []
        
        warnings = []
        for warning_id in data["users"][user_id_str]["warnings"]:
            if warning_id in data["warnings"]:
                warnings.append(data["warnings"][warning_id])
        
        return sorted(warnings, key=lambda x: x["timestamp"], reverse=True)[:limit]
