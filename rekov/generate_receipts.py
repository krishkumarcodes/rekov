import os
import urllib.request
import time
from playwright.sync_api import sync_playwright

DESKTOP_CHECKED_DIR = os.path.expanduser("~/Desktop/checked")
os.makedirs(DESKTOP_CHECKED_DIR, exist_ok=True)

def run():
    print("Waiting for frontend at http://localhost:3000...")
    for _ in range(60):
        try:
            urllib.request.urlopen("http://localhost:3000")
            break
        except Exception:
            time.sleep(1)
    else:
        print("Frontend did not start in time.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        for i in range(20):
            print(f"Generating receipt {i+1}/20...")
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            
            try:
                page.goto("http://localhost:3000/kiosk")
                
                # Step 1: Patient details
                page.wait_for_selector('input[type="text"]', timeout=10000)
                page.fill('input[type="text"]', f"Test Patient {i+1}")
                page.fill('input[type="tel"]', f"99900011{i:02d}")
                page.click("button:has-text('CONTINUE ->')")
                
                # Step 2: Department
                page.wait_for_selector('text="General Clinic"', timeout=10000)
                # Click the first department card
                page.locator('text="General Clinic"').first.click()
                page.click("button:has-text('CONTINUE ->')")
                
                # Step 3: Doctor
                page.wait_for_selector('text="Dr."', timeout=10000)
                # Click the first doctor
                page.locator('text="Dr."').first.click()
                page.click("button:has-text('CONTINUE ->')")
                
                # Step 4: Combos / Vitals
                page.wait_for_selector("button:has-text('COMPLETE CHECK-IN'), button:has-text('SKIP VITALS')", timeout=10000)
                
                # Depending on what the button says
                if page.locator("button:has-text('SKIP VITALS')").count() > 0:
                    page.click("button:has-text('SKIP VITALS')")
                else:
                    page.click("button:has-text('COMPLETE CHECK-IN')")
                
                # Modal will pop up
                # Wait for the download button
                page.wait_for_selector("button:has-text('DOWNLOAD')", timeout=20000)
                
                # Click download and save
                with page.expect_download(timeout=30000) as download_info:
                    page.click("button:has-text('DOWNLOAD')")
                
                download = download_info.value
                download.save_as(os.path.join(DESKTOP_CHECKED_DIR, f"receipt_{i+1}.pdf"))
                
                print(f"Saved: receipt_{i+1}.pdf")
            except Exception as e:
                print(f"Failed on receipt {i+1}: {e}")
            finally:
                context.close()
            
        browser.close()
        print("Done generating 20 receipts.")

if __name__ == "__main__":
    run()
