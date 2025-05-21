import os
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(
    format='[%(levelname)s] %(asctime)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('name_tracker.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env')
logger.info(f"Loading environment from: {env_path}")
load_dotenv(env_path)

class Config:
    API_ID = int(os.getenv('API_ID', 0))
    API_HASH = os.getenv('API_HASH', '')
    BOT_TOKEN = os.getenv('BOT_TOKEN', '')
    ADMIN_ID = int(os.getenv('ADMIN_ID', 0))
    SESSION_NAME = 'name_change_bot'
    MONITORED_GROUPS = [int(x) for x in os.getenv('MONITORED_GROUPS', '').split(',') if x]
    PORT = int(os.getenv('PORT', 8080))
    RAILWAY_HEALTH_CHECK = os.getenv('RAILWAY_HEALTH_CHECK', 'true').lower() == 'true'

    @classmethod
    def validate(cls):
        """Validate required configuration"""
        if not all([cls.API_ID, cls.API_HASH, cls.BOT_TOKEN, cls.ADMIN_ID]):
            logger.error("Missing required environment variables")
            logger.error(f"API_ID: {cls.API_ID}")
            logger.error(f"API_HASH: {'Set' if cls.API_HASH else 'Not Set'}")
            logger.error(f"BOT_TOKEN: {'Set' if cls.BOT_TOKEN else 'Not Set'}")
            logger.error(f"ADMIN_ID: {cls.ADMIN_ID}")
            raise ValueError("Missing required environment variables") 