"""
Module B2 — Claude.ai (决策官, Opus 4.6 Extended)
使用共享浏览器，报告通过粘贴传入
"""

import time
import logging

log = logging.getLogger("claude")

CLAUDE_URL = "https://claude.ai/new"
MAX_WAIT = 180


class ClaudeDriver:
    def __init__(self):
        pass

    def analyze_report(self, gemini_report: str, task_prompt: str) -> str:
        from modules.browser_manager import BrowserManager
        bm = BrowserManager.get()
        page = None
        try:
            page = bm.new_page()
            page.goto(CLAUDE_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)

            # 报告可能很长，截取关键部分避免粘贴失败
            # Claude上下文够大，但粘贴有物理限制
            if len(gemini_report) > 15000:
                gemini_report = gemini_report[:15000] + "\n\n[报告过长，已截取前15000字符]"

            full_prompt = task_prompt + "\n\n═══ GEMINI DEEP RESEARCH 报告 ═══\n\n" + gemini_report

            # 找输入框
            input_el = None
            for selector in ['div[contenteditable="true"]', 'textarea', '.ProseMirror']:
                try:
                    el = page.wait_for_selector(selector, timeout=5000)
                    if el and el.is_visible():
                        input_el = el
                        break
                except:
                    continue

            if not input_el:
                log.error("无法找到Claude输入框")
                page.screenshot(path="debug_claude_no_input.png")
                page.close()
                return None

            # 粘贴
            input_el.click()
            time.sleep(0.5)
            page.keyboard.press("Meta+a")
            time.sleep(0.2)
            page.evaluate("text => navigator.clipboard.writeText(text)", full_prompt)
            page.keyboard.press("Meta+v")
            time.sleep(2)

            # 发送
            log.info("发送给Claude Opus 4.6 Extended...")
            sent = False
            for sel in ['[aria-label="Send message"]', 'button[aria-label*="Send"]', '[data-testid="send-button"]']:
                try:
                    btn = page.wait_for_selector(sel, timeout=3000)
                    if btn and btn.is_visible():
                        btn.click()
                        sent = True
                        break
                except:
                    continue
            if not sent:
                page.keyboard.press("Enter")
            time.sleep(3)

            # 等待
            log.info("等待Claude回复...")
            start_time = time.time()
            completed = False
            while time.time() - start_time < MAX_WAIT:
                time.sleep(5)
                elapsed = int(time.time() - start_time)
                still_going = False
                for sel in ['button:has-text("Stop")', '[aria-label*="Stop"]', '.animate-spin']:
                    try:
                        el = page.query_selector(sel)
                        if el and el.is_visible():
                            still_going = True
                            break
                    except:
                        continue
                if still_going:
                    log.info(f"  思考中... ({elapsed}s)")
                    continue
                time.sleep(3)
                completed = True
                break

            if not completed:
                log.warning("Claude超时")
                page.screenshot(path="debug_claude_timeout.png")
                page.close()
                return None

            response = self._extract_response(page)
            if response:
                log.info(f"Claude回复: {len(response)}字符")
            page.close()
            return response

        except Exception as e:
            log.exception(f"Claude出错: {e}")
            if page:
                try:
                    page.screenshot(path="debug_claude_error.png")
                    page.close()
                except:
                    pass
            return None

    def _extract_response(self, page) -> str:
        for selector in ['[data-testid="assistant-message"]', '.font-claude-message', '[class*="assistant"]']:
            try:
                elements = page.query_selector_all(selector)
                if elements:
                    text = elements[-1].inner_text()
                    if text and len(text) > 10:
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
                        if (t.length > longest.length && t.length > 50) longest = t;
                    }
                    return longest;
                }
            """).strip()
        except:
            return None

    def close(self):
        pass  # 由BrowserManager统一管理
