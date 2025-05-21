import logging
from aiohttp import web
from telethon import TelegramClient
from src.database import Database

logger = logging.getLogger(__name__)

class HealthCheckService:
    def __init__(self, client: TelegramClient, db: Database, port: int):
        self.client = client
        self.db = db
        self.port = port

    async def health_check(self, request):
        """Health check endpoint"""
        try:
            # Check if client is connected
            if not self.client.is_connected():
                return web.Response(status=503, text="Bot not connected")
            
            # Check if database is accessible
            try:
                self.db.get_connection()
            except Exception as e:
                logger.error(f"Database health check failed: {str(e)}")
                return web.Response(status=503, text="Database not accessible")
                
            return web.Response(text="OK")
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return web.Response(status=503, text="Service unhealthy")

    async def start(self):
        """Start the health check server"""
        app = web.Application()
        app.router.add_get('/health', self.health_check)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.port)
        await site.start()
        logger.info(f"Health check server started on port {self.port}")
        
        # Keep the server running
        while True:
            if not self.client.is_connected():
                logger.warning("Bot disconnected, attempting to reconnect...")
                await self.client.connect() 