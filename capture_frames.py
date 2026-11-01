import time
import os
from playwright.sync_api import sync_playwright

VIDEO_URL = "https://www.youtube.com/watch?v=iMBI3ZcQ6sU"
OUTPUT_DIR = "/workspace/data/frames/iMBI3ZcQ6sU/tail"
START_TIME = 4698  # 1:18:18
END_TIME = 5298    # End of video

def capture_frames():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        
        print(f"Navigating to {VIDEO_URL}")
        page.goto(VIDEO_URL, wait_until='domcontentloaded', timeout=30000)
        time.sleep(5)
        
        # Check page content
        page_text = page.content()
        
        # Try to dismiss cookie consent if present
        try:
            consent_buttons = ['button:has-text("Accept all")', 'button:has-text("Reject all")', 'button:has-text("I agree")']
            for selector in consent_buttons:
                try:
                    button = page.locator(selector).first
                    if button.is_visible(timeout=1000):
                        button.click()
                        print(f"Clicked consent button: {selector}")
                        time.sleep(1)
                        break
                except:
                    pass
        except:
            pass
        
        # Take screenshot of current state
        page.screenshot(path=f"{OUTPUT_DIR}/initial_page.png", full_page=False)
        print("Captured initial page state")
        
        # Check if bot detection is present
        if "Sign in to confirm" in page_text or "not a bot" in page_text:
            print("WARNING: Bot detection detected on page")
            with open(f"{OUTPUT_DIR}/BROWSER_CAPTURE.txt", "w") as f:
                f.write(f"Video: {VIDEO_URL}\n")
                f.write(f"Capture successful: NO\n")
                f.write(f"Error: YouTube bot detection blocking playback\n\n")
                f.write("The video page loaded but YouTube is blocking playback with 'Sign in to confirm you're not a bot' message.\n")
                f.write("See initial_page.png for screenshot of the blocking message.\n")
            browser.close()
            return False
        
        # Check if video player is available
        try:
            video_element = page.locator('video').first
            video_element.wait_for(timeout=10000)
            print("Video player found")
        except Exception as e:
            print(f"ERROR: Video player not found: {e}")
            with open(f"{OUTPUT_DIR}/BROWSER_CAPTURE.txt", "w") as f:
                f.write(f"Video: {VIDEO_URL}\n")
                f.write(f"Capture successful: NO\n")
                f.write(f"Error: Video player not found\n")
                f.write(f"Details: {str(e)}\n")
            browser.close()
            return False
        
        # Wait for video to be ready
        time.sleep(3)
        
        # Skip to start time using JavaScript
        print(f"Seeking to {START_TIME} seconds...")
        page.evaluate(f"""
            const video = document.querySelector('video');
            if (video) {{
                video.currentTime = {START_TIME};
                video.pause();
            }}
        """)
        time.sleep(3)
        
        # Capture frames throughout the last 10 minutes
        frame_count = 0
        capture_times = []
        
        # Capture every ~30 seconds through the last 10 minutes
        for offset in range(0, 600, 30):  # 0, 30, 60, ... 570 seconds
            target_time = START_TIME + offset
            if target_time > END_TIME:
                break
                
            # Seek to target time
            page.evaluate(f"""
                const video = document.querySelector('video');
                if (video) {{
                    video.currentTime = {target_time};
                    video.pause();
                }}
            """)
            time.sleep(3)  # Wait for seek and frame to stabilize
            
            # Get current time for filename
            try:
                current_time = page.evaluate("""
                    const video = document.querySelector('video');
                    return video ? video.currentTime : 0;
                """)
            except:
                current_time = target_time
            
            minutes = int(current_time // 60)
            seconds = int(current_time % 60)
            filename = f"{OUTPUT_DIR}/{minutes:02d}-{seconds:02d}.png"
            
            page.screenshot(path=filename, full_page=False)
            frame_count += 1
            capture_times.append(f"{minutes}:{seconds:02d}")
            print(f"Captured frame {frame_count}: {minutes}:{seconds:02d}")
            
        browser.close()
        
        # Write report
        with open(f"{OUTPUT_DIR}/BROWSER_CAPTURE.txt", "w") as f:
            f.write(f"Video: {VIDEO_URL}\n")
            f.write(f"Title: SOXX short | 28 Oct 2026\n")
            f.write(f"Channel: martinlukkt\n")
            f.write(f"Capture successful: Yes\n")
            f.write(f"Frames captured: {frame_count}\n")
            f.write(f"Timestamps: {', '.join(capture_times)}\n\n")
            f.write("Note: Full browser screenshots captured from last ~10 minutes of video.\n")
            f.write("Stock watchlist may be visible on right side of screen if Martin displayed it.\n")
            f.write("Recommend manual inspection of frames to identify ticker symbols.\n")
            f.write("\nTickers visible: (Manual inspection required)\n")
        
        print(f"\nCapture complete! {frame_count} frames saved to {OUTPUT_DIR}")
        return True

if __name__ == "__main__":
    success = capture_frames()
    if not success:
        print("\nCapture failed - see BROWSER_CAPTURE.txt for details")
        exit(1)
