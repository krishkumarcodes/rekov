import os
import requests
from playwright.sync_api import sync_playwright
import time
import random

FRONTEND_URL = "http://localhost:3000"
BACKEND_URL = "http://localhost:4040/api/v1"
CHECKED_DIR = os.path.expanduser(r"~\Desktop\checked")

os.makedirs(CHECKED_DIR, exist_ok=True)

def generate_random_patient():
    first_names = ["John", "Jane", "Alice", "Bob", "Charlie", "Diana", "Ethan", "Fiona", "George", "Hannah"]
    last_names = ["Smith", "Doe", "Johnson", "Brown", "Williams", "Jones", "Miller", "Davis", "Garcia", "Rodriguez"]
    name = f"{random.choice(first_names)} {random.choice(last_names)}"
    phone = f"9876{random.randint(100000, 999999)}"
    return name, phone

def run_test():
    print(f"Testing environment: {FRONTEND_URL}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        for i in range(1, 21):
            try:
                print(f"--- Generating Receipt {i}/20 ---")
                name, phone = generate_random_patient()
                
                # We will intercept the create_ticket network response to grab the receipt_pdf_url
                pdf_url = None
                def handle_response(response):
                    nonlocal pdf_url
                    if "api/v1/kiosk/ticket" in response.url and response.status == 200:
                        try:
                            data = response.json()
                            print(f"[DEBUG] create_ticket response: {data}")
                            if "receipt_pdf_url" in data:
                                pdf_url = data["receipt_pdf_url"]
                        except Exception as e:
                            print(f"[DEBUG] Failed to parse create_ticket response: {e}")
                page.on("response", handle_response)
                
                # Step 1: Start at Home
                page.goto(FRONTEND_URL)
                page.wait_for_load_state("networkidle")
                
                # Click Continue Button to go to kiosk
                page.wait_for_selector("button.btn-continue-slide", timeout=10000)
                page.click("button.btn-continue-slide")
                
                # Step 1 (Kiosk): Patient Identity
                page.wait_for_selector("text=PATIENT DETAILS", timeout=5000)
                page.fill("input[placeholder='e.g. Jane Doe']", name)
                page.fill("input[placeholder='10-digit mobile number']", phone)
                page.click("button:has-text('CONTINUE ->')")
                
                # Step 2: Select Department
                page.wait_for_selector("text=Cardiology", timeout=5000)
                page.click("text=Cardiology")
                page.click("button:has-text('CONTINUE ->')")
                
                # Step 3: Select Doctor
                page.wait_for_selector("text=Dr. Priya Patel", timeout=5000)
                page.click("text=Dr. Priya Patel")
                page.click("button:has-text('CONTINUE ->')")
                
                # Step 4: Vitals
                page.wait_for_selector("text=SKIP VITALS", timeout=5000)
                # Submit (click COMPLETE CHECK-IN)
                page.click("button:has-text('COMPLETE CHECK-IN')")
                
                # Step 5: Wait for Ticket Modal
                page.wait_for_selector("text=CHECK-IN COMPLETE", timeout=10000)
                
                print("Ticket generated! Waiting for PDF URL...")
                for _ in range(20):
                    if pdf_url:
                        break
                    page.wait_for_timeout(500)
                
                if pdf_url:
                    print(f"Found PDF URL target: {pdf_url}")
                    # Give it a few seconds to upload to Supabase
                    time.sleep(5)
                    
                    # Download the PDF
                    resp = requests.get(pdf_url)
                    if resp.status_code == 200:
                        file_path = os.path.join(CHECKED_DIR, f"receipt_{i}.pdf")
                        with open(file_path, "wb") as f:
                            f.write(resp.content)
                        print(f"[OK] Successfully downloaded receipt {i} to {file_path}")
                    else:
                        print(f"[ERROR] Failed to download PDF. Status: {resp.status_code}")
                else:
                    print("[ERROR] PDF URL not found in response!")
                
                # Close Modal
                page.click("button:has-text('NO, FINISH')", force=True)
                page.wait_for_timeout(1000)
                
            except Exception as e:
                print(f"Failed on receipt {i}: {e}")
                
        browser.close()

if __name__ == "__main__":
    run_test()
