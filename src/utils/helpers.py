import gc
import logging
from datetime import datetime
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def optimize_memory():
    """Optimize memory usage"""
    gc.collect()
    if hasattr(gc, 'collect_generations'):
        gc.collect_generations()

def format_notification(message: str) -> str:
    """Format notification message with consistent styling"""
    return (
        "🔔 Name Change Notification\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{message}\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

def format_scam_alert(user_data: Dict[str, Any], group_names: List[str]) -> str:
    """Format scam alert message"""
    return (
        "⚠️ Potential Scam Alert!\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 User: {user_data['first_name']} {user_data['last_name'] or ''}\n"
        f"👥 Groups: {', '.join(group_names) if group_names else 'None'}\n"
    )

def format_user_left_notification(user_data: Dict[str, Any], group_name: str, remaining_groups: List[str]) -> str:
    """Format user left notification"""
    chat_link = f"tg://user?id={user_data['user_id']}"
    message = (
        "👋 User Left Group Notification\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 User: {user_data['first_name']} {user_data['last_name'] or ''}\n"
        f"🚪 Left Group: {group_name}\n"
        f"💬 [Click to Chat]({chat_link})\n"
    )

    if remaining_groups:
        message += f"\n📋 Still in groups:\n• " + "\n• ".join(remaining_groups)
    else:
        message += "\n⚠️ User is no longer in any monitored groups"

    return message

def get_current_time() -> str:
    """Get current time in formatted string"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S") 