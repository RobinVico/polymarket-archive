"""
Claude Research — single AI engine
Opens Claude.ai, activates Research mode, sends prompt, waits, extracts response
"""
import time
import json
import re
import logging

log = logging.getLogger("claude_research")
CLAUDE_URL = "https://claude.ai/new"
MAX_WAIT = 1500  # 25 minutes


class ClaudeResearch:
    def __init__(self):
        pass

    def run(self, prompt, timeout_minutes=25):
        from playwright.sync_api import sync_playwright
        pw = None
        page = None
        try:
            # 每次创建新浏览器实例，避免跨线程问题
            PROFILE = "/Users/baymaxagent/.polymarket-bot-chrome-profile-copy"
            
            # 清理锁文件，防止"profile already in use"错误
            import os
            for lock_file in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
                lock_path = os.path.join(PROFILE, lock_file)
                try:
                    if os.path.exists(lock_path):
                        os.remove(lock_path)
                        log.info(f"Removed lock: {lock_file}")
                except:
                    pass
            
            pw = sync_playwright().start()
            context = pw.chromium.launch_persistent_context(
                user_data_dir=PROFILE, headless=False, channel="chrome",
                viewport={"width": 1280, "height": 900},
                args=["--disable-blink-features=AutomationControlled", "--disable-infobars", "--no-first-run"],
                slow_mo=500,
            )
            page = context.new_page()
            page.goto(CLAUDE_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)

            # Activate Research mode
            self._activate_research(page)
            time.sleep(2)

            # Find input
            input_el = None
            for sel in ['div[contenteditable="true"]', 'textarea', '.ProseMirror']:
                try:
                    el = page.wait_for_selector(sel, timeout=5000)
                    if el and el.is_visible():
                        input_el = el
                        break
                except:
                    continue
            if not input_el:
                log.error("No input box found")
                page.screenshot(path="debug_cr_no_input.png")
                page.close()
                return None

            # Paste prompt
            input_el.click(force=True)
            time.sleep(0.5)
            page.keyboard.press("Meta+a")
            time.sleep(0.2)
            page.evaluate("text => navigator.clipboard.writeText(text)", prompt)
            page.keyboard.press("Meta+v")
            time.sleep(2)

            # Send
            log.info("Sending to Claude Research...")
            sent = False
            for sel in ['[aria-label="Send message"]', 'button[aria-label*="Send"]']:
                try:
                    btn = page.wait_for_selector(sel, timeout=3000)
                    if btn and btn.is_visible():
                        btn.click(force=True)
                        sent = True
                        break
                except:
                    continue
            if not sent:
                page.keyboard.press("Enter")
            time.sleep(5)

            # Wait for Research completion
            max_wait = timeout_minutes * 60
            log.info(f"Waiting for Claude Research (max {timeout_minutes}min)...")
            start = time.time()

            # 先等30秒让Research开始
            time.sleep(30)

            while time.time() - start < max_wait:
                time.sleep(10)
                elapsed = int(time.time() - start)

                # 多种方式检测是否还在生成
                still_going = False

                # 方法1: Stop按钮
                for sel in ['button:has-text("Stop")', '[aria-label*="Stop"]']:
                    try:
                        el = page.query_selector(sel)
                        if el and el.is_visible():
                            still_going = True
                            break
                    except:
                        continue

                # 方法2: 检测动画/loading元素
                if not still_going:
                    try:
                        still_going = page.evaluate("""
                            () => {
                                const spinners = document.querySelectorAll('.animate-spin, [class*="loading"], [class*="streaming"], [data-is-streaming]');
                                for (const s of spinners) {
                                    if (s.offsetWidth > 0) return true;
                                }
                                return false;
                            }
                        """)
                    except:
                        pass

                # 方法3: 检测回复内容是否还在增长
                if not still_going:
                    try:
                        current_len = page.evaluate("""
                            () => {
                                const msgs = document.querySelectorAll('[data-testid="assistant-message"], .font-claude-message, [class*="assistant"]');
                                if (msgs.length === 0) return 0;
                                return msgs[msgs.length - 1].innerText.length;
                            }
                        """)
                        time.sleep(5)
                        new_len = page.evaluate("""
                            () => {
                                const msgs = document.querySelectorAll('[data-testid="assistant-message"], .font-claude-message, [class*="assistant"]');
                                if (msgs.length === 0) return 0;
                                return msgs[msgs.length - 1].innerText.length;
                            }
                        """)
                        if new_len > current_len:
                            still_going = True
                    except:
                        pass

                if still_going:
                    log.info(f"  researching... ({elapsed}s)")
                    continue

                # 额外等10秒确认真的停了
                time.sleep(10)
                try:
                    final_check = page.evaluate("""
                        () => {
                            const msgs = document.querySelectorAll('[data-testid="assistant-message"], .font-claude-message, [class*="assistant"]');
                            if (msgs.length === 0) return 0;
                            return msgs[msgs.length - 1].innerText.length;
                        }
                    """)
                    time.sleep(5)
                    final_check2 = page.evaluate("""
                        () => {
                            const msgs = document.querySelectorAll('[data-testid="assistant-message"], .font-claude-message, [class*="assistant"]');
                            if (msgs.length === 0) return 0;
                            return msgs[msgs.length - 1].innerText.length;
                        }
                    """)
                    if final_check2 > final_check:
                        log.info(f"  still growing... ({elapsed}s)")
                        continue
                except:
                    pass

                log.info(f"  Research complete ({elapsed}s)")
                break

            # Research完成，不需要读取报告内容
            # 直接在同一对话追问要JSON，Claude知道自己刚研究了什么
            log.info("Research complete, sending JSON follow-up...")
            time.sleep(5)

            followup = """Based on your research above, now output ONLY a single line of JSON. No other text.

If you found a recommendation:
{"bets":[{"slug":"exact-polymarket-slug","q":"full question","side":"YES or NO","mp":0.03,"tp":0.12,"conf":"medium","settle":"2026-xx-xx","reason":"50 char reason"}]}

If no recommendation:
{"bets":[]}

Output only the JSON line, nothing else."""

            input_el2 = None
            for sel in ['div[contenteditable="true"]', 'textarea', '.ProseMirror']:
                try:
                    el = page.wait_for_selector(sel, timeout=5000)
                    if el and el.is_visible():
                        input_el2 = el
                        break
                except:
                    continue

            if input_el2:
                input_el2.click(force=True)
                time.sleep(0.5)
                page.keyboard.press("Meta+a")
                time.sleep(0.2)
                page.evaluate("text => navigator.clipboard.writeText(text)", followup)
                page.keyboard.press("Meta+v")
                time.sleep(1)

                # Send
                for sel in ['[aria-label="Send message"]', 'button[aria-label*="Send"]']:
                    try:
                        btn = page.wait_for_selector(sel, timeout=3000)
                        if btn and btn.is_visible():
                            btn.click(force=True)
                            break
                    except:
                        continue

                # Wait for JSON reply (should be fast, not Research)
                log.info("Waiting for JSON reply...")
                start2 = time.time()
                while time.time() - start2 < 120:
                    time.sleep(5)
                    still = False
                    for sel in ['button:has-text("Stop")', '[aria-label*="Stop"]']:
                        try:
                            el = page.query_selector(sel)
                            if el and el.is_visible():
                                still = True
                                break
                        except:
                            continue
                    if not still:
                        time.sleep(3)
                        break

                json_response = self._extract_response(page)
                if json_response:
                    log.info(f"JSON reply: {len(json_response)} chars")
                    page.close()
                    return json_response

            log.warning("No JSON response received")
            try: context.close()
            except: pass
            try: pw.stop()
            except: pass
            return None

        except Exception as e:
            log.exception(f"Claude Research error: {e}")
            if page:
                try: page.screenshot(path="debug_cr_error.png")
                except: pass
            try:
                if context: context.close()
                if pw: pw.stop()
            except: pass
            return None

    def _activate_research(self, page):
        """Click + button then Research — with retries"""
        log.info("Activating Research mode...")

        for attempt in range(3):
            try:
                log.info(f"  attempt {attempt+1}/3")

                # 1. Wait for page to be ready
                time.sleep(3)

                # 2. Click the + button
                plus_btn = page.wait_for_selector('[aria-label="Add files, connectors, and more"]', timeout=10000)
                if plus_btn and plus_btn.is_visible():
                    plus_btn.click(force=True)
                    log.info("  Plus menu clicked")
                else:
                    log.warning("  Plus button not visible")
                    continue

                # 3. Wait for menu to appear
                time.sleep(3)

                # 4. Click Research — scan all elements
                clicked = False
                items = page.query_selector_all('button, [role="menuitem"], div, span')
                for item in items:
                    try:
                        txt = (item.inner_text() or '').strip()
                        if txt == 'Research' and item.is_visible():
                            item.click(force=True)
                            clicked = True
                            log.info("  Research clicked!")
                            break
                    except:
                        continue

                if not clicked:
                    # Try text selector
                    try:
                        page.click('text=Research', force=True)
                        clicked = True
                        log.info("  Research clicked via text selector")
                    except:
                        pass

                if clicked:
                    time.sleep(3)
                    return True
                else:
                    log.warning("  Research not found, pressing Escape and retrying")
                    page.keyboard.press('Escape')
                    time.sleep(2)

            except Exception as e:
                log.warning(f"  attempt {attempt+1} error: {e}")
                page.keyboard.press('Escape')
                time.sleep(2)

        log.error("Could not activate Research mode after 3 attempts")
        page.screenshot(path="debug_research_fail.png")
        return False

    def _extract_response(self, page):
        for sel in ['[data-testid="assistant-message"]', '.font-claude-message', '[class*="assistant"]']:
            try:
                elements = page.query_selector_all(sel)
                if elements:
                    text = elements[-1].inner_text()
                    if text and len(text) > 50:
                        return text.strip()
            except: continue
        try:
            return page.evaluate("""
                () => {
                    const els = document.querySelectorAll('div, p, span');
                    let longest = '';
                    for (const el of els) {
                        const t = el.innerText || '';
                        if (t.length > longest.length && t.length > 100) longest = t;
                    }
                    return longest;
                }
            """).strip()
        except: return None

    @staticmethod
    def extract_json(response_text):
        if not response_text:
            return {"bets": [], "_error": "empty response"}

        lines = response_text.strip().split('\n')
        # Search from end for JSON line
        for line in reversed(lines):
            line = line.strip()
            if line.startswith('{') and line.endswith('}'):
                try:
                    data = json.loads(line)
                    if "bets" in data or "action" in data:
                        return data
                except: continue

        # Regex fallback for bets
        for pattern in [r'\{"bets":\[.*?\]\}', r'\{"bets":\[.*?\]\s*\}']:
            matches = re.findall(pattern, response_text, re.DOTALL)
            if matches:
                try: return json.loads(matches[-1])
                except: continue

        # Regex for position review
        matches = re.findall(r'\{"action":"(?:hold|sell|add)"[^}]*\}', response_text)
        if matches:
            try: return json.loads(matches[-1])
            except: pass

        # Bare JSON fallback
        depth = 0; end = -1; start = -1
        for i in range(len(response_text) - 1, -1, -1):
            if response_text[i] == '}':
                if end == -1: end = i
                depth += 1
            elif response_text[i] == '{':
                depth -= 1
                if depth == 0 and end != -1:
                    start = i; break
        if start != -1 and end != -1:
            try:
                data = json.loads(response_text[start:end+1])
                if "bets" in data or "action" in data or "slug" in data:
                    return data
            except: pass

        return {"bets": [], "_error": "no JSON found"}
