import os
import json
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

load_dotenv()

firebase_creds = os.getenv("FIREBASE_CREDENTIALS")

if not firebase_creds:
    raise RuntimeError("❌ FIREBASE_CREDENTIALS not set")

try:
    # Try parsing as JSON (Render method)
    cred_dict = json.loads(firebase_creds)
    cred = credentials.Certificate(cred_dict)
    print("✅ Using Firebase credentials from ENV (JSON mode)")
except json.JSONDecodeError:
    # Fallback to file path (local dev)
    if not os.path.exists(firebase_creds):
        raise RuntimeError(f"❌ Firebase file not found: {firebase_creds}")
    cred = credentials.Certificate(firebase_creds)
    print("✅ Using Firebase credentials from FILE")

# Initialize Firebase
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)


db = firestore.client()