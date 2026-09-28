import os
import time
import requests

DESKTOP_CHECKED_DIR = os.path.expanduser("~/Desktop/checked")
os.makedirs(DESKTOP_CHECKED_DIR, exist_ok=True)

def run():
    print("Generating 20 receipts via API...")
    urls_to_download = []
    
    # 1. Generate 20 tickets
    for i in range(20):
        payload = {
            "department_id": "dep_gen",
            "doctor_id": "doc_1",
            "combo_package_ids": [],
            "patient": {
                "full_name": f"API Patient {i+1}",
                "phone": f"99900011{i:02d}",
                "national_id": f"A{100000+i}",
                "age": 30 + i,
                "gender": "Male",
                "insurance_member": False
            },
            "vitals": {
                "systolic_bp": 120,
                "diastolic_bp": 80,
                "heart_rate": 72,
                "temperature": 98.6,
                "pain_score": 1,
                "symptoms": ["General Checkup"]
            }
        }
        try:
            res = requests.post("http://localhost:4040/api/v1/kiosk/ticket", json=payload, timeout=5)
            if res.status_code == 200:
                data = res.json()
                pdf_url = data.get("receipt_pdf_url")
                if pdf_url:
                    urls_to_download.append((i+1, pdf_url))
                print(f"[{i+1}/20] Ticket created: {data.get('token_number')}")
            else:
                print(f"[{i+1}/20] Failed: {res.text}")
        except Exception as e:
            print(f"[{i+1}/20] Error: {e}")
            
    # 2. Wait for background upload to complete
    print("Waiting 15s for background PDF generation & Supabase uploads to complete...")
    time.sleep(15)
    
    # 3. Download PDFs
    print("Downloading PDFs...")
    for idx, pdf_url in urls_to_download:
        filename = f"receipt_api_{idx}.pdf"
        filepath = os.path.join(DESKTOP_CHECKED_DIR, filename)
        
        # Retry logic up to 3 times
        for attempt in range(3):
            try:
                r = requests.get(pdf_url, timeout=10)
                if r.status_code == 200:
                    with open(filepath, "wb") as f:
                        f.write(r.content)
                    print(f"Downloaded: {filename}")
                    break
                else:
                    print(f"Attempt {attempt+1} failed for {filename} (HTTP {r.status_code})")
            except Exception as e:
                print(f"Attempt {attempt+1} error for {filename}: {e}")
            time.sleep(5)
            
    print("Done!")

if __name__ == "__main__":
    run()
