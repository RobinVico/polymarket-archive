import logging
from playwright.sync_api import sync_playwright

log = logging.getLogger("browser")
PROFILE_DIR = "/Users/baymaxagent/.polymarket-bot-chrome-profile-copy"

class BrowserManager:
    _instance = None
    def __init__(self):
        self._pw = None
        self.context = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def ensure_browser(self):
        if self.context:
            return
        self._pw = sync_playwright().start()
        self.context = self._pw.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR, headless=False, channel="chrome",
            viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled", "--disable-infobars", "--no-first-run"],
            slow_mo=500,
        )
        for p in self.context.pages:
            p.add_init_script('Object.defineProperty(navigator, "webdriver", {get: () => undefined})')
        log.info("Browser started")

    def new_page(self):
        self.ensure_browser()
        page = self.context.new_page()
        page.add_init_script('Object.defineProperty(navigator, "webdriver", {get: () => undefined})')
        return page

    def close(self):
        try:
            if self.context: self.context.close(); self.context = None
            if self._pw: self._pw.stop(); self._pw = None
            BrowserManager._instance = None
        except: pass
