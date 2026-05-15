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

    async def send_twilio(self, to: str, message: str, media_url: Optional[str] = None) -> bool:
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
            if response.status_code < 300:
                logger.info(f"Twilio message sent to {to}")
                return True
            else:
                logger.error(f"Twilio error {response.status_code}: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Twilio dispatch failed: {e}")
            return False

    async def send_gmail(self, to: str, subject: str, body: str) -> bool:
        """Send Email via Gmail SMTP."""
        if not self.config.gmail_user or not self.config.gmail_password:
            logger.warning("Gmail not configured, skipping Email")
            return False

        message = MIMEMultipart()
        message["From"] = self.config.gmail_user
        message["To"] = to
        message["Subject"] = subject
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
            logger.info(f"Gmail sent to {to}")
            return True
        except Exception as e:
            logger.error(f"Gmail dispatch failed: {e}")
            return False

    async def close(self):
        await self.client.aclose()
