import logging
from telethon import events, TelegramClient
from telethon.tl.types import User, PeerChannel, UpdateUserName, UpdateUser, UpdateUserStatus, UpdatePeerSettings, PeerUser
from ..database import Database
from ..config.config import Config
from ..utils.helpers import format_notification, format_scam_alert, format_user_left_notification

logger = logging.getLogger(__name__)

class EventHandlers:
    def __init__(self, client: TelegramClient, db: Database):
        self.client = client
        self.db = db

    async def check_name_changes(self, user: User):
        """Check for and report name changes"""
        try:
            if not user:
                return

            # First check if user is in any active monitored groups
            active_groups = self.db.get_user_active_groups(user.id)
            if not active_groups:
                logger.debug(f"User {user.id} is not in any active monitored groups, skipping name check")
                return

            current_data = {
                'first_name': user.first_name,
                'last_name': user.last_name or ""
            }

            # Get user data from database
            db_user = self.db.get_user(user.id)
            
            # Log the data for debugging
            logger.debug(f"DB user data: {db_user}")
            logger.debug(f"Current user data: {current_data}")

            # If user doesn't exist in database, register them
            if not db_user:
                self.db.register_user(
                    user_id=user.id,
                    first_name=user.first_name,
                    last_name=user.last_name or ""
                )
                logger.info(f"Registered new user {user.id} in database")
                return

            # Update the database with new data
            self.db.update_user(
                user_id=user.id,
                first_name=current_data['first_name'],
                last_name=current_data['last_name']
            )

            # Check if the user's name matches any scam names
            scam_names = self.db.get_scam_names()
            full_name = f"{current_data['first_name']} {current_data['last_name']}".strip().lower()
            
            if any(scam_name.lower() in full_name for scam_name in scam_names):
                group_names = [g['group_name'] for g in active_groups]
                scam_message = format_scam_alert(current_data, group_names)
                await self.send_to_admin(scam_message)
                logger.info(f"Sent scam alert for user {user.id}")

        except Exception as e:
            logger.error(f"Error checking name changes for user {user.id}: {str(e)}")

    async def send_to_admin(self, message: str):
        """Send notification to admin"""
        try:
            formatted_message = format_notification(message)
            await self.client.send_message(Config.ADMIN_ID, formatted_message)
            logger.info(f"Notification sent to admin: {message}")
        except Exception as e:
            logger.error(f"Error sending message to admin: {str(e)}")

    async def handle_group_events(self, event):
        """Handle group events where users might change names"""
        try:
            logger.debug(f"Received ChatAction event: {event.action_message}")
            # Get the actual group ID
            if isinstance(event.chat_id, PeerChannel):
                group_id = event.chat_id.channel_id
            else:
                group_id = event.chat_id

            logger.debug(f"Processing event for group ID: {group_id}")

            # Add group to monitored list if not already there
            if group_id not in Config.MONITORED_GROUPS:
                Config.MONITORED_GROUPS.append(group_id)
                logger.info(f"Added new group to monitoring: {group_id}")

                # Register group in database
                try:
                    chat = await event.get_chat()
                    group_name = getattr(chat, 'title', f'Group {group_id}')
                    self.db.register_group(group_id, group_name)
                except Exception as e:
                    logger.error(f"Error registering group {group_id}: {e}")

            # Handle user leaving
            if event.user_left or event.user_kicked:
                logger.debug(f"User left/kicked event detected")
                if hasattr(event, 'user_id') and event.user_id:
                    user_id = event.user_id
                    try:
                        chat = await event.get_chat()
                        group_name = getattr(chat, 'title', f'Group {group_id}')
                        
                        # Remove user from group in database
                        if self.db.remove_user_from_group(user_id, group_id):
                            # Get user info
                            user = await self.client.get_entity(user_id)
                            if user:
                                # Get user's remaining active groups
                                remaining_groups = self.db.get_user_active_groups(user_id)
                                remaining_group_names = [g['group_name'] for g in remaining_groups]
                                
                                # Format and send notification
                                message = format_user_left_notification(
                                    {'user_id': user_id, 'first_name': user.first_name, 'last_name': user.last_name},
                                    group_name,
                                    remaining_group_names
                                )
                                await self.client.send_message(
                                    Config.ADMIN_ID,
                                    message,
                                    parse_mode='markdown',
                                    link_preview=False
                                )
                    except Exception as e:
                        logger.error(f"Error handling user leaving: {str(e)}")
                return

            if event.user_joined or event.user_added:
                logger.debug(f"User joined/added event detected")
                # New user - add to database
                user = await event.get_user()
                if user:
                    logger.debug(f"Processing new user: {user.id}")
                    self.db.register_user(
                        user_id=user.id,
                        first_name=user.first_name,
                        last_name=user.last_name or "",
                        username=user.username or ""
                    )
                    # Add user to group in database
                    self.db.add_user_to_group(user.id, group_id)
                    logger.info(f"Added new user {user.id} to group {group_id}")
                return

            if hasattr(event, 'user_id') and event.user_id:
                logger.debug(f"Processing existing user event for user_id: {event.user_id}") 
                # Existing user - check for changes
                user = await event.get_user()
                if user:
                    await self.check_name_changes(user)
                    # Update last seen in group
                    self.db.add_user_to_group(user.id, group_id)

        except Exception as e:
            logger.error(f"Error in group event: {str(e)}", exc_info=True)

    def register_handlers(self):
        """Register all event handlers"""
        self.client.add_event_handler(self.handle_group_events, events.ChatAction())
        self.client.add_event_handler(self.check_name_changes, events.Raw(UpdateUserName))
        self.client.add_event_handler(self.check_name_changes, events.Raw(UpdateUser))
        self.client.add_event_handler(self.check_name_changes, events.Raw(UpdateUserStatus))
        self.client.add_event_handler(self.check_name_changes, events.Raw(UpdatePeerSettings)) 