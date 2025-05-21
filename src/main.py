import asyncio
import logging
from telethon import TelegramClient, events
from telethon.tl.types import User, UpdateUser, UpdateUserName, PeerChannel, UpdateChannelParticipant
from src.config.config import Config
from src.database import Database
import os
from aiohttp import web

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class NameChangeBot:
    def __init__(self):
        # Initialize client with bot token
        self.client = TelegramClient(
            Config.SESSION_NAME,
            Config.API_ID,
            Config.API_HASH
        ).start(bot_token=Config.BOT_TOKEN)
        
        # Initialize database
        self.db = Database()
        
        # Initialize web app for Render
        self.app = web.Application()
        self.app.router.add_get('/', self.handle_web_request)

    async def handle_web_request(self, request):
        """Handle web requests for Render"""
        return web.Response(text="Bot is running!")

    async def start_web_server(self):
        """Start the web server for Render"""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', int(os.getenv('PORT', 8080)))
        await site.start()
        logger.info(f"Web server started on port {os.getenv('PORT', 8080)}")

    async def handle_name_change(self, event):
        """Handle user name changes"""
        try:
            logger.info(f"Received update event: {type(event)}")
            
            # Handle different update types
            if isinstance(event, UpdateUser):
                user = event.user
                if not isinstance(user, User):
                    logger.warning(f"UpdateUser event contains non-User object: {type(user)}")
                    return
                logger.info(f"Processing UpdateUser event for user {user.id}")
            elif isinstance(event, UpdateUserName):
                # For UpdateUserName, we need to fetch the user
                try:
                    user = await self.client.get_entity(event.user_id)
                    if not isinstance(user, User):
                        logger.warning(f"Could not get User object for UpdateUserName event: {event.user_id}")
                        return
                    logger.info(f"Processing UpdateUserName event for user {user.id}")
                except Exception as e:
                    logger.error(f"Error fetching user for UpdateUserName event: {str(e)}")
                    return
            elif isinstance(event, UpdateChannelParticipant):
                logger.info(f"Processing UpdateChannelParticipant event: {event}")
                try:
                    user = await self.client.get_entity(event.user_id)
                    if isinstance(user, User):
                        logger.info(f"User {user.id} updated in channel: {event.channel_id}")
                        # Create a synthetic UpdateUser event
                        update_event = UpdateUser(user=user)
                        await self.handle_name_change(update_event)
                except Exception as e:
                    logger.error(f"Error processing UpdateChannelParticipant: {str(e)}")
                return
            else:
                logger.debug(f"Ignoring unsupported update type: {type(event)}")
                return

            # Get existing user data
            existing_user = self.db.get_user(user.id)
            if not existing_user:
                # New user, just register them
                logger.info(f"New user detected, registering user {user.id}")
                self.db.register_user(
                    user_id=user.id,
                    first_name=user.first_name or "Unknown",
                    last_name=user.last_name or "",
                    username=user.username or ""
                )
                logger.info(f"Registered new user {user.id}")
                return

            # Check for changes
            changes = []
            if existing_user['first_name'] != user.first_name:
                changes.append(('First Name', existing_user['first_name'], user.first_name or "Unknown"))
                logger.info(f"First name change detected for user {user.id}: {existing_user['first_name']} -> {user.first_name or 'Unknown'}")
            
            if existing_user['last_name'] != user.last_name:
                changes.append(('Last Name', existing_user['last_name'], user.last_name or ""))
                logger.info(f"Last name change detected for user {user.id}: {existing_user['last_name']} -> {user.last_name or ''}")
            
            if existing_user['username'] != user.username:
                changes.append(('Username', existing_user['username'], user.username or ""))
                logger.info(f"Username change detected for user {user.id}: {existing_user['username']} -> {user.username or ''}")

            if changes:
                logger.info(f"Detected {len(changes)} changes for user {user.id}")
                # Get user's active groups
                user_groups = self.db.get_user_active_groups(user.id)
                logger.info(f"User {user.id} is in {len(user_groups)} active groups")
                
                if not user_groups:
                    logger.warning(f"User {user.id} has no active groups, skipping notification")
                    return

                # Get all scam names
                scam_names = self.db.get_scam_names()
                logger.info(f"Retrieved {len(scam_names)} scam names from database")

                # Check if new name matches any scam names
                new_full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
                is_scammer = False
                matched_scam_names = []

                for scam_name in scam_names:
                    if scam_name.lower() in new_full_name.lower():
                        is_scammer = True
                        matched_scam_names.append(scam_name)
                        logger.warning(f"Scam name match detected for user {user.id}: {scam_name}")

                # Record the change for each group
                for group in user_groups:
                    logger.info(f"Recording change for user {user.id} in group {group['group_name']}")
                    self.db.record_name_change(
                        user_id=user.id,
                        group_id=group['group_id'],
                        old_first_name=existing_user['first_name'],
                        old_last_name=existing_user['last_name'],
                        old_username=existing_user['username'],
                        new_first_name=user.first_name or "Unknown",
                        new_last_name=user.last_name or "",
                        new_username=user.username or ""
                    )

                    # If scammer detected, ban from the group
                    if is_scammer:
                        try:
                            # Get the chat entity
                            chat = await self.client.get_entity(group['group_id'])
                            
                            # Get bot's permissions in the chat
                            bot_permissions = await self.client.get_permissions(chat, await self.client.get_me())
                            
                            # Check if bot has ban rights
                            if not bot_permissions.is_admin and not bot_permissions.ban_users:
                                logger.warning(f"Bot doesn't have ban rights in group {group['group_name']}")
                                continue

                            try:
                                # Try to ban using edit_permissions first (for supergroups)
                                await self.client.edit_permissions(
                                    chat,
                                    user,
                                    until_date=None,  # Permanent ban
                                    view_messages=False,
                                    send_messages=False,
                                    send_media=False,
                                    send_stickers=False,
                                    send_gifs=False,
                                    send_games=False,
                                    send_inline=False
                                )
                                logger.info(f"Banned user {user.id} from supergroup {group['group_name']}")
                            except Exception as e:
                                # If that fails, try kick_participant (for regular groups)
                                logger.info(f"edit_permissions failed, trying kick_participant: {str(e)}")
                                await self.client.kick_participant(chat, user)
                                logger.info(f"Kicked user {user.id} from group {group['group_name']}")

                        except Exception as e:
                            logger.error(f"Failed to ban user {user.id} from group {group['group_name']}: {str(e)}")

                # Update user data
                self.db.register_user(
                    user_id=user.id,
                    first_name=user.first_name or "Unknown",
                    last_name=user.last_name or "",
                    username=user.username or ""
                )
                logger.info(f"Updated user data for {user.id}")

                # Only notify admin if scammer detected
                if is_scammer:
                    # Prepare concise notification message
                    change_msg = [
                        f"🚨 Scammer Detected & Banned",
                        f"From: {existing_user['first_name']} {existing_user['last_name']}",
                        f"To: {user.first_name} {user.last_name}",
                        f"Group: {', '.join(g['group_name'] for g in user_groups)}"
                    ]

                    # Send notification to admin
                    await self.client.send_message(Config.ADMIN_ID, "\n".join(change_msg))
                    logger.info(f"Sent scammer notification to admin for user {user.id}")
                else:
                    logger.debug(f"No scam names matched for user {user.id}, skipping notification")
            else:
                logger.debug(f"No changes detected for user {user.id}")

        except Exception as e:
            logger.error(f"Error handling name change: {str(e)}", exc_info=True)

    async def handle_user_join(self, event):
        """Handle new users joining the group"""
        try:
            logger.info(f"Received join event: {type(event)}")
            
            if not event.is_group:
                logger.debug("Ignoring join event: not a group")
                return

            # Get group information
            chat = await event.get_chat()
            logger.info(f"Got chat object: {type(chat)}")
            
            # Handle different chat types and normalize group ID
            if hasattr(chat, 'channel_id'):  # Channel/Supergroup
                group_id = abs(chat.channel_id)
            elif hasattr(chat, 'id'):  # Regular group
                group_id = abs(chat.id)
            else:
                logger.warning(f"Unsupported chat type: {type(chat)}")
                return

            # Get proper group name
            group_name = getattr(chat, 'title', None)
            if not group_name:
                logger.warning(f"Could not get group name for group {group_id}")
                return

            logger.info(f"Processing join event in group: {group_name} ({group_id})")
            
            # Register group with proper name
            if not self.db.register_group(group_id, group_name):
                logger.error(f"Failed to register group {group_name}")
                return

            # Get user information
            user = await event.get_user()
            logger.info(f"Got user object: {type(user)}")
            
            if not isinstance(user, User):
                logger.warning(f"Could not get user information for join event in group {group_name}")
                return

            logger.info(f"New user joined group {group_name}:")
            logger.info(f"  User ID: {user.id}")
            logger.info(f"  Name: {user.first_name} {user.last_name}")
            logger.info(f"  Username: @{user.username or 'none'}")

            # Check for scam names
            scam_names = self.db.get_scam_names()
            logger.info(f"Retrieved {len(scam_names)} scam names from database")

            # Check if name matches any scam names
            full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
            is_scammer = False
            matched_scam_names = []

            for scam_name in scam_names:
                if scam_name.lower() in full_name.lower():
                    is_scammer = True
                    matched_scam_names.append(scam_name)
                    logger.warning(f"Scam name match detected for new user {user.id}: {scam_name}")

            # If scammer detected, ban immediately
            if is_scammer:
                try:
                    # Get bot's permissions in the chat
                    bot_permissions = await self.client.get_permissions(chat, await self.client.get_me())
                    
                    # Check if bot has ban rights
                    if not bot_permissions.is_admin and not bot_permissions.ban_users:
                        logger.warning(f"Bot doesn't have ban rights in group {group_name}")
                        return

                    try:
                        # Try to ban using edit_permissions first (for supergroups)
                        await self.client.edit_permissions(
                            chat,
                            user,
                            until_date=None,  # Permanent ban
                            view_messages=False,
                            send_messages=False,
                            send_media=False,
                            send_stickers=False,
                            send_gifs=False,
                            send_games=False,
                            send_inline=False
                        )
                        logger.info(f"Banned new user {user.id} from supergroup {group_name}")
                    except Exception as e:
                        # If that fails, try kick_participant (for regular groups)
                        logger.info(f"edit_permissions failed, trying kick_participant: {str(e)}")
                        await self.client.kick_participant(chat, user)
                        logger.info(f"Kicked new user {user.id} from group {group_name}")

                    # Send notification to admin
                    change_msg = [
                        f"🚨 New Scammer Detected & Banned",
                        f"From: New User",
                        f"To: {user.first_name} {user.last_name}",
                        f"Group: {group_name}"
                    ]
                    await self.client.send_message(Config.ADMIN_ID, "\n".join(change_msg))
                    logger.info(f"Sent scammer notification to admin for new user {user.id}")
                    return

                except Exception as e:
                    logger.error(f"Failed to ban new user {user.id} from group {group_name}: {str(e)}")
                    return

            # Register user and add to group if not a scammer
            if self.db.register_user(
                user_id=user.id,
                first_name=user.first_name or "Unknown",
                last_name=user.last_name or "",
                username=user.username or ""
            ):
                logger.info(f"Successfully registered user {user.id} in database")
            else:
                logger.error(f"Failed to register user {user.id} in database")
                return

            if self.db.add_user_to_group(user.id, group_id):
                logger.info(f"Successfully added user {user.id} to group {group_name}")
                # Get updated user count
                total_users = self.db.get_group_user_count(group_id)
                logger.info(f"Total users in group {group_name}: {total_users}")
            else:
                logger.error(f"Failed to add user {user.id} to group {group_name}")
                return

        except Exception as e:
            logger.error(f"Error handling user join: {str(e)}", exc_info=True)

    async def handle_user_leave(self, event):
        """Handle users leaving the group"""
        try:
            if not event.is_group:
                logger.debug("Ignoring leave event: not a group")
                return

            # Get group information
            chat = await event.get_chat()
            group_id = abs(chat.id)
            group_name = getattr(chat, 'title', None)
            
            if not group_name:
                logger.warning(f"Could not get group name for group {group_id}")
                return

            # Get user information
            user = await event.get_user()
            if not isinstance(user, User):
                logger.warning(f"Could not get user information for leave event in group {group_name}")
                return

            logger.info(f"User {user.id} left group {group_name}")

            # Get user's remaining active groups
            remaining_groups = self.db.get_user_active_groups(user.id)
            remaining_groups = [g for g in remaining_groups if g['group_id'] != group_id]

            # Create clickable user link
            user_link = f"tg://user?id={user.id}"

            # Prepare notification message
            msg = [
                "👋 User Left Group Notification",
                "━━━━━━━━━━━━━━━━━━━━━━",
                f"👤 User: {user.first_name} {user.last_name}",
                f"🚪 Left Group: {group_name}",
                f"💬 [Click to Chat]({user_link})"
            ]

            if remaining_groups:
                msg.append("\n📋 Still in groups:")
                for group in remaining_groups:
                    msg.append(f"• {group['group_name']}")
            else:
                msg.append("\n📋 Not in any other groups")

            # Send notification to admin
            await self.client.send_message(
                Config.ADMIN_ID,
                "\n".join(msg),
                link_preview=False,
                parse_mode='markdown'
            )
            logger.info(f"Sent leave notification to admin for user {user.id}")

        except Exception as e:
            logger.error(f"Error handling user leave: {str(e)}", exc_info=True)

    async def start_command(self, event):
        """Handle /start command"""
        try:
            # Check if user is admin
            if event.sender_id != Config.ADMIN_ID:
                await event.reply("⛔ Only admin can use this command")
                return

            if not event.is_group:
                await event.reply("❌ This command can only be used in groups.")
                return

            # Get group information
            chat = await event.get_chat()
            # Normalize group ID
            group_id = abs(event.chat_id.channel_id if isinstance(event.chat_id, PeerChannel) else event.chat_id)
            
            # Get proper group name
            group_name = getattr(chat, 'title', None)
            if not group_name:
                await event.reply("❌ Could not get group name. Please try again.")
                return

            logger.info(f"Processing /start command for group: {group_name} ({group_id})")

            # Register group first
            if not self.db.register_group(group_id, group_name):
                await event.reply("❌ Error registering group. Please try again.")
                return

            # Add all current members to tracking
            count = 0
            errors = 0
            async for user in self.client.iter_participants(chat):
                if isinstance(user, User):
                    try:
                        self.db.register_user(
                            user_id=user.id,
                            first_name=user.first_name or "Unknown",
                            last_name=user.last_name or "",
                            username=user.username or ""
                        )
                        if self.db.add_user_to_group(user.id, group_id):
                            count += 1
                    except Exception as e:
                        logger.error(f"Error adding user {user.id} to group: {str(e)}")
                        errors += 1

            # Get total user count for the group
            total_users = self.db.get_group_user_count(group_id)

            status_msg = [
                f"✅ Name tracking activated for {group_name}!",
                f"Added {count} users to tracking.",
                f"Total users in group: {total_users}"
            ]
            
            if errors > 0:
                status_msg.append(f"⚠️ {errors} users could not be added.")
            
            status_msg.append("I'll notify the admin when users change their names.")
            await event.reply("\n".join(status_msg))
            
            # Notify admin
            await self.client.send_message(
                Config.ADMIN_ID,
                f"🎯 New group added to tracking:\n"
                f"Group: {group_name}\n"
                f"Users added: {count}\n"
                f"Total users: {total_users}"
            )

        except Exception as e:
            logger.error(f"Error in start command: {str(e)}", exc_info=True)
            await event.reply("❌ An error occurred. Please try again.")

    async def status_command(self, event):
        """Handle /status command"""
        try:
            # Check if user is admin
            if event.sender_id != Config.ADMIN_ID:
                await event.reply("⛔ Only admin can use this command")
                return

            # Get all active groups directly from database
            groups = self.db.get_all_groups()
            
            # Get all users with debug logging
            users = self.db.get_all_users()
            
            # Log the actual counts for debugging
            logger.info(f"Status command - Groups: {len(groups)}, Users: {len(users)}")
            
            status_msg = [
                "📊 Bot Status",
                f"👤 Users tracked: {len(users)}",
                f"👥 Groups monitored: {len(groups)}",
                "",
                "🎯 Monitored Groups:"
            ]

            # Add group names to status
            for group in groups:
                if group['group_name']:
                    # Get user count for this group
                    group_users = self.db.get_group_user_count(group['group_id'])
                    status_msg.append(f"• {group['group_name']} ({group_users} users)")

            await event.reply("\n".join(status_msg))

        except Exception as e:
            logger.error(f"Error in status command: {str(e)}", exc_info=True)
            await event.reply("❌ Error getting status. Please try again.")

    async def add_scam_command(self, event):
        """Handle /addscam command"""
        try:
            # Check if user is admin
            if event.sender_id != Config.ADMIN_ID:
                await event.reply("⛔ Only admin can add scam names")
                return

            # Get the scam names from the command
            args = event.text.split(maxsplit=1)
            if len(args) < 2:
                await event.reply("❌ Please provide names to add.\nUsage: /addscam <name1>, <name2>, <name3>")
                return

            # Split names by comma and clean them
            scam_names = [name.strip() for name in args[1].split(',')]
            scam_names = [name for name in scam_names if name]  # Remove empty names

            if not scam_names:
                await event.reply("❌ Please provide valid names.")
                return

            # Track results
            added = []
            failed = []
            already_exist = []

            # Add each name
            for name in scam_names:
                if self.db.add_scam_name(name):
                    added.append(name)
                    logger.info(f"Admin added scam name: {name}")
                else:
                    already_exist.append(name)
                    logger.info(f"Scam name already exists: {name}")

            # Prepare response message
            msg = []
            if added:
                msg.append("✅ Added names:")
                for name in added:
                    msg.append(f"• {name}")
            
            if already_exist:
                msg.append("\n⚠️ Names already exist:")
                for name in already_exist:
                    msg.append(f"• {name}")

            if failed:
                msg.append("\n❌ Failed to add names:")
                for name in failed:
                    msg.append(f"• {name}")

            # Send response
            if msg:
                await event.reply("\n".join(msg))
            else:
                await event.reply("❌ No names were added.")

        except Exception as e:
            logger.error(f"Error in add_scam command: {str(e)}", exc_info=True)
            await event.reply("❌ An error occurred while adding scam names.")

    async def remove_scam_command(self, event):
        """Handle /removescam command"""
        try:
            # Check if user is admin
            if event.sender_id != Config.ADMIN_ID:
                await event.reply("⛔ Only admin can remove scam names")
                return

            # Get the scam name from the command
            args = event.text.split(maxsplit=1)
            if len(args) < 2:
                await event.reply("❌ Please provide a name to remove.\nUsage: /removescam <name>")
                return

            scam_name = args[1].strip()
            if not scam_name:
                await event.reply("❌ Please provide a valid name.")
                return

            # Remove the scam name
            if self.db.remove_scam_name(scam_name):
                await event.reply(f"✅ Removed '{scam_name}' from scam names list")
                logger.info(f"Admin removed scam name: {scam_name}")
            else:
                await event.reply("❌ Failed to remove scam name. It might not exist.")
        except Exception as e:
            logger.error(f"Error in remove_scam command: {str(e)}", exc_info=True)
            await event.reply("❌ An error occurred while removing the scam name.")

    async def list_scam_command(self, event):
        """Handle /listscam command"""
        try:
            # Check if user is admin
            if event.sender_id != Config.ADMIN_ID:
                await event.reply("⛔ Only admin can view scam names")
                return

            # Get all scam names
            scam_names = self.db.get_scam_names()
            
            if not scam_names:
                await event.reply("📝 No scam names in the list.")
                return

            # Format the message
            msg = ["📝 Scam Names List:"]
            for i, name in enumerate(scam_names, 1):
                msg.append(f"{i}. {name}")

            await event.reply("\n".join(msg))
            logger.info("Admin viewed scam names list")
        except Exception as e:
            logger.error(f"Error in list_scam command: {str(e)}", exc_info=True)
            await event.reply("❌ An error occurred while fetching the scam names list.")

    async def start(self):
        """Start the bot"""
        try:
            # Start the client with connection retry
            retry_count = 0
            max_retries = 5
            
            while retry_count < max_retries:
                try:
                    await self.client.start(bot_token=Config.BOT_TOKEN)
                    break
                except Exception as e:
                    retry_count += 1
                    logger.error(f"Connection attempt {retry_count} failed: {str(e)}")
                    if retry_count < max_retries:
                        await asyncio.sleep(5)  # Wait 5 seconds before retrying
                    else:
                        raise Exception("Failed to connect after maximum retries")
            
            # Get bot info
            me = await self.client.get_me()
            logger.info(f"Bot started as @{me.username}")

            # Start web server for Render
            await self.start_web_server()

            # Add name change handlers for all update types
            @self.client.on(events.Raw)
            async def handle_raw(event):
                """Handle raw events for name changes"""
                try:
                    logger.info(f"Received raw event: {type(event)}")
                    logger.info(f"Event details: {event}")
                    
                    # Handle UpdateUser
                    if isinstance(event, UpdateUser):
                        logger.info(f"Processing UpdateUser event for user {event.user.id}")
                        logger.info(f"User details: {event.user}")
                        await self.handle_name_change(event)
                        return
                    
                    # Handle UpdateUserName
                    if isinstance(event, UpdateUserName):
                        logger.info(f"Processing UpdateUserName event for user {event.user_id}")
                        await self.handle_name_change(event)
                        return
                    
                    # Handle UpdateChannelParticipant
                    if isinstance(event, UpdateChannelParticipant):
                        logger.info(f"Processing UpdateChannelParticipant event: {event}")
                        try:
                            user = await self.client.get_entity(event.user_id)
                            if isinstance(user, User):
                                logger.info(f"User {user.id} updated in channel: {event.channel_id}")
                                logger.info(f"User details: {user}")
                                # Create a synthetic UpdateUser event
                                update_event = UpdateUser(user=user)
                                await self.handle_name_change(update_event)
                        except Exception as e:
                            logger.error(f"Error processing UpdateChannelParticipant: {str(e)}")
                        return

                    # Handle UpdateChatParticipant
                    if hasattr(event, 'participant') and hasattr(event, 'chat_id'):
                        logger.info(f"Processing UpdateChatParticipant event: {event}")
                        try:
                            user = await self.client.get_entity(event.participant.user_id)
                            if isinstance(user, User):
                                logger.info(f"User {user.id} updated in chat: {event.chat_id}")
                                logger.info(f"User details: {user}")
                                # Create a synthetic UpdateUser event
                                update_event = UpdateUser(user=user)
                                await self.handle_name_change(update_event)
                        except Exception as e:
                            logger.error(f"Error processing UpdateChatParticipant: {str(e)}")
                        return

                    # Handle UpdateChatParticipants
                    if hasattr(event, 'participants'):
                        logger.info(f"Processing UpdateChatParticipants event: {event}")
                        try:
                            for participant in event.participants:
                                if hasattr(participant, 'user_id'):
                                    user = await self.client.get_entity(participant.user_id)
                                    if isinstance(user, User):
                                        logger.info(f"User {user.id} updated in chat participants")
                                        logger.info(f"User details: {user}")
                                        # Create a synthetic UpdateUser event
                                        update_event = UpdateUser(user=user)
                                        await self.handle_name_change(update_event)
                        except Exception as e:
                            logger.error(f"Error processing UpdateChatParticipants: {str(e)}")
                        return

                except Exception as e:
                    logger.error(f"Error in raw event handler: {str(e)}", exc_info=True)

            # Add command handlers
            self.client.add_event_handler(self.start_command, events.NewMessage(pattern='/start'))
            self.client.add_event_handler(self.status_command, events.NewMessage(pattern='/status'))
            self.client.add_event_handler(self.add_scam_command, events.NewMessage(pattern='/addscam'))
            self.client.add_event_handler(self.remove_scam_command, events.NewMessage(pattern='/removescam'))
            self.client.add_event_handler(self.list_scam_command, events.NewMessage(pattern='/listscam'))

            # Add user join/leave handlers
            self.client.add_event_handler(
                self.handle_user_join,
                events.ChatAction(func=lambda e: e.user_joined)
            )
            self.client.add_event_handler(
                self.handle_user_leave,
                events.ChatAction(func=lambda e: e.user_left)
            )

            # Send startup message to admin
            await self.client.send_message(
                Config.ADMIN_ID,
                "🤖 Name Change Bot started!\n\n"
                "Commands:\n"
                "/start - Start tracking in a group\n"
                "/status - Check bot status\n"
                "/addscam <name1>, <name2>, <name3> - Add multiple scam names\n"
                "/removescam <name> - Remove a scam name\n"
                "/listscam - View all scam names"
            )
            logger.info("Bot is ready! Monitoring for name changes...")

            # Keep the bot running with connection monitoring
            while True:
                try:
                    if not self.client.is_connected():
                        logger.warning("Bot disconnected, attempting to reconnect...")
                        await self.client.connect()
                        if not await self.client.is_user_authorized():
                            await self.client.start(bot_token=Config.BOT_TOKEN)
                        logger.info("Bot reconnected successfully")
                    
                    await asyncio.sleep(30)  # Check connection every 30 seconds
                except Exception as e:
                    logger.error(f"Error in connection monitoring: {str(e)}")
                    await asyncio.sleep(5)  # Wait before retrying

        except Exception as e:
            logger.error(f"Error in bot: {str(e)}", exc_info=True)
            raise

if __name__ == '__main__':
    try:
        bot = NameChangeBot()
        with bot.client:
            bot.client.loop.run_until_complete(bot.start())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True) 