"""
VisionGuard AI - Clip Recorder Service

Standalone service that:
1. Subscribes to vg:clip:requests Redis stream
2. Records post-event video clips from the camera
3. Uploads snapshot + clip to Cloudinary
4. Writes Cloudinary URLs to event_evidence table
"""
