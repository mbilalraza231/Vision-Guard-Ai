import logging
import json
import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional
import aiosmtplib
import httpx

from .config import AlertConfig

logger = logging.getLogger(__name__)

class AlertNotifier:
    """Handles dispatching alerts via Twilio (SMS/WhatsApp) and Gmail (SMTP)."""
    
    def __init__(self, config: AlertConfig):
        self.config = config
        self.client = httpx.AsyncClient(timeout=10.0)

    def anonymize_value(self, val: str) -> str:
        """Mask emails and phone numbers to respect user privacy settings."""
        if not val:
            return ""
        if "@" in val:  # email
            try:
                parts = val.split("@")
                name = parts[0]
                domain = parts[1]
                if len(name) > 2:
                    return name[:2] + "***@" + domain
                return "***@" + domain
            except:
                return "***@***.***"
        elif val.startswith("whatsapp:") or val.startswith("+"):  # phone/whatsapp
            prefix = "whatsapp:" if val.startswith("whatsapp:") else ""
            num = val.replace("whatsapp:", "")
            if len(num) > 5:
                return prefix + num[:3] + "******" + num[-2:]
            return prefix + "******"
        return "***"

    async def send_twilio(self, to: str, message: str, media_url: Optional[str] = None, anonymize: bool = False) -> bool:
        """Send SMS or WhatsApp via Twilio."""
        if not self.config.twilio_sid or not self.config.twilio_auth_token:
            logger.warning("Twilio not configured, skipping SMS/WhatsApp")
            return False

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.config.twilio_sid}/Messages.json"
        
        # Both From and To must have 'whatsapp:' prefix for WhatsApp messages
        is_whatsapp = to.startswith("whatsapp:")
        from_number = self.config.twilio_from
        if is_whatsapp and from_number and not from_number.startswith("whatsapp:"):
            from_number = f"whatsapp:{from_number}"
            
        data = {
            "To": to,
            "From": from_number,
            "Body": message
        }
        if media_url:
            data["MediaUrl"] = media_url

        try:
            response = await self.client.post(
                url,
                data=data,
                auth=(self.config.twilio_sid, self.config.twilio_auth_token)
            )
            to_log = self.anonymize_value(to) if anonymize else to
            if response.status_code < 300:
                logger.info(f"Twilio message sent to {to_log}")
                return True
            else:
                logger.error(f"Twilio error {response.status_code} for {to_log}: {response.text}")
                return False
        except Exception as e:
            to_log = self.anonymize_value(to) if anonymize else to
            logger.error(f"Twilio dispatch failed for {to_log}: {e}")
            return False

    async def send_gmail(self, to: str, subject: str, body: str, anonymize: bool = False) -> bool:
        """Send Email via Gmail SMTP."""
        if not self.config.gmail_user or not self.config.gmail_password:
            logger.warning("Gmail not configured, skipping Email")
            return False

        message = MIMEMultipart()
        message["From"] = self.config.gmail_user
        message["To"] = to
        message["Subject"] = subject
        # Add unique headers to prevent email grouping
        import time
        import uuid
        message["Message-ID"] = f"<{uuid.uuid4()}@visionguard.ai>"
        message["X-Entity-SE-UUID"] = str(uuid.uuid4())
        message["Date"] = time.strftime("%a, %d %b %Y %H:%M:%S %z")
        message.attach(MIMEText(body, "html"))

        try:
            await aiosmtplib.send(
                message,
                hostname="smtp.gmail.com",
                port=587,
                username=self.config.gmail_user,
                password=self.config.gmail_password,
                start_tls=True,
            )
            to_log = self.anonymize_value(to) if anonymize else to
            logger.info(f"Gmail sent to {to_log}")
            return True
        except Exception as e:
            to_log = self.anonymize_value(to) if anonymize else to
            logger.error(f"Gmail dispatch failed for {to_log}: {e}")
            return False

    async def close(self):
        await self.client.aclose()
