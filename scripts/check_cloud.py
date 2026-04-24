import cloudinary
import cloudinary.api
import os
import sys

try:
    cloudinary.config(
      cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME', '').replace(' ', ''),
      api_key = os.environ.get('CLOUDINARY_API_KEY'),
      api_secret = os.environ.get('CLOUDINARY_API_SECRET')
    )
    
    print("Checking Cloudinary configuration...")
    res = cloudinary.api.resources(max_results=50)
    
    if 'resources' in res and len(res['resources']) > 0:
        print(f"Found {len(res['resources'])} resources:")
        for r in res['resources']:
            print(f"- {r.get('resource_type', 'unknown')}: {r.get('public_id', 'unknown')} ({r.get('url', 'no url')})")
    else:
        print('No resources found on this account.')
except Exception as e:
    print('ERROR communicating with Cloudinary:')
    print(str(e))
