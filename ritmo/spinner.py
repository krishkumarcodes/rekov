"""
ritmo/spinner.py
================
ASCII animated spinner for RITMO CLI blocking tasks.
"""
import sys
import time
import threading

class Spinner:
    def __init__(self, message="Thinking..."):
        self.message = message
        self.running = False
        self.thread = None
        self.frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    
    def _spin(self):
        i = 0
        while self.running:
            sys.stdout.write(f"\r  \x1b[36m{self.frames[i]}\x1b[0m \x1b[2m{self.message}\x1b[0m")
            sys.stdout.flush()
            i = (i + 1) % len(self.frames)
            time.sleep(0.08)
            
    def __enter__(self):
        self.running = True
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.running = False
        if self.thread:
            self.thread.join()
        sys.stdout.write("\r" + " " * (len(self.message) + 15) + "\r")
        sys.stdout.flush()
