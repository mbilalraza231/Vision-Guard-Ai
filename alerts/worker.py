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
        # Must match CloudinaryUploader.upload_snapshot folder structure exactly
        return f"https://res.cloudinary.com/{self.config.cloudinary_cloud_name}/image/upload/visionguard/snapshots/{event_type}/snapshot_{event_id}.jpg"

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

    def get_predictable_video_url(self, event_id: str, event_type: str) -> str:
        """Construct the predictable Cloudinary Video URL."""
        return f"https://res.cloudinary.com/{self.config.cloudinary_cloud_name}/video/upload/visionguard/clips/{event_type}/clip_{event_id}.mp4"

    async def wait_for_snapshot(self, url: str, timeout: float = 15.0) -> bool:
        """Poll the snapshot URL until it is available (HTTP 200) or timeout is reached."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = await self.notifier.client.head(url)
                if resp.status_code == 200:
                    logger.info(f"Snapshot available at {url} after {time.time() - start:.2f}s")
                    return True
            except Exception as e:
                pass
            await asyncio.sleep(1.0)
        logger.warning(f"Snapshot URL {url} not available after {timeout}s timeout")
        return False

    async def send_twilio_with_media_wait(self, to: str, message: str, media_url: Optional[str] = None) -> bool:
        """Wait for the media_url to be available (HTTP 200) before sending the Twilio message."""
        if media_url:
            await self.wait_for_snapshot(media_url)
        return await self.notifier.send_twilio(to, message, media_url=media_url)

    async def process_event(self, event: Dict[str, Any]):
        """Evaluate event and dispatch notifications to matched contacts."""
        await self.update_contact_cache()
        
        event_id = event.get('event_id')
        event_type = event.get('event_type')
        severity = event.get('severity', 'medium').lower()
        
        snap_url = self.get_predictable_url(event_id, event_type)
        video_url = self.get_predictable_video_url(event_id, event_type)
        whatsapp_msg = self.format_message(event, snap_url)
        
        rank = {"critical": 3, "high": 2, "medium": 1, "low": 0}
        event_rank = rank.get(severity, 0)
        
        tasks = []
        for contact in self.contacts:
            min_sev = contact.get('min_severity', 'medium').lower()
            if event_rank < rank.get(min_sev, 0):
                continue
            
            # Send WhatsApp
            if contact.get('phone') and contact.get('whatsapp'):
                phone = contact['phone']
                to = f"whatsapp:{phone}" if not phone.startswith('whatsapp:') else phone
                tasks.append(self.send_twilio_with_media_wait(to, whatsapp_msg, media_url=snap_url))
                
            # Send Premium Email
            if contact.get('email') and contact.get('email_alert'):
                color = "#ff4b2b" if severity == "critical" else "#ffa502" if severity == "high" else "#2ed573"
                subject = f"⚠️ VisionGuard: {severity.upper()} {event_type.replace('_', ' ').title()}"
                body = f"""
                <div style="background-color: #0f172a; color: #f8fafc; font-family: sans-serif; padding: 40px 20px; max-width: 600px; margin: auto; border-radius: 16px;">
                    <div style="text-align: center; margin-bottom: 30px;">
                        <h1 style="color: #3b82f6; margin: 0; font-size: 28px;">VisionGuard AI</h1>
                        <p style="color: #94a3b8; font-size: 14px; margin-top: 5px;">Real-time Security Intelligence</p>
                    </div>
                    
                    <div style="background-color: #1e293b; border-left: 4px solid {color}; padding: 20px; border-radius: 8px; margin-bottom: 25px;">
                        <h2 style="margin: 0 0 10px 0; color: {color}; text-transform: uppercase; font-size: 18px;">{severity.upper()} ALERT DETECTED</h2>
                        <p style="margin: 5px 0;"><strong>Incident:</strong> {event_type.replace('_', ' ').title()}</p>
                        <p style="margin: 5px 0;"><strong>Camera:</strong> {event.get('camera_id')}</p>
                        <p style="margin: 5px 0;"><strong>Confidence:</strong> {float(event.get('confidence', 0))*100:.1f}%</p>
                    </div>

                    <div style="margin-bottom: 25px;">
                        <a href="{snap_url}">
                            <img src="{snap_url}" width="100%" style="border-radius: 12px; border: 1px solid #334155; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);" />
                        </a>
                    </div>

                    <div style="display: flex; gap: 10px; justify-content: center; margin-top: 20px;">
                        <a href="{video_url}" style="background-color: #3b82f6; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block;">▶ Watch Video Clip</a>
                        <a href="{snap_url}" style="background-color: transparent; color: #94a3b8; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold; border: 1px solid #334155; display: inline-block; margin-left: 10px;">Full Snapshot</a>
                    </div>

                    <div style="margin-top: 40px; text-align: center; border-top: 1px solid #334155; padding-top: 20px;">
                        <p style="color: #64748b; font-size: 12px;">This is an automated security alert from your VisionGuard AI system.</p>
                    </div>
                </div>
                """
                tasks.append(self.notifier.send_gmail(contact['email'], subject, body))

        if tasks:
            logger.info(f"Dispatching {len(tasks)} notifications for event {event_id}")

            # Collect recipient names for logging
            recipient_names = [c.get('name', 'User') for c in self.contacts if c.get('id')]
            recipient_summary = ", ".join(recipient_names[:2])
            if len(recipient_names) > 2:
                recipient_summary += f" +{len(recipient_names) - 2} others"

            # --- OPTIMIZED: Send first, write ONCE to DB with final result ---
            # Execute all dispatches simultaneously
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Map results back to channels for granular UI display
            # Initialize as False so that disabled/failed channels show Red in UI
            details = {"whatsapp": False, "email": False}
            
            task_idx = 0
            for contact in self.contacts:
                min_sev = contact.get('min_severity', 'medium').lower()
                if event_rank < rank.get(min_sev, 0):
                    continue
                
                if contact.get('phone') and contact.get('whatsapp'):
                    # If any contact succeeds on this channel, mark as True
                    if task_idx < len(results) and results[task_idx] is True:
                        details['whatsapp'] = True
                    task_idx += 1
                
                if contact.get('email') and contact.get('email_alert'):
                    # If any contact succeeds on this channel, mark as True
                    if task_idx < len(results) and results[task_idx] is True:
                        details['email'] = True
                    task_idx += 1

            # Determine final status: 'failed' only if ALL channels failed
            any_success = any(r is True for r in results)
            final_status = "sent" if any_success else "failed"

            # Single DB write with complete final state (no pending ghost row)
            await self.repo.create(
                event_id,
                channel="multi-channel",
                recipient=recipient_summary,
                status=final_status,
                details=details
            )

            if not any_success:
                logger.warning(f"ALL notifications failed for event {event_id}. Status: failed.")
            elif not all(r is True for r in results):
                logger.info(f"Partial success for event {event_id}. Some channels failed.")
            else:
                logger.info(f"All notifications dispatched successfully for event {event_id}.")

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

        logger.info("Alert Worker active. Listening to vg:events:finalized...")
        stream_key = "vg:events:finalized"
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
