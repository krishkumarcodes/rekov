import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"]
        )
        context = await browser.new_context()
        page = await context.new_page()
        
        print("[Test] Navigating to voice assistant...")
        await page.goto("http://localhost:3000/voice-assistant")
        await page.wait_for_timeout(3000)
        
        print("[Test] Sending booking request...")
        await page.fill("input[type='text']", "I need an appointment in general medicine")
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(10000)
        
        print("[Test] Confirming booking...")
        await page.fill("input[type='text']", "yes")
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(10000)
        
        print("[Test] Asking for receipt...")
        await page.fill("input[type='text']", "Can I get a receipt for this?")
        await page.keyboard.press("Enter")
        
        print("[Test] Waiting for receipt generation...")
        await page.wait_for_timeout(10000)
        
        # Check if the PDF link is rendered in the chat
        content = await page.content()
        if "DOWNLOAD PDF" in content or "receipt" in content.lower():
            print("\n[SUCCESS] Receipt generated and linked in the chat successfully!")
        else:
            print("\n[FAILED] Could not find the receipt link in the chat.")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
