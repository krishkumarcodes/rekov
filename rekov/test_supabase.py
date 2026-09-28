import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    import json
    with open("config.json") as f:
        cfg = json.load(f)
        url = cfg.get("SUPABASE_URL")
        key = cfg.get("SUPABASE_KEY")

client = create_client(url, key)
try:
    with open("test.pdf", "wb") as f:
        f.write(b"%PDF-1.4...")
    res = client.storage.from_("receipts").upload("test.pdf", "test.pdf", file_options={"content-type": "application/pdf", "upsert": "true"})
    print("Upload result:", res)
    pub_url = client.storage.from_("receipts").get_public_url("test.pdf")
    print("Public URL:", pub_url)
except Exception as e:
    print("Error:", e)
