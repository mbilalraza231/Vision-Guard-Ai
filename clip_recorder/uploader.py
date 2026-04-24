"""
VisionGuard AI - Cloudinary Uploader

Handles uploading snapshots and video clips to Cloudinary.
All methods are non-blocking on failure — errors are logged, never raised.
"""

import logging
from typing import Optional

import cloudinary
import cloudinary.uploader

logger = logging.getLogger(__name__)


class CloudinaryUploader:
    """
    Upload images and videos to Cloudinary.

    All upload methods return the secure_url string on success,
    or None on any failure. They never raise exceptions.
    """

    def __init__(self, cloud_name: str, api_key: str, api_secret: str) -> None:
        """
        Initialize uploader and configure the Cloudinary SDK.

        Args:
            cloud_name: Cloudinary cloud name
            api_key:    Cloudinary API key
            api_secret: Cloudinary API secret
        """
        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
            secure=True,
        )
        logger.info(
            "Cloudinary configured",
            extra={"cloud_name": cloud_name},
        )

    def upload_snapshot(
        self,
        file_path: str,
        event_id: str,
        event_type: str,
    ) -> Optional[str]:
        """
        Upload a snapshot image to Cloudinary.

        Args:
            file_path:  Local path to the JPEG snapshot
            event_id:   UUID of the classified event
            event_type: Event type (weapon | fire | fall)

        Returns:
            secure_url string on success, None on failure
        """
        try:
            result = cloudinary.uploader.upload(
                file_path,
                folder=f"visionguard/snapshots/{event_type}",
                public_id=f"snapshot_{event_id}",
                resource_type="image",
                overwrite=True,
            )
            url: str = result["secure_url"]
            logger.info(
                "Snapshot uploaded to Cloudinary",
                extra={"event_id": event_id, "url": url},
            )
            return url
        except Exception as e:  # noqa: BLE001
            logger.error(
                f"Snapshot upload failed for event {event_id}: {e}",
                extra={"event_id": event_id, "file_path": file_path},
            )
            return None

    def upload_clip(
        self,
        file_path: str,
        event_id: str,
        event_type: str,
    ) -> Optional[str]:
        """
        Upload a video clip to Cloudinary.

        Args:
            file_path:  Local path to the MP4 clip
            event_id:   UUID of the classified event
            event_type: Event type (weapon | fire | fall)

        Returns:
            secure_url string on success, None on failure
        """
        try:
            result = cloudinary.uploader.upload(
                file_path,
                folder=f"visionguard/clips/{event_type}",
                public_id=f"clip_{event_id}",
                resource_type="video",
                overwrite=True,
            )
            url: str = result["secure_url"]
            logger.info(
                "Clip uploaded to Cloudinary",
                extra={"event_id": event_id, "url": url},
            )
            return url
        except Exception as e:  # noqa: BLE001
            logger.error(
                f"Clip upload failed for event {event_id}: {e}",
                extra={"event_id": event_id, "file_path": file_path},
            )
            return None
