"""
Module B1 — Gemini Deep Research Pro (情报员)
"""

import time
import logging

log = logging.getLogger("gemini")

GEMINI_URL = "https://gemini.google.com/app"
MAX_WAIT_SECONDS = 1800
POLL_INTERVAL = 10


class GeminiDriver:
    def __init__(self, chrome_user_data_dir: str = ""):
        pass

    def run_deep_research(self, prompt: str) -> str:
        from modules.browser_manager import BrowserManager
        bm = BrowserManager.get()
        page = None
        try:
            page = bm.new_page()
            page.goto(GEMINI_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)

            # 关掉所有可能的弹窗/overlay
            self._dismiss_popups(page)
            time.sleep(2)

            # 设置 Deep Research Pro
            log.info("点击 Tools...")
            page.click('button:has-text("Tools")', force=True, timeout=10000)
            time.sleep(2)

            log.info("点击 Deep Research...")
            for sel in ['text=Deep Research', 'button:has-text("Deep Research")']:
                try:
                    el = page.wait_for_selector(sel, timeout=3000)
                    if el and el.is_visible():
                        el.click(force=True)
                        log.info("Deep Research 已选择")
                        break
                except:
                    continue
            time.sleep(2)

            # 关overlay
            self._dismiss_popups(page)
            time.sleep(1)

            # 选Pro模式
            log.info("选择 Pro 模式...")
            fast_clicked = False
            for sel in ['[aria-label="Open mode picker"]', 'button:has-text("Fast")']:
                try:
                    btn = page.wait_for_selector(sel, timeout=5000)
                    if btn and btn.is_visible():
                        btn.click(force=True)
                        fast_clicked = True
                        log.info("Mode picker已打开")
                        break
                except:
                    continue
            time.sleep(2)

            if fast_clicked:
                pro_clicked = False
                try:
                    # 精确匹配：找包含'Advanced math'的那个Pro选项
                    items = page.query_selector_all('button, [role="menuitem"], [role="option"], div[role="button"], li')
                    for item in items:
                        txt = (item.inner_text() or '').strip()
                        if 'Advanced math' in txt or (txt == 'Pro' and item.is_visible()):
                            item.click(force=True)
                            pro_clicked = True
                            log.info(f"已选择 Pro (text='{txt[:30]}')")
                            break
                    if not pro_clicked:
                        # 备选：用文本精确匹配
                        el = page.locator('text=Advanced math and code').first
                        el.click(force=True)
                        log.info("已选择 Pro (via Advanced math text)")
                except Exception as ex:
                    log.warning(f"Pro选择失败: {ex}")
                time.sleep(2)

            # 输入prompt
            input_el = self._find_input(page)
            if not input_el:
                page.close()
                return None
            self._paste_text(page, input_el, prompt)

            # 发送
            self._click_send(page)
            time.sleep(5)

            # 点"开始研究"
            self._click_start_research(page)
            time.sleep(5)

            # 等待完成
            log.info(f"等待Deep Research（最长{MAX_WAIT_SECONDS}秒）...")
            if not self._wait_for_completion(page):
                page.close()
                return None

            output = self._extract_response(page)
            if output:
                log.info(f"Gemini报告: {len(output)}字符")
            page.close()
            return output

        except Exception as e:
            log.exception(f"Gemini出错: {e}")
            if page:
                try:
                    page.screenshot(path="debug_gemini_error.png")
                    page.close()
                except:
                    pass
            return None

    def _dismiss_popups(self, page):
        """关掉Gemini的各种弹窗和overlay"""
        # 点 "Not now" / "关闭" 等按钮
        for sel in ['button:has-text("Not now")', 'button:has-text("Dismiss")', 'button:has-text("Close")', 'button:has-text("关闭")', 'button:has-text("以后再说")']:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click(force=True)
                    log.info(f"关闭弹窗: {sel}")
                    time.sleep(1)
            except:
                continue

        # 按Escape关闭overlay
        page.keyboard.press('Escape')
        time.sleep(0.5)
        page.keyboard.press('Escape')
        time.sleep(0.5)

        # 直接用JS移除overlay
        try:
            page.evaluate("""
                document.querySelectorAll('.cdk-overlay-backdrop').forEach(el => el.remove());
                document.querySelectorAll('.cdk-overlay-container').forEach(el => {
                    el.style.pointerEvents = 'none';
                });
            """)
            log.info("已用JS清除overlay")
        except:
            pass

    def _find_input(self, page):
        for sel in ['div[contenteditable="true"]', 'rich-textarea div[contenteditable="true"]', 'textarea']:
            try:
                el = page.wait_for_selector(sel, timeout=5000)
                if el and el.is_visible():
                    return el
            except:
                continue
        log.error("无法找到输入框")
        page.screenshot(path="debug_no_input.png")
        return None

    def _paste_text(self, page, input_el, text):
        input_el.click(force=True)
        time.sleep(0.5)
        page.keyboard.press("Meta+a")
        time.sleep(0.2)
        page.evaluate("text => navigator.clipboard.writeText(text)", text)
        page.keyboard.press("Meta+v")
        time.sleep(2)

    def _click_send(self, page):
        for sel in ['[aria-label="Send message"]', 'button[aria-label*="Send"]']:
            try:
                btn = page.wait_for_selector(sel, timeout=3000)
                if btn and btn.is_visible():
                    btn.click(force=True)
                    return
            except:
                continue
        page.keyboard.press("Enter")

    def _click_start_research(self, page):
        time.sleep(10)
        for sel in ['button:has-text("开始研究")', 'button:has-text("Start research")', 'button:has-text("Start")']:
            try:
                btn = page.wait_for_selector(sel, timeout=15000)
                if btn and btn.is_visible():
                    btn.click(force=True)
                    log.info(f"已点击: {sel}")
                    return
            except:
                continue
        try:
            for b in page.query_selector_all("button"):
                txt = (b.inner_text() or "").strip()
                if "开始" in txt or "Start" in txt:
                    b.click(force=True)
                    return
        except:
            pass

    def _wait_for_completion(self, page):
        start = time.time()
        while time.time() - start < MAX_WAIT_SECONDS:
            time.sleep(POLL_INTERVAL)
            elapsed = int(time.time() - start)
            still_going = False
            for sel in ['button:has-text("Stop")', 'button:has-text("停止")', '[aria-label*="Stop"]']:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        still_going = True
                        break
                except:
                    continue
            if still_going:
                log.info(f"  研究中... ({elapsed}s)")
                continue
            time.sleep(5)
            return True
        log.warning("超时")
        page.screenshot(path="debug_timeout.png")
        return False

    def _extract_response(self, page) -> str:
        for sel in ['.response-content', '.model-response-text', '[data-message-author-role="model"]', '.markdown-main-panel']:
            try:
                elements = page.query_selector_all(sel)
                if elements:
                    text = elements[-1].inner_text()
                    if text and len(text) > 100:
                        return text.strip()
            except:
                continue
        try:
            return page.evaluate("""
                () => {
                    const els = document.querySelectorAll('div, p, span');
                    let longest = '';
                    for (const el of els) {
                        const t = el.innerText || '';
                        if (t.length > longest.length && t.length > 200) longest = t;
                    }
                    return longest;
                }
            """).strip()
        except:
            return None

    def close(self):
        pass
