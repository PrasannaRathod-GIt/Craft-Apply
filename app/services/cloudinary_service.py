"""
Assumes cloudinary.config(secure=True) is already called once at app
startup (main.py) reading CLOUDINARY_URL / CLOUDINARY_* env vars, exactly
like your Flask code did. If Phase 1 didn't add that yet:

    import cloudinary
    cloudinary.config(secure=True)

...at the top of main.py, before the app object is created.
"""

import time
from typing import Optional

import cloudinary.uploader
from fastapi import UploadFile


async def upload_job_image(file: Optional[UploadFile]) -> Optional[str]:
    """Uploads a job thumbnail to Cloudinary, returns the secure_url or None."""
    if not file or not file.filename:
        return None

    contents = await file.read()
    result = cloudinary.uploader.upload(
        contents,
        folder="resumify/job_thumbnails",
        public_id=f"job_{int(time.time())}",
        overwrite=True,
        resource_type="image",
    )
    return result.get("secure_url")
