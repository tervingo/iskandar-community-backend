import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
from app.services.backup_service import backup_service
import os

logger = logging.getLogger(__name__)

class SchedulerService:
    def __init__(self):
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self.backup_interval_hours = int(os.getenv("BACKUP_INTERVAL_HOURS", "168"))  # 168 hours = 1 week
        self.enabled = os.getenv("ENABLE_SCHEDULED_BACKUPS", "true").lower() == "true"

        if self.enabled:
            logger.info(f"Scheduler initialized - backups every {self.backup_interval_hours} hours")
        else:
            logger.info("Scheduled backups disabled via ENABLE_SCHEDULED_BACKUPS environment variable")

    async def start(self):
        """Start the backup scheduler"""
        if not self.enabled:
            logger.info("Scheduled backups are disabled")
            return

        if self.running:
            logger.warning("Scheduler is already running")
            return

        self.running = True
        self.task = asyncio.create_task(self._scheduler_loop())
        logger.info("Backup scheduler started")

    async def stop(self):
        """Stop the backup scheduler"""
        if not self.running:
            return

        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("Backup scheduler stopped")

    async def _scheduler_loop(self):
        """Main scheduler loop"""
        try:
            # Wait for initial delay (start backup 1 hour after server start)
            initial_delay = 3600  # 1 hour in seconds
            logger.info(f"Scheduler will start first backup in {initial_delay // 60} minutes")
            await asyncio.sleep(initial_delay)

            while self.running:
                try:
                    logger.info("Starting scheduled backup...")
                    result = await backup_service.create_backup()

                    if result["success"]:
                        logger.info(f"Scheduled backup completed successfully: {result.get('timestamp')}")
                    else:
                        logger.error(f"Scheduled backup failed: {result.get('message')}")

                except Exception as e:
                    logger.error(f"Scheduled backup error: {e}")

                # Wait for next backup interval
                wait_seconds = self.backup_interval_hours * 3600
                logger.info(f"Next backup scheduled in {self.backup_interval_hours} hours")

                # Sleep in smaller chunks to allow for graceful shutdown
                for _ in range(wait_seconds // 60):  # Check every minute
                    if not self.running:
                        break
                    await asyncio.sleep(60)

        except asyncio.CancelledError:
            logger.info("Scheduler loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Scheduler loop error: {e}")
        finally:
            self.running = False

    def get_status(self) -> dict:
        """Get scheduler status"""
        return {
            "enabled": self.enabled,
            "running": self.running,
            "interval_hours": self.backup_interval_hours,
            "next_backup_estimate": self._estimate_next_backup()
        }

    def _estimate_next_backup(self) -> Optional[str]:
        """Estimate when the next backup will occur"""
        if not self.running:
            return None

        # This is an approximation - in a production system you'd track this more precisely
        next_backup = datetime.utcnow() + timedelta(hours=self.backup_interval_hours)
        return next_backup.isoformat()

# Global scheduler instance
scheduler_service = SchedulerService()