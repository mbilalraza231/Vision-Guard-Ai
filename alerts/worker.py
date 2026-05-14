import asyncio
import json
import logging
import os
import socket
import sys
import time
from typing import List, Dict, Any, Optional

import redis.asyncio as redis
import psutil

from .config import AlertConfig
from .repository import AlertRepository
from .notifier import AlertNotifier

# Add parent directory to sys.path for database access
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

class MetricsReporter:
    def __init__(self, r, name):
        self.r, self.name = r, name
        self.pid = os.getpid()
        self.host = socket.gethostname()
        self.key = f"vg:metrics:{name}:{self.host}"
        self._stop = asyncio.Event()

    async def start(self):
        asyncio.create_task(self._run())

    async def _run(self):
        p = psutil.Process(self.pid)
        while not self._stop.is_set():
            try:
                cpu = p.cpu_percent(interval=None)
                mem = p.memory_info().rss / (1024**3)
                await self.r.setex(self.key, 15, json.dumps({
                    "cpu_percent": round(cpu, 2),
                    "memory_gb": round(mem, 4),
                    "timestamp": time.time(),
                    "instance": self.host
                }))
            except: pass
            await asyncio.sleep(5)

class AlertWorker:
    def __init__(self, config: AlertConfig):
        self.config = config
        self.repo = AlertRepository(config)
        self.notifier = AlertNotifier(config)
        self.redis = None
        self.contacts = []
        self._last_cache_update = 0
        self._stop = asyncio.Event()

    async def update_contact_cache(self):
        """Fetch active contacts from DB every 60 seconds."""
        if time.time() - self._last_cache_update < 60:
            return
        
        try:
            self.contacts = await self.repo.get_active_contacts()
            self._last_cache_update = time.time()
            logger.info(f"Updated contact cache: {len(self.contacts)} active contacts")
        except Exception as e:
            logger.error(f"Failed to update contact cache: {e}")

    def get_predictable_url(self, event_id: str, event_type: str) -> str:
        """Construct the predictable Cloudinary URL."""
        # Folder pattern from uploader.py
        etype_folder = event_type.split('_')[0] if '_' in event_type else event_type
        return f"https://res.cloudinary.com/{self.config.cloudinary_cloud_name}/image/upload/visionguard/snapshots/{etype_folder}/snapshot_{event_id}.jpg"

    def format_message(self, event: Dict[str, Any], url: str) -> str:
        """Format the alert message for SMS/WhatsApp."""
        severity = event.get('severity', 'UNKNOWN').upper()
        etype = event.get('event_type', 'Detection').replace('_', ' ').title()
        
        ts_val = event.get('timestamp')
        try:
            ts_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(float(ts_val)))
        except:
            ts_str = "Recently"
        
        return (
            f"🚨 {severity} ALERT: {etype} 🚨\n"
            f"Camera: {event.get('camera_id')}\n"
            f"Time: {ts_str}\n"
            f"Confidence: {float(event.get('confidence', 0))*100:.1f}%\n"
            f"Evidence: {url}"
        )

    async def process_event(self, event: Dict[str, Any]):
        """Evaluate event and dispatch notifications to matched contacts."""
        await self.update_contact_cache()
        
        event_id = event.get('event_id')
        event_type = event.get('event_type')
        severity = event.get('severity', 'medium').lower()
        
        url = self.get_predictable_url(event_id, event_type)
        message = self.format_message(event, url)
        
        rank = {"critical": 3, "high": 2, "medium": 1, "low": 0}
        event_rank = rank.get(severity, 0)
        
        tasks = []
        for contact in self.contacts:
            min_sev = contact.get('min_severity', 'medium').lower()
            if event_rank < rank.get(min_sev, 0):
                continue
            
            # Send WhatsApp/SMS
            if contact.get('phone') and contact.get('whatsapp'):
                phone = contact['phone']
                to = f"whatsapp:{phone}" if not phone.startswith('whatsapp:') else phone
                tasks.append(self.notifier.send_twilio(to, message, media_url=url))
            elif contact.get('phone'):
                tasks.append(self.notifier.send_twilio(contact['phone'], message))
                
            # Send Email
            if contact.get('email') and contact.get('email_alert'):
                subject = f"VisionGuard Alert: {severity.upper()} {event_type.replace('_', ' ').title()}"
                body = f"""
                <html>
                <body>
                    <h2>VisionGuard AI Security Alert</h2>
                    <p><strong>Type:</strong> {event_type.replace('_', ' ').title()}</p>
                    <p><strong>Severity:</strong> {severity.upper()}</p>
                    <p><strong>Camera:</strong> {event.get('camera_id')}</p>
                    <p><strong>Confidence:</strong> {float(event.get('confidence', 0))*100:.1f}%</p>
                    <p><a href="{url}"><img src="{url}" width="600" style="max-width:100%;" /></a></p>
                    <p><a href="{url}">View Full Evidence Snapshot</a></p>
                </body>
                </html>
                """
                tasks.append(self.notifier.send_gmail(contact['email'], subject, body))

        if tasks:
            logger.info(f"Dispatching {len(tasks)} notifications for event {event_id}")
            # Collect recipient names for logging
            recipient_names = [c.get('name', 'User') for c in self.contacts if c.get('id')]
            recipient_summary = ", ".join(recipient_names[:2])
            if len(recipient_names) > 2:
                recipient_summary += f" +{len(recipient_names) - 2} others"
            
            # Create alert record as 'sent'
            await self.repo.create(
                event_id, 
                channel="multi-channel", 
                recipient=recipient_summary, 
                status="sent"
            )
            
            # Execute dispatches
            await asyncio.gather(*tasks, return_exceptions=True)

    async def run(self):
        """Main loop listening to Redis stream."""
        while not self._stop.is_set():
            try:
                self.redis = redis.Redis(
                    host=self.config.redis_host,
                    port=self.config.redis_port,
                    decode_responses=True
                )
                await self.redis.ping()
                break
            except Exception as e:
                logger.error(f"Redis failed: {e}. Retrying...")
                await asyncio.sleep(5)

        reporter = MetricsReporter(self.redis, "alert-worker")
        await reporter.start()

        await self.update_contact_cache()

        logger.info("Alert Worker active. Listening to vg:clip:requests...")
        stream_key = "vg:clip:requests"
        last_id = "$" 

        while not self._stop.is_set():
            try:
                results = await self.redis.xread({stream_key: last_id}, count=1, block=5000)
                if not results:
                    continue
                
                for stream, messages in results:
                    for msg_id, data in messages:
                        last_id = msg_id
                        await self.process_event(data)
                        
            except Exception as e:
                logger.error(f"Loop error: {e}")
                await asyncio.sleep(2)

async def main():
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    
    config = AlertConfig()
    worker = AlertWorker(config)
    
    try:
        await worker.run()
    except KeyboardInterrupt:
        await worker.stop()

if __name__ == "__main__":
    asyncio.run(main())
