import logging
from telethon import events, TelegramClient
from telethon.tl.types import User, PeerChannel
from src.database import Database
from src.config.config import Config
from src.utils.helpers import format_notification

logger = logging.getLogger(__name__)

class CommandHandlers:
    def __init__(self, client: TelegramClient, db: Database):
        self.client = client
        self.db = db

    async def start_command(self, event):
        """Initialize tracking in a group"""
        try:
            logger.info(f"Received /start command from user {event.sender_id} in chat {event.chat_id}")
            
            # Check if the command is used in a group
            if not event.is_group:
                logger.info(f"Command used in non-group chat: {event.chat_id}")
                await event.reply("❌ This command can only be used in groups.")
                return

            # Get group information
            try:
                chat = await event.get_chat()
                group_id = event.chat_id.channel_id if isinstance(event.chat_id, PeerChannel) else event.chat_id
                group_name = getattr(chat, 'title', f'Group {group_id}')
                
                logger.info(f"Processing group: {group_name} ({group_id})")
                logger.info(f"Group type: {type(chat)}")
                logger.info(f"Group attributes: {dir(chat)}")

                # Check if user has admin rights
                try:
                    participant = await self.client.get_permissions(event.sender_id, chat)
                    if not participant.is_admin:
                        logger.info(f"User {event.sender_id} is not an admin in group {group_name}")
                        await event.reply("❌ Only group administrators can use this command.")
                        return
                except Exception as e:
                    logger.error(f"Error checking user permissions: {str(e)}", exc_info=True)
                    await event.reply("❌ Error checking permissions. Please make sure the bot has admin rights.")
                    return

                # Check if bot has admin rights
                try:
                    bot_participant = await self.client.get_permissions(self.client.me.id, chat)
                    if not bot_participant.is_admin:
                        logger.info(f"Bot is not an admin in group {group_name}")
                        await event.reply("❌ The bot needs to be an administrator to track name changes.")
                        return
                except Exception as e:
                    logger.error(f"Error checking bot permissions: {str(e)}", exc_info=True)
                    await event.reply("❌ Error checking bot permissions. Please make sure the bot has admin rights.")
                    return

                # Register the group in database
                if not self.db.register_group(group_id, group_name):
                    logger.error(f"Failed to register group {group_name} ({group_id}) in database")
                    await event.reply("❌ Error registering group in database. Please try again.")
                    return

                # Add to monitored groups if not already there
                if group_id not in Config.MONITORED_GROUPS:
                    Config.MONITORED_GROUPS.append(group_id)
                    logger.info(f"Added group to monitoring: {group_name} ({group_id})")

                # Load all current group members into database
                count = 0
                errors = 0
                error_details = []
                
                try:
                    logger.info(f"Fetching participants for group {group_name}")
                    participants = await self.client.get_participants(chat)
                    total_participants = len(participants)
                    logger.info(f"Found {total_participants} participants in group {group_name}")
                    
                    for user in participants:
                        if isinstance(user, User):
                            try:
                                existing_user = self.db.get_user(user.id)
                                if not existing_user:
                                    first_name = user.first_name or "Unknown"
                                    last_name = user.last_name or ""
                                    username = user.username or ""
                                    
                                    self.db.register_user(
                                        user_id=user.id,
                                        first_name=first_name,
                                        last_name=last_name,
                                        username=username
                                    )
                                    count += 1
                                
                                self.db.add_user_to_group(user.id, group_id)
                                
                                if count % 10 == 0:
                                    logger.info(f"Processed {count}/{total_participants} users in group {group_name}")
                                    
                            except Exception as e:
                                errors += 1
                                error_msg = f"User {user.id}: {str(e)}"
                                error_details.append(error_msg)
                                logger.error(error_msg)
                                
                except Exception as e:
                    logger.error(f"Error processing users in group {group_name}: {str(e)}", exc_info=True)
                    await event.reply("⚠️ Warning: Error processing users. Tracking is still active.")
                    return

                # Send confirmation message
                status_msg = [
                    f"✅ Name tracking activated!",
                    f"Group: {group_name}",
                    f"ID: {group_id}",
                    f"Added {count} users to tracking."
                ]
                
                if errors > 0:
                    status_msg.append(f"⚠️ {errors} users could not be processed.")
                    if error_details:
                        status_msg.append("\nError details (first 3):")
                        for detail in error_details[:3]:
                            status_msg.append(f"• {detail}")
                        if len(error_details) > 3:
                            status_msg.append(f"... and {len(error_details) - 3} more errors")
                
                status_msg.append("\nI'll report name changes to the admin.")
                await event.reply("\n".join(status_msg))
                logger.info(f"Successfully activated tracking for group {group_name}")

            except Exception as e:
                logger.error(f"Error getting group information: {str(e)}", exc_info=True)
                await event.reply("❌ Error getting group information. Please try again.")    

        except Exception as e:
            logger.error(f"Error in start command: {str(e)}", exc_info=True)
            await event.reply("❌ An unexpected error occurred. Please try again.")

    async def status_command(self, event):
        """Report current tracking status"""
        try:
            users = self.db.get_all_users()
            total_groups = len(set(group['group_id'] for user in users for group in user.get('groups', [])))

            # Get group names for monitored groups
            monitored_groups_info = []
            for group_id in Config.MONITORED_GROUPS:
                try:
                    chat = await self.client.get_entity(group_id)
                    group_name = getattr(chat, 'title', f'Group {group_id}')
                    monitored_groups_info.append(f"• {group_name}")
                except Exception as e:
                    logger.error(f"Error getting group info for {group_id}: {e}")
                    monitored_groups_info.append(f"• Group {group_id}")

            status_msg = [
                "📊 Status",
                f"👤 Users: {len(users)}",
                f"👥 Groups: {len(Config.MONITORED_GROUPS)}",
                "",
                "🎯 Monitored:"
            ]

            if monitored_groups_info:
                status_msg.extend(monitored_groups_info)
            else:
                status_msg.append("No groups monitored")

            await event.reply("\n".join(status_msg))
        except Exception as e:
            logger.error(f"Error in status command: {str(e)}")

    async def scan_command(self, event):
        """Trigger immediate scan of all groups"""
        try:
            if event.sender_id == Config.ADMIN_ID:
                await event.reply("🔄 Starting manual scan of all monitored groups...")      
                for group_id in Config.MONITORED_GROUPS:
                    try:
                        count = 0
                        async for user in self.client.iter_participants(group_id):
                            if isinstance(user, User):
                                await self.check_name_changes(user)
                                count += 1
                        logger.info(f"Scanned {count} users in group {group_id}")
                    except Exception as e:
                        logger.error(f"Error scanning group {group_id}: {str(e)}")
                await event.reply("✅ Manual scan completed!")
            else:
                await event.reply("⛔ Only admin can trigger manual scans")
        except Exception as e:
            logger.error(f"Error in scan command: {str(e)}")

    def register_handlers(self):
        """Register all command handlers"""
        logger.info("Registering command handlers")
        self.client.add_event_handler(self.start_command, events.NewMessage(pattern='/start'))
        self.client.add_event_handler(self.status_command, events.NewMessage(pattern='/status'))
        self.client.add_event_handler(self.scan_command, events.NewMessage(pattern='/scan'))
        logger.info("Command handlers registered successfully") 