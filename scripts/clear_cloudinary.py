import os
import sys
import cloudinary
import cloudinary.api
from dotenv import load_dotenv

# Find and load the root .env file
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(base_dir, '.env')

if os.path.exists(dotenv_path):
    print(f"Loading environment from: {dotenv_path}")
    load_dotenv(dotenv_path)
else:
    print("Warning: .env file not found in root, falling back to system environment variables.")
    load_dotenv()

# Retrieve credentials
cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME')
api_key = os.environ.get('CLOUDINARY_API_KEY')
api_secret = os.environ.get('CLOUDINARY_API_SECRET')

if not all([cloud_name, api_key, api_secret]):
    print("ERROR: Cloudinary credentials (CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET) must be set in your .env file.")
    sys.exit(1)

# Sanitize cloud name (remove spaces)
cloud_name = cloud_name.replace(' ', '').strip()
api_key = api_key.strip()
api_secret = api_secret.strip()

print(f"Configuring Cloudinary connection...")
print(f"Cloud Name: {cloud_name}")
print(f"API Key:    {api_key[:6]}******")

cloudinary.config(
    cloud_name=cloud_name,
    api_key=api_key,
    api_secret=api_secret
)

# Resource types to clean up
resource_types = ["image", "video", "raw"]

for r_type in resource_types:
    print(f"\n--- Deleting '{r_type}' resources with prefix 'visionguard/' ---")
    deleted_total = 0
    next_cursor = None
    
    while True:
        try:
            # Delete resources by using the 'visionguard/' prefix
            result = cloudinary.api.delete_resources_by_prefix(
                "visionguard/",
                resource_type=r_type,
                next_cursor=next_cursor
            )
            deleted_dict = result.get("deleted", {})
            deleted_count = len(deleted_dict)
            deleted_total += deleted_count
            print(f"  Deleted batch of {deleted_count} {r_type}(s).")
            
            next_cursor = result.get("next_cursor")
            if not next_cursor:
                break
        except Exception as e:
            print(f"  No more resources found or error: {e}")
            break
            
    print(f"Finished '{r_type}' deletion. Total deleted: {deleted_total}")

print("\n--- Deleting VisionGuard folders ---")
# List of known VisionGuard subfolders to delete (must be empty of assets first)
folders_to_delete = [
    "visionguard/snapshots/weapon",
    "visionguard/snapshots/fire",
    "visionguard/snapshots/fall",
    "visionguard/snapshots",
    "visionguard/clips/weapon",
    "visionguard/clips/fire",
    "visionguard/clips/fall",
    "visionguard/clips",
    "visionguard"
]

for folder in folders_to_delete:
    print(f"  Deleting folder: {folder}")
    try:
        cloudinary.api.delete_folder(folder)
    except Exception as e:
        print(f"    Could not delete folder {folder}: {e}")

print("\nCloudinary account clean-up complete.")
