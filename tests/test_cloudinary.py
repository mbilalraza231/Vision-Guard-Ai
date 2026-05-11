import cloudinary
import cloudinary.api
import os

cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME')
api_key = os.environ.get('CLOUDINARY_API_KEY')
api_secret = os.environ.get('CLOUDINARY_API_SECRET')

print(f"DEBUG: Attempting connection with:")
print(f"  Cloud Name: [{cloud_name}]")
print(f"  API Key:    [{api_key}]")

cloudinary.config(
    cloud_name=cloud_name,
    api_key=api_key,
    api_secret=api_secret,
    secure=True
)

try:
    res = cloudinary.api.resources(max_results=1)
    print("SUCCESS: Credentials are valid.")
    if 'resources' in res:
        print(f"Successfully retrieved {len(res['resources'])} resources.")
except Exception as e:
    print(f"ERROR: {e}")
