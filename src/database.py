import sqlite3
import logging
import os
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        """Initialize database connection"""
        self.db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'name_change.db')
        logger.info(f"Initializing database at: {self.db_path}")
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.create_tables()
        self.migrate_database()

    def create_tables(self):
        """Create necessary tables if they don't exist"""
        with self.conn:
            # Users table
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    first_name TEXT NOT NULL,
                    last_name TEXT,
                    username TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Groups table
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS groups (
                    group_id INTEGER PRIMARY KEY,
                    group_name TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # User-Group relationships
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS user_groups (
                    user_id INTEGER,
                    group_id INTEGER,
                    is_active BOOLEAN DEFAULT 1,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, group_id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (group_id) REFERENCES groups(group_id)
                )
            ''')

            # Name changes history
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS name_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    group_id INTEGER,
                    old_first_name TEXT,
                    old_last_name TEXT,
                    old_username TEXT,
                    new_first_name TEXT,
                    new_last_name TEXT,
                    new_username TEXT,
                    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (group_id) REFERENCES groups(group_id)
                )
            ''')
        logger.info("Database initialized successfully")

    def register_group(self, group_id, group_name):
        """Register or update a group"""
        try:
            with self.conn:
                # Normalize group ID (remove negative sign)
                normalized_id = abs(group_id)
                
                # First, check if group exists with this name
                cursor = self.conn.execute(
                    'SELECT group_id FROM groups WHERE group_name = ? AND is_active = 1',
                    (group_name,)
                )
                existing = cursor.fetchone()

                if existing:
                    # If group exists with this name but different ID, update the ID
                    if abs(existing['group_id']) != normalized_id:
                        logger.info(f"Updating group ID for {group_name} from {existing['group_id']} to {normalized_id}")
                        self.conn.execute(
                            'UPDATE groups SET group_id = ?, last_updated = CURRENT_TIMESTAMP WHERE group_name = ?',
                            (normalized_id, group_name)
                        )
                    return True

                # Check if group exists with this ID
                cursor = self.conn.execute(
                    'SELECT group_name FROM groups WHERE ABS(group_id) = ?',
                    (normalized_id,)
                )
                existing = cursor.fetchone()

                if existing:
                    # Update group name if it has changed
                    if existing['group_name'] != group_name:
                        self.conn.execute(
                            'UPDATE groups SET group_name = ?, last_updated = CURRENT_TIMESTAMP WHERE ABS(group_id) = ?',
                            (group_name, normalized_id)
                        )
                        logger.info(f"Updated group name for {normalized_id} to {group_name}")
                else:
                    # Insert new group
                    self.conn.execute(
                        'INSERT INTO groups (group_id, group_name) VALUES (?, ?)',
                        (normalized_id, group_name)
                    )
                    logger.info(f"Registered new group: {group_name} ({normalized_id})")
                return True
        except Exception as e:
            logger.error(f"Error registering group: {str(e)}")
            return False

    def get_group(self, group_id):
        """Get group information"""
        try:
            cursor = self.conn.execute(
                'SELECT * FROM groups WHERE ABS(group_id) = ? AND is_active = 1',
                (abs(group_id),)
            )
            return dict(cursor.fetchone()) if cursor.fetchone() else None
        except Exception as e:
            logger.error(f"Error getting group: {str(e)}")
            return None

    def get_all_groups(self):
        """Get all active groups with their names"""
        try:
            cursor = self.conn.execute('''
                SELECT DISTINCT group_id, group_name 
                FROM groups 
                WHERE is_active = 1 
                ORDER BY group_name
            ''')
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting all groups: {str(e)}")
            return []

    def get_all_users(self):
        """Get all users with their groups"""
        try:
            # First, let's debug the actual data in the tables
            cursor = self.conn.execute('SELECT COUNT(*) as count FROM users WHERE is_active = 1')
            total_users = cursor.fetchone()['count']
            logger.info(f"Total active users in users table: {total_users}")

            cursor = self.conn.execute('''
                SELECT COUNT(*) as count 
                FROM user_groups 
                WHERE is_active = 1
            ''')
            total_user_groups = cursor.fetchone()['count']
            logger.info(f"Total active user-group relationships: {total_user_groups}")

            # Now get the actual users with their groups
            cursor = self.conn.execute('''
                SELECT DISTINCT
                    u.user_id,
                    u.first_name,
                    u.last_name,
                    u.username,
                    g.group_id,
                    g.group_name
                FROM users u
                INNER JOIN user_groups ug ON u.user_id = ug.user_id
                INNER JOIN groups g ON ug.group_id = g.group_id
                WHERE u.is_active = 1 
                AND ug.is_active = 1 
                AND g.is_active = 1
            ''')
            
            users = {}
            for row in cursor.fetchall():
                row_dict = dict(row)
                user_id = row_dict['user_id']
                
                if user_id not in users:
                    users[user_id] = {
                        'user_id': user_id,
                        'first_name': row_dict['first_name'],
                        'last_name': row_dict['last_name'],
                        'username': row_dict['username'],
                        'groups': []
                    }
                
                users[user_id]['groups'].append({
                    'group_id': row_dict['group_id'],
                    'group_name': row_dict['group_name']
                })
            
            logger.info(f"Found {len(users)} users with active group memberships")
            return list(users.values())
        except Exception as e:
            logger.error(f"Error getting all users: {str(e)}")
            return []

    def register_user(self, user_id: int, first_name: str, last_name: str, username: str) -> bool:
        """Register a new user or update existing user"""
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO users (user_id, first_name, last_name, username)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, first_name, last_name, username))
            return True
        except Exception as e:
            logger.error(f"Error registering user {user_id}: {str(e)}")
            return False

    def add_user_to_group(self, user_id: int, group_id: int) -> bool:
        """Add a user to a group"""
        try:
            with self.conn:
                cursor = self.conn.cursor()
                normalized_id = abs(group_id)
                
                # First ensure user is active
                cursor.execute('''
                    UPDATE users 
                    SET is_active = 1 
                    WHERE user_id = ?
                ''', (user_id,))
                
                # Check if user is already in the group
                cursor.execute('''
                    SELECT is_active FROM user_groups 
                    WHERE user_id = ? AND ABS(group_id) = ?
                ''', (user_id, normalized_id))
                existing = cursor.fetchone()

                if existing:
                    if not existing['is_active']:
                        # Reactivate user in group
                        cursor.execute('''
                            UPDATE user_groups 
                            SET is_active = 1, last_seen = CURRENT_TIMESTAMP 
                            WHERE user_id = ? AND ABS(group_id) = ?
                        ''', (user_id, normalized_id))
                        logger.info(f"Reactivated user {user_id} in group {normalized_id}")
                else:
                    # Add new user to group
                    cursor.execute('''
                        INSERT INTO user_groups (user_id, group_id, is_active, added_at)
                        VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                    ''', (user_id, normalized_id))
                    logger.info(f"Added new user {user_id} to group {normalized_id}")
                
                # Verify the addition
                cursor.execute('''
                    SELECT COUNT(*) as count 
                    FROM user_groups 
                    WHERE user_id = ? AND ABS(group_id) = ? AND is_active = 1
                ''', (user_id, normalized_id))
                result = cursor.fetchone()
                if result['count'] != 1:
                    logger.error(f"Failed to verify user {user_id} addition to group {normalized_id}")
                    return False
                    
                return True
        except Exception as e:
            logger.error(f"Error adding user {user_id} to group {group_id}: {str(e)}")
            return False

    def record_name_change(self, user_id: int, group_id: int, 
                          old_first_name: str, old_last_name: str, old_username: str,
                          new_first_name: str, new_last_name: str, new_username: str) -> bool:
        """Record a name change for a user"""
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute('''
                    INSERT INTO name_changes 
                    (user_id, group_id, old_first_name, old_last_name, old_username,
                     new_first_name, new_last_name, new_username)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, group_id, old_first_name, old_last_name, old_username,
                      new_first_name, new_last_name, new_username))
            return True
        except Exception as e:
            logger.error(f"Error recording name change for user {user_id}: {str(e)}")
            return False

    def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user information"""
        try:
            cursor = self.conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            user = cursor.fetchone()
            if user:
                return {
                    'user_id': user[0],
                    'first_name': user[1],
                    'last_name': user[2],
                    'username': user[3],
                    'created_at': user[4]
                }
            return None
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {str(e)}")
            return None

    def get_user_groups(self, user_id: int):
        """Get all groups a user belongs to"""
        try:
            cursor = self.conn.execute('''
                SELECT g.group_id, g.group_name, g.is_active
                FROM groups g
                JOIN user_groups ug ON g.group_id = ug.group_id
                WHERE ug.user_id = ? 
                AND ug.is_active = 1 
                AND g.is_active = 1
                AND g.group_name IS NOT NULL
            ''', (user_id,))
            groups = [dict(row) for row in cursor.fetchall()]
            if not groups:
                logger.debug(f"No active groups found for user {user_id}")
            return groups
        except Exception as e:
            logger.error(f"Error getting user groups: {str(e)}")
            return []

    def get_name_changes(self, user_id: int, limit: int = 10):
        """Get recent name changes for a user"""
        try:
            cursor = self.conn.execute('''
                SELECT * FROM name_changes 
                WHERE user_id = ? 
                ORDER BY changed_at DESC 
                LIMIT ?
            ''', (user_id, limit))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting name changes: {str(e)}")
            return []

    def check_name_changes(self, user_id: int, current_data: Dict[str, Any]) -> Dict[str, Any]:
        """Check for name changes and return changes if any"""
        try:
            old_data = self.get_user(user_id)
            if not old_data:
                logger.debug(f"No existing data found for user {user_id}")
                return {}

            changes = {}
            if old_data['first_name'] != current_data['first_name']:
                changes['first_name'] = {
                    'old': old_data['first_name'],
                    'new': current_data['first_name']
                }
                logger.debug(f"First name change detected for user {user_id}: {old_data['first_name']} -> {current_data['first_name']}")
            
            if old_data['last_name'] != current_data['last_name']:
                changes['last_name'] = {
                    'old': old_data['last_name'],
                    'new': current_data['last_name']
                }
                logger.debug(f"Last name change detected for user {user_id}: {old_data['last_name']} -> {current_data['last_name']}")

            return changes
        except Exception as e:
            logger.error(f"Error checking name changes: {str(e)}")
            return {}

    def remove_user_from_group(self, user_id: int, group_id: int):
        """Remove user from group and mark as inactive"""
        try:
            with self.conn:
                cursor = self.conn.cursor()
                # Update user_groups to mark as inactive
                cursor.execute('''
                    UPDATE user_groups 
                    SET is_active = 0, last_seen = ?
                    WHERE user_id = ? AND group_id = ?
                ''', (datetime.now(), user_id, group_id))
                
                # Check if user is in any other active groups
                cursor.execute('''
                    SELECT COUNT(*) as active_groups
                    FROM user_groups
                    WHERE user_id = ? AND is_active = 1
                ''', (user_id,))
                result = cursor.fetchone()
                
                # If user is not in any active groups, mark user as inactive
                if result['active_groups'] == 0:
                    cursor.execute('''
                        UPDATE users
                        SET is_active = 0
                        WHERE user_id = ?
                    ''', (user_id,))
                
            logger.info(f"Removed user {user_id} from group {group_id}")
            return True
        except Exception as e:
            logger.error(f"Error removing user from group: {str(e)}")
            return False

    def get_user_active_groups(self, user_id: int):
        """Get all active groups a user belongs to"""
        try:
            cursor = self.conn.execute('''
                SELECT g.group_id, g.group_name
                FROM groups g
                JOIN user_groups ug ON g.group_id = ug.group_id
                WHERE ug.user_id = ? 
                AND ug.is_active = 1 
                AND g.is_active = 1
            ''', (user_id,))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting user active groups: {str(e)}")
            return []

    def update_user(self, user_id: int, first_name: str, last_name: str, username: str = None):
        """Update user information in the database"""
        try:
            with self.conn:
                cursor = self.conn.cursor()
                
                # Get existing user data
                cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
                existing_user = cursor.fetchone()
                
                if existing_user:
                    # Check for changes
                    changes = []
                    if existing_user['first_name'] != first_name:
                        changes.append(('first_name', existing_user['first_name'], first_name))
                    if existing_user['last_name'] != last_name:
                        changes.append(('last_name', existing_user['last_name'], last_name))
                    if username and existing_user['username'] != username:
                        changes.append(('username', existing_user['username'], username))
                    
                    # Record changes
                    for change_type, old_value, new_value in changes:
                        cursor.execute('''
                            INSERT INTO name_changes 
                            (user_id, change_type, old_value, new_value, changed_at)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (user_id, change_type, old_value, new_value, datetime.now()))
                        logger.info(f"Recorded {change_type} change for user {user_id}: {old_value} -> {new_value}")
                
                # Update user data
                cursor.execute('''
                    UPDATE users 
                    SET first_name = ?, last_name = ?, username = ?, created_at = ?
                    WHERE user_id = ?
                ''', (first_name, last_name, username or "", datetime.now(), user_id))
                
            logger.info(f"Updated user {user_id} in database")
            return True
        except Exception as e:
            logger.error(f"Error updating user: {str(e)}")
            return False

    def add_scam_name(self, name: str):
        """Add a new scam name to the scam_names table"""
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute('INSERT INTO scam_names (name) VALUES (?)', (name,))
            logger.info(f"Successfully added scam name: {name}")
            return True
        except Exception as e:
            logger.error(f"Error adding scam name: {str(e)}")
            return False

    def remove_scam_name(self, name: str):
        """Remove a scam name from the scam_names table"""
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute('DELETE FROM scam_names WHERE name = ?', (name,))
            logger.info(f"Successfully removed scam name: {name}")
            return True
        except Exception as e:
            logger.error(f"Error removing scam name: {str(e)}")
            return False

    def get_scam_names(self):
        """Get all scam names from the scam_names table"""
        try:
            cursor = self.conn.execute('SELECT name FROM scam_names')
            return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting scam names: {str(e)}")
            return []

    def migrate_database(self):
        """Migrate database schema to latest version"""
        try:
            with self.conn:
                cursor = self.conn.cursor()
                
                # Check if is_active column exists in users table
                cursor.execute("PRAGMA table_info(users)")
                columns = [column[1] for column in cursor.fetchall()]
                
                if 'is_active' not in columns:
                    logger.info("Adding is_active column to users table")
                    cursor.execute('ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1')
                
                if 'username' not in columns:
                    logger.info("Adding username column to users table")
                    cursor.execute('ALTER TABLE users ADD COLUMN username TEXT')
                
                # Check if is_active column exists in groups table
                cursor.execute("PRAGMA table_info(groups)")
                columns = [column[1] for column in cursor.fetchall()]
                
                if 'is_active' not in columns:
                    logger.info("Adding is_active column to groups table")
                    cursor.execute('ALTER TABLE groups ADD COLUMN is_active BOOLEAN DEFAULT 1')
                
                # Check if last_seen and is_active columns exist in user_groups table
                cursor.execute("PRAGMA table_info(user_groups)")
                columns = [column[1] for column in cursor.fetchall()]
                
                if 'last_seen' not in columns:
                    logger.info("Adding last_seen column to user_groups table")
                    cursor.execute('ALTER TABLE user_groups ADD COLUMN last_seen TIMESTAMP')
                
                if 'is_active' not in columns:
                    logger.info("Adding is_active column to user_groups table")
                    cursor.execute('ALTER TABLE user_groups ADD COLUMN is_active BOOLEAN DEFAULT 1')
                
                if 'added_at' not in columns:
                    logger.info("Adding added_at column to user_groups table")
                    cursor.execute('ALTER TABLE user_groups ADD COLUMN added_at TIMESTAMP')
                
                # Check if name_changes table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='name_changes'")
                if not cursor.fetchone():
                    logger.info("Creating name_changes table")
                    cursor.execute('''
                        CREATE TABLE name_changes (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER,
                            change_type TEXT,
                            old_value TEXT,
                            new_value TEXT,
                            changed_at TIMESTAMP,
                            FOREIGN KEY (user_id) REFERENCES users(user_id)
                        )
                    ''')
                
                # Check if scam_names table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scam_names'")
                if not cursor.fetchone():
                    logger.info("Creating scam_names table")
                    cursor.execute('''
                        CREATE TABLE scam_names (
                            id INTEGER PRIMARY KEY,
                            name TEXT UNIQUE
                        )
                    ''')
                
            logger.info("Database migration completed successfully")
        except Exception as e:
            logger.error(f"Error during database migration: {str(e)}")
            raise 

    def get_group_user_count(self, group_id: int) -> int:
        """Get the number of active users in a group"""
        try:
            cursor = self.conn.execute('''
                SELECT COUNT(DISTINCT u.user_id) as user_count
                FROM users u
                JOIN user_groups ug ON u.user_id = ug.user_id
                WHERE ug.group_id = ? 
                AND u.is_active = 1 
                AND ug.is_active = 1
            ''', (group_id,))
            result = cursor.fetchone()
            return result['user_count'] if result else 0
        except Exception as e:
            logger.error(f"Error getting group user count: {str(e)}")
            return 0 