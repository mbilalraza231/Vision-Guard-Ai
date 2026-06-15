import asyncio
import hashlib
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

    def format_message(self, event: Dict[str, Any], snap_url: str, video_url: str, anonymize: bool = False) -> str:
        """Format the alert message for SMS/WhatsApp."""
        severity = event.get('severity', 'UNKNOWN').upper()
        etype = event.get('event_type', 'Detection').replace('_', ' ').title()
        event_id = event.get('event_id', '')
        
        ts_val = event.get('timestamp')
        try:
            ts_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(float(ts_val)))
        except:
            ts_str = "Recently"
        
        cam_id = event.get('camera_id', 'Unknown')
        if anonymize:
            if len(cam_id) > 4:
                cam_id = cam_id[:2] + "****" + cam_id[-2:]
            else:
                cam_id = "****"
        
        dashboard_url = os.getenv("FRONTEND_URL", "http://localhost:8080").rstrip("/")
        # Generate simple token for public access (using event ID + timestamp)
        token_payload = f"{event_id}{int(time.time())}"
        secure_token = hashlib.sha256(token_payload.encode()).hexdigest()[:32]
        # Note: contact name will be added in the main loop where contact is available
        public_url = f"{dashboard_url}/public-incident/{event_id}?token={secure_token}&from=whatsapp"
        
        return (
            f"🚨 {severity} ALERT: {etype} 🚨\n"
            f"Camera: {cam_id}\n"
            f"Time: {ts_str}\n"
            f"Confidence: {float(event.get('confidence', 0))*100:.1f}%\n"
            f"📸 Snapshot: {snap_url}\n"
            f"🎬 Clip: {video_url}\n\n"
            f"✅ [ Acknowledge ]:\n"
            f"👉 {public_url}?action=acknowledge\n\n"
            f"🔍 [ View Details ]:\n"
            f"👉 {public_url}"
        )

    def get_predictable_video_url(self, event_id: str, event_type: str) -> str:
        """Construct the predictable Cloudinary Video URL."""
        return f"https://res.cloudinary.com/{self.config.cloudinary_cloud_name}/video/upload/visionguard/clips/{event_type}/clip_{event_id}.mp4"

    # Note: No media_url polling needed — we embed URLs directly in the message text.

    async def process_event(self, event: Dict[str, Any]):
        """Evaluate event and dispatch notifications to matched contacts."""
        await self.update_contact_cache()
        
        event_id = event.get('event_id')
        event_type = event.get('event_type')
        severity = event.get('severity', 'medium').lower()
        
        snap_url = self.get_predictable_url(event_id, event_type)
        video_url = self.get_predictable_video_url(event_id, event_type)
        
        # Fetch global system settings
        sys_settings = await self.repo.get_system_settings()
        privacy_settings = sys_settings.get('privacy', {})
        anonymize_data = privacy_settings.get('anonymizeData', False)

        whatsapp_msg = self.format_message(event, snap_url, video_url, anonymize=anonymize_data)
        
        # Format timestamp for email template
        ts_val = event.get('timestamp')
        try:
            ts_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(float(ts_val)))
        except:
            ts_str = "Recently"
        
        # Determine camera ID string to use in notifications
        cam_id = event.get('camera_id', 'Unknown')
        if anonymize_data:
            if len(cam_id) > 4:
                cam_id = cam_id[:2] + "****" + cam_id[-2:]
            else:
                cam_id = "****"
        
        rank = {"critical": 3, "high": 2, "medium": 1, "low": 0}
        event_rank = rank.get(severity, 0)
        
        # Fetch global system settings
        sys_settings = await self.repo.get_system_settings()
        alert_settings = sys_settings.get('alerts', {})
        global_threshold = alert_settings.get('alertThreshold', 'low').lower()
        email_enabled = alert_settings.get('emailNotifications', False)
        push_enabled = alert_settings.get('pushNotifications', False)
        
        # If the event severity is below the global threshold, skip entirely
        if event_rank < rank.get(global_threshold, 0):
            logger.info(f"Skipping event {event_id}: severity '{severity}' is below global threshold '{global_threshold}'")
            return
        
        tasks = []
        for contact in self.contacts:
            min_sev = contact.get('min_severity', 'medium').lower()
            if event_rank < rank.get(min_sev, 0):
                continue
            
            # Send WhatsApp — plain text with URLs embedded in body (no MediaUrl attachment).
            # This avoids the race condition where Twilio tries to download the Cloudinary
            # image before the clip recorder has finished uploading it (error 63019).
            # Send WhatsApp (Push Notification toggle)
            if push_enabled and contact.get('phone') and contact.get('whatsapp'):
                phone = contact['phone']
                to = f"whatsapp:{phone}" if not phone.startswith('whatsapp:') else phone
                # Add contact name to WhatsApp URL
                from urllib.parse import quote
                contact_name = contact.get('name', 'Alert Contact')
                whatsapp_msg_with_contact = whatsapp_msg.replace(
                    f"{dashboard_url}/public-incident/{event_id}?token=",
                    f"{dashboard_url}/public-incident/{event_id}?token={secure_token}&from=whatsapp&contact={quote(contact_name)}"
                )
                tasks.append(self.notifier.send_twilio(to, whatsapp_msg_with_contact, anonymize=anonymize_data))
                
            # Send Premium Email
            if email_enabled and contact.get('email') and contact.get('email_alert'):
                color = "#ff4b2b" if severity == "critical" else "#ffa502" if severity == "high" else "#2ed573"
                subject = f"⚠️ VisionGuard: {severity.upper()} {event_type.replace('_', ' ').title()}"
                dashboard_url = os.getenv("FRONTEND_URL", "http://localhost:8080").rstrip("/")
                # Generate simple token for public access (using event ID + timestamp)
                import hashlib
                from urllib.parse import quote
                token_payload = f"{event_id}{int(time.time())}"
                secure_token = hashlib.sha256(token_payload.encode()).hexdigest()[:32]
                contact_name = contact.get('name', 'Alert Contact')
                public_url = f"{dashboard_url}/public-incident/{event_id}?token={secure_token}&from=email&contact={quote(contact_name)}"
                
                body = f"""
                <div style="background-color: #0f172a; color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 40px 20px; max-width: 600px; margin: auto; border-radius: 16px;">
                    <div style="text-align: center; margin-bottom: 30px;">
                        <h1 style="color: #3b82f6; margin: 0; font-size: 28px; font-weight: 700;">VisionGuard AI</h1>
                        <p style="color: #94a3b8; font-size: 14px; margin-top: 8px; font-weight: 500;">Real-time Security Intelligence</p>
                    </div>
                    
                    <div style="background-color: #1e293b; border-left: 4px solid {color}; padding: 24px; border-radius: 12px; margin-bottom: 25px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
                        <h2 style="margin: 0 0 12px 0; color: {color}; text-transform: uppercase; font-size: 16px; font-weight: 700; letter-spacing: 0.05em;">{severity.upper()} ALERT DETECTED</h2>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 16px;">
                            <div>
                                <p style="margin: 0; color: #64748b; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;">Incident</p>
                                <p style="margin: 4px 0 0 0; color: #f1f5f9; font-size: 15px; font-weight: 500;">{event_type.replace('_', ' ').title()}</p>
                            </div>
                            <div>
                                <p style="margin: 0; color: #64748b; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;">Camera</p>
                                <p style="margin: 4px 0 0 0; color: #f1f5f9; font-size: 15px; font-weight: 500;">{cam_id}</p>
                            </div>
                            <div style="grid-column: span 2;">
                                <p style="margin: 0; color: #64748b; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;">Time</p>
                                <p style="margin: 4px 0 0 0; color: #f1f5f9; font-size: 15px; font-weight: 500;">{ts_str}</p>
                            </div>
                            <div style="grid-column: span 2;">
                                <p style="margin: 0; color: #64748b; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;">AI Confidence</p>
                                <div style="display: flex; align-items: center; gap: 8px; margin-top: 4px;">
                                    <div style="flex: 1; height: 8px; background-color: #334155; border-radius: 4px; overflow: hidden;">
                                        <div style="height: 100%; background-color: {color}; width: {float(event.get('confidence', 0))*100:.1f}%;"></div>
                                    </div>
                                    <p style="margin: 0; color: #f1f5f9; font-size: 14px; font-weight: 700;">{float(event.get('confidence', 0))*100:.1f}%</p>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div style="margin-bottom: 25px;">
                        <a href="{public_url}">
                            <img src="{snap_url}" width="100%" style="border-radius: 12px; border: 2px solid #334155; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4); transition: transform 0.2s;" />
                        </a>
                    </div>

                    <div style="display: flex; flex-direction: column; gap: 12px; margin-top: 24px;">
                        <a href="{public_url}?action=acknowledge" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; padding: 16px 32px; text-decoration: none; border-radius: 10px; font-weight: 700; display: block; text-align: center; box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3); transition: transform 0.2s, box-shadow 0.2s;">✅ Acknowledge Alert</a>
                        <a href="{public_url}" style="background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%); color: white; padding: 16px 32px; text-decoration: none; border-radius: 10px; font-weight: 700; display: block; text-align: center; box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3); transition: transform 0.2s, box-shadow 0.2s;">🔍 View Full Details</a>
                        <a href="{video_url}" style="background-color: transparent; color: #94a3b8; padding: 16px 32px; text-decoration: none; border-radius: 10px; font-weight: 600; border: 2px solid #334155; display: block; text-align: center; transition: all 0.2s;">▶ Watch Video Clip</a>
                    </div>

                    <div style="margin-top: 40px; text-align: center; border-top: 1px solid #334155; padding-top: 24px;">
                        <p style="color: #64748b; font-size: 13px; font-weight: 500;">This is an automated security alert from your VisionGuard AI system.</p>
                        <p style="color: #475569; font-size: 12px; margin-top: 8px;">Contact your security team if you have questions about this alert.</p>
                    </div>
                </div>
                """
                tasks.append(self.notifier.send_gmail(contact['email'], subject, body, anonymize=anonymize_data))

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
                
                # Must mirror the exact same guards used when building `tasks` above
                if push_enabled and contact.get('phone') and contact.get('whatsapp'):
                    if task_idx < len(results) and results[task_idx] is True:
                        details['whatsapp'] = True
                    task_idx += 1
                
                if email_enabled and contact.get('email') and contact.get('email_alert'):
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
                await self.redis.ping()  # type: ignore
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
