#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import time
import subprocess
import requests
from datetime import datetime, timezone, timedelta
from seleniumbase import Driver

# ====================== 配置区域 ======================
HIDENCLOUD = os.getenv("HIDENCLOUD", "")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")
PROXY_SERVER = os.getenv("PROXY_SERVER", "")

if "-----" in HIDENCLOUD:
    HIDEN_EMAIL, HIDEN_PWD = HIDENCLOUD.split("-----", 1)
else:
    raise ValueError("❌ HIDENCLOUD 格式错误，应为 email-----password")

BASE_URL = "https://dash.hidencloud.com"
STATE_DIR = "browser_state"
SCREENSHOT_DIR = "screenshots"

os.makedirs(STATE_DIR, exist_ok=True)
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

USER_DATA_DIR = os.path.abspath(os.path.join(STATE_DIR, "selenium_profile"))

# ====================== 工具函数 ======================
def get_bj_time():
    """返回北京时间字符串"""
    return (datetime.now(timezone.utc) + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')

def send_tg_notification(message, photo_path=None):
    """发送 Telegram 通知，可附带截图"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("[WARN] 未配置 TG 信息，跳过发送")
        return
    try:
        if photo_path and os.path.exists(photo_path):
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
            with open(photo_path, 'rb') as f:
                files = {'photo': f}
                data = {'chat_id': TG_CHAT_ID, 'caption': message, 'parse_mode': 'Markdown'}
                requests.post(url, files=files, data=data, timeout=30)
        else:
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
            payload = {"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "Markdown"}
            requests.post(url, json=payload, timeout=10)
        print("[INFO] 📡 TG 通知已发送")
    except Exception as e:
        print(f"[ERROR] TG 发送失败: {e}")

def take_screenshot(driver, name):
    """截图并返回文件路径"""
    timestamp = datetime.now().strftime('%H%M%S')
    filename = f"{SCREENSHOT_DIR}/{timestamp}-{name}.png"
    try:
        driver.save_screenshot(filename)
        print(f"[INFO] 📸 截图 → {filename}")
    except Exception as e:
        print(f"[WARN] 截图失败: {e}")
    return filename

def wait_for_turnstile_token(driver, timeout=90):
    """等待 Cloudflare Turnstile token 生成"""
    print("[INFO] ⏳ 等待 Turnstile 验证通过...")
    start = time.time()
    while time.time() - start < timeout:
        token = driver.execute_script(
            'return document.querySelector("[name=cf-turnstile-response]")?.value'
        )
        if token and len(token) > 20:
            print("[INFO] ✅ Turnstile token 已生成")
            return True
        time.sleep(1)
    return False

def wait_for_url_contains(driver, keyword, timeout=45):
    """等待当前 URL 包含特定关键字"""
    start = time.time()
    while time.time() - start < timeout:
        if keyword in driver.current_url:
            return True
        time.sleep(0.5)
    return False

def check_login_error(driver):
    """检查页面是否有登录错误信息"""
    try:
        error_selectors = [
            ".text-red-500", ".alert-danger", "[role='alert']", ".error", ".invalid-feedback"
        ]
        for sel in error_selectors:
            elem = driver.find_element(sel, by="css selector")
            if elem and elem.is_displayed() and elem.text.strip():
                return elem.text.strip()
    except:
        pass
    return None

def mask_email(email):
    """邮箱脱敏显示"""
    if '@' in email:
        local, domain = email.split('@', 1)
        return f"{local[:3]}***@{domain}"
    return f"{email[:3]}***"

def parse_due_date(text):
    """将页面显示的日期字符串转换为 YYYY-MM-DD 格式"""
    if not text:
        return None
    # 格式: "28 Apr 2026"
    match = re.search(r'(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})', text)
    if match:
        day, month_str, year = match.groups()
        try:
            dt = datetime.strptime(f"{day} {month_str} {year}", "%d %b %Y")
            return dt.strftime("%Y-%m-%d")
        except:
            pass
    # 已经是标准格式
    if re.match(r'\d{4}-\d{2}-\d{2}', text):
        return text
    return None

def get_current_due_date(driver):
    """获取当前管理页面的到期时间，返回原始字符串和标准化日期"""
    selectors = [
        "//h6[contains(text(),'Due date')]/following-sibling::div",
        "//*[contains(text(),'Due date')]/following-sibling::*",
        "//*[contains(text(),'Due Date')]/following-sibling::*",
        "//*[contains(text(),'到期')]/following-sibling::*",
    ]
    for sel in selectors:
        try:
            due_elem = driver.find_element("xpath", sel)
            raw = due_elem.text.strip()
            std = parse_due_date(raw)
            if std:
                return raw, std
        except:
            continue
    return "N/A", None

def detect_connection_error(driver):
    """检测页面是否是 Chrome 连接错误页"""
    try:
        body_text = driver.execute_script("return document.body?.innerText || ''")
        error_indicators = [
            "ERR_CONNECTION_RESET", "ERR_TIMED_OUT", "ERR_NAME_NOT_RESOLVED",
            "ERR_CONNECTION_REFUSED", "ERR_CONNECTION_CLOSED",
            "ERR_PROXY_CONNECTION_FAILED", "ERR_SOCKS_CONNECTION_FAILED",
            "ERR_TUNNEL_CONNECTION_FAILED",
            "This site can\u2019t be reached", "This site can't be reached",
            "Unable to connect", "No internet", "Webpage not available",
        ]
        for indicator in error_indicators:
            if indicator in body_text:
                for line in body_text.split('\n'):
                    line = line.strip()
                    if any(err in line for err in error_indicators):
                        return line
        return None
    except:
        return None

def wait_for_page_loaded(driver, timeout=30):
    """等待页面真正加载完成（非 Chrome 错误页）"""
    start = time.time()
    check_count = 0
    while time.time() - start < timeout:
        check_count += 1
        try:
            # 如果 URL 还是 about:blank，导航根本没发生
            if driver.current_url in ("about:blank", "data:,"):
                if check_count > 5:
                    return False, "页面未加载（URL 仍为 about:blank）"
                time.sleep(1)
                continue

            conn_error = detect_connection_error(driver)
            if conn_error:
                if check_count <= 3:
                    time.sleep(2)
                    continue
                else:
                    return False, conn_error

            body_text = driver.execute_script("return document.body?.innerText || ''")
            source = driver.page_source

            if any(kw in body_text for kw in ["Free Server", "Your Services", "Dashboard"]):
                return True, None
            if "table-column-body-" in source:
                return True, None
            if driver.is_element_visible("input#username") or "/auth/login" in driver.current_url:
                return True, None
            if any(kw in body_text for kw in ["Cloudflare", "Checking your browser", "Just a moment"]):
                if check_count % 3 == 0:
                    print(f"[DEBUG] 第{check_count}次检查 - Cloudflare 验证页，继续等待...")
            elif check_count % 3 == 0:
                print(f"[DEBUG] 第{check_count}次检查 - 等待中...")
        except Exception as e:
            print(f"[WARN] 第{check_count}次检查异常: {e}")
        time.sleep(1)

    conn_error = detect_connection_error(driver)
    if conn_error:
        return False, conn_error
    return False, "页面加载超时"

def navigate_and_wait(driver, url, timeout=30):
    """导航到指定 URL 并等待页面加载完成"""
    print(f"[INFO] 🌐 导航到: {url}")
    try:
        driver.get(url)
    except Exception as e:
        print(f"[WARN] 导航异常: {e}")
        time.sleep(2)
        # 检查是否导航到了任何页面
        try:
            if driver.current_url in ("about:blank", "data:,"):
                conn_error = detect_connection_error(driver)
                if conn_error:
                    return False, f"导航失败: {conn_error}"
                return False, f"导航失败: Chrome 异常（{str(e)[:80]}）"
        except:
            pass
        conn_error = detect_connection_error(driver)
        if conn_error:
            return False, f"导航失败: {conn_error}"

    loaded, error = wait_for_page_loaded(driver, timeout=timeout)
    if loaded:
        return True, None

    # 刷新重试
    print(f"[WARN] 页面加载失败 ({error})，刷新重试...")
    try:
        driver.refresh()
    except:
        try:
            driver.get(url)
        except Exception as e:
            return False, f"刷新也失败: {e}"

    time.sleep(3)
    loaded2, error2 = wait_for_page_loaded(driver, timeout=timeout)
    if loaded2:
        print("[INFO] ✅ 刷新后页面加载成功")
        return True, None
    return False, f"页面加载失败: {error2}"

def kill_chrome_processes():
    """杀掉所有 Chrome/ChromeDriver 残留进程"""
    try:
        subprocess.run(['pkill', '-9', '-f', 'chromium'], capture_output=True, timeout=10)
    except Exception:
        pass
    try:
        subprocess.run(['pkill', '-9', '-f', 'chrome'], capture_output=True, timeout=10)
    except Exception:
        pass
    try:
        subprocess.run(['pkill', '-9', '-f', 'chromedriver'], capture_output=True, timeout=10)
    except Exception:
        pass
    try:
        subprocess.run(['pkill', '-9', '-f', 'Xvfb'], capture_output=True, timeout=10)
    except Exception:
        pass
    time.sleep(2)

def create_driver():
    """创建并返回浏览器驱动"""
    driver_kwargs = {
        "headless": True,
        "headless2": True,
        "uc": True,
        "user_data_dir": USER_DATA_DIR,
        "window_size": "1280,753",
        "disable_csp": True,
        "agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    }
    if PROXY_SERVER:
        driver_kwargs["proxy"] = PROXY_SERVER

    driver = Driver(**driver_kwargs)
    driver.set_page_load_timeout(60)
    driver.set_script_timeout(60)

    try:
        driver.get("about:blank")
    except Exception:
        pass

    time.sleep(2)
    return driver

# ====================== 主逻辑 ======================
def main():
    print("[INFO] " + "=" * 50)
    print("[INFO] HidenCloud 自动续期脚本 (SeleniumBase)")
    print("[INFO] " + "=" * 50)
    print(f"[INFO] 📂 状态目录: {USER_DATA_DIR}")
    print(f"[INFO] 📸 截图目录: {SCREENSHOT_DIR}")
    if PROXY_SERVER:
        print("[INFO] 🌐 使用代理: 已配置")

    MAX_NAV_RETRIES = 5

    # ---------- 启动浏览器 ----------
    print("[INFO] 🚀 启动浏览器...")
    driver = create_driver()

    final_screenshot = None
    result_status = "❌ 续订失败"
    due_date_before_raw = "N/A"
    due_date_before_std = None
    due_date_after_raw = "N/A"
    due_date_after_std = None
    sid = None

    try:
        # ---------- 1. 访问主页（带重试） ----------
        nav_ok = False
        nav_error = None
        for attempt in range(1, MAX_NAV_RETRIES + 1):
            print(f"[INFO] 🌐 访问主页 (第{attempt}/{MAX_NAV_RETRIES}次): {BASE_URL}/dashboard")
            nav_ok, nav_error = navigate_and_wait(driver, f"{BASE_URL}/dashboard", timeout=20)
            take_screenshot(driver, f"01-initial-attempt{attempt}")

            if nav_ok:
                break

            print(f"[WARN] 第{attempt}次访问失败: {nav_error}")

            if attempt < MAX_NAV_RETRIES:
                print(f"[INFO] 🔄 杀掉残留进程后重启浏览器...")
                try:
                    driver.quit()
                except Exception:
                    pass
                kill_chrome_processes()
                time.sleep(3)
                driver = create_driver()

        if not nav_ok:
            print(f"[ERROR] ❌ 无法访问 HidenCloud（已重试{MAX_NAV_RETRIES}次）: {nav_error}")
            take_screenshot(driver, "ERROR-connection-failed")
            try:
                print(f"[DEBUG] 当前URL: {driver.current_url}")
                body_text = driver.execute_script("return document.body?.innerText || ''")
                if body_text.strip():
                    print(f"[DEBUG] 页面内容前500字:\n{body_text[:500]}")
                else:
                    print("[DEBUG] 页面内容为空")
            except:
                pass
            raise Exception(f"无法访问 HidenCloud（{nav_error}），已重试{MAX_NAV_RETRIES}次")

        print("[INFO] ✅ 主页加载成功")

        # ---------- 2. 登录判断 ----------
        if "/auth/login" in driver.current_url or driver.is_element_visible("input#username"):
            print("[INFO] 🔒 检测到未登录，开始登录流程")
            take_screenshot(driver, "02-login-page")

            masked_email = mask_email(HIDEN_EMAIL)
            print(f"[INFO] ✍️ 填写邮箱: {masked_email}")
            driver.type("input#username", HIDEN_EMAIL)
            driver.type("input#password", HIDEN_PWD)
            take_screenshot(driver, "03-credentials-filled")

            print("[INFO] ⏳ 等待 Turnstile 加载...")
            time.sleep(5)

            if driver.is_element_present(".cf-turnstile"):
                print("[INFO] 🖱️ 尝试点击 Turnstile...")
                try:
                    driver.uc_gui_click_cf(".cf-turnstile")
                except:
                    driver.click(".cf-turnstile")
                take_screenshot(driver, "04-turnstile-clicked")

                if not wait_for_turnstile_token(driver, timeout=90):
                    take_screenshot(driver, "ERROR-turnstile-timeout")
                    raise Exception("Turnstile 验证超时")
                take_screenshot(driver, "05-token-ready")
            else:
                print("[WARN] 未找到 Turnstile 元素，继续提交...")

            print("[INFO] 🚀 提交登录表单")
            driver.click("button[type='submit']")
            take_screenshot(driver, "06-login-submitted")

            print("[INFO] ⏳ 等待登录跳转...")
            if not wait_for_url_contains(driver, "/dashboard", timeout=45):
                error_text = check_login_error(driver)
                if error_text:
                    print(f"[ERROR] 登录失败: {error_text}")
                    take_screenshot(driver, "ERROR-login-failed-message")
                    raise Exception(f"登录失败: {error_text}")
                else:
                    time.sleep(5)
                    if "/dashboard" not in driver.current_url:
                        take_screenshot(driver, "ERROR-login-stuck")
                        raise Exception("登录后卡住，未跳转")

            print("[INFO] ✅ 登录成功")
            take_screenshot(driver, "07-login-success")
        else:
            print("[INFO] ✅ 已登录，跳过登录流程")
            take_screenshot(driver, "02-already-logged-in")

        # ---------- 3. 提取服务器 ID ----------
        print("[INFO] 🔍 提取服务器 ID...")
        take_screenshot(driver, "08-dashboard")

        conn_err = detect_connection_error(driver)
        if conn_err:
            print(f"[ERROR] ❌ Dashboard 页面连接错误: {conn_err}")
            take_screenshot(driver, "ERROR-dashboard-connection")
            raise Exception(f"Dashboard 连接错误: {conn_err}，请检查代理配置")

        print("[INFO] ⏳ 等待服务列表渲染...")
        max_wait = 15
        start = time.time()
        loaded = False
        check_count = 0
        while time.time() - start < max_wait:
            check_count += 1
            try:
                body_text = driver.execute_script("return document.body?.innerText || ''")
                source = driver.page_source

                conn_err = detect_connection_error(driver)
                if conn_err:
                    print(f"[ERROR] 等待期间检测到连接错误: {conn_err}")
                    loaded = False
                    break

                if "Free Server" in body_text or "Your Services" in body_text or "table-column-body-" in source:
                    loaded = True
                    print("[INFO] ✅ 服务列表已渲染")
                    break
                if "Cloudflare" in body_text or "Checking your browser" in body_text or "Just a moment" in body_text:
                    if check_count % 3 == 0:
                        print(f"[DEBUG] 第{check_count}次检查 - Cloudflare 验证页，继续等待...")
                elif check_count % 3 == 0:
                    print(f"[DEBUG] 第{check_count}次检查 - 等待中...")

                if driver.is_element_visible("input#username") or "/auth/login" in driver.current_url:
                    print("[WARN] 检测到登录页，登录态可能已失效")
                    break
            except Exception as e:
                print(f"[WARN] 第{check_count}次检查异常: {e}")
            time.sleep(1)

        if not loaded:
            print("[WARN] 服务列表未渲染，尝试刷新页面...")
            driver.get(f"{BASE_URL}/dashboard")
            time.sleep(5)
            take_screenshot(driver, "08-dashboard-refresh")

            conn_err = detect_connection_error(driver)
            if conn_err:
                print(f"[ERROR] ❌ 刷新后连接错误: {conn_err}")
                raise Exception(f"刷新后连接错误: {conn_err}，请检查代理配置")

            start2 = time.time()
            check_count2 = 0
            while time.time() - start2 < 10:
                check_count2 += 1
                try:
                    body_text = driver.execute_script("return document.body?.innerText || ''")
                    if "Free Server" in body_text or "Your Services" in body_text:
                        loaded = True
                        print("[INFO] ✅ 刷新后服务列表已渲染")
                        break
                except Exception as e:
                    print(f"[WARN] 刷新后检查异常: {e}")
                time.sleep(1)

        sid = None

        # 策略1：从表格行的 id 属性提取
        if not sid:
            try:
                row = driver.find_element("xpath", "//tr[contains(@id,'table-column-body-')]")
                row_id = row.get_attribute("id") or ""
                match = re.search(r'table-column-body-(\d+)', row_id)
                if match:
                    sid = match.group(1)
                    print(f"[INFO] ✅ 策略1从行ID提取到服务器 ID: {sid}")
            except Exception as e:
                print(f"[WARN] 策略1失败: {e}")

        # 策略2：用 . 代替 text() 匹配 span 内所有文本
        if not sid:
            try:
                elem = driver.find_element("xpath", "//span[contains(.,'Free Server #')]")
                text = elem.text.strip()
                match = re.search(r'Free Server #(\d+)', text)
                if match:
                    sid = match.group(1)
                    print(f"[INFO] ✅ 策略2从文本提取到服务器 ID: {sid}")
            except Exception as e:
                print(f"[WARN] 策略2失败: {e}")

        # 策略3：从页面链接 href 提取
        if not sid:
            try:
                links = driver.find_elements("xpath", "//a[contains(@href,'/service/')]")
                for link in links:
                    href = link.get_attribute("href") or ""
                    match = re.search(r'/service/(\d+)/manage', href)
                    if match:
                        sid = match.group(1)
                        print(f"[INFO] ✅ 策略3从链接提取到服务器 ID: {sid}")
                        break
            except Exception as e:
                print(f"[WARN] 策略3失败: {e}")

        # 策略4：从整个页面 body 文本正则兜底
        if not sid:
            try:
                body_text = driver.execute_script("return document.body?.innerText || ''")
                match = re.search(r'Free Server #(\d+)', body_text)
                if match:
                    sid = match.group(1)
                    print(f"[INFO] ✅ 策略4从页面文本提取到服务器 ID: {sid}")
            except Exception as e:
                print(f"[WARN] 策略4失败: {e}")

        if not sid:
            try:
                print(f"[DEBUG] 当前URL: {driver.current_url}")
                print(f"[DEBUG] 页面共 {len(driver.find_elements('xpath', '//a[@href]'))} 个链接")
                all_links = driver.find_elements("xpath", "//a[@href]")
                for link in all_links:
                    href = link.get_attribute("href") or ""
                    if "/service/" in href:
                        text = (link.text or "").strip()
                        print(f"[DEBUG] 服务链接: href={href}, text={text}")
                full_source = driver.page_source
                print(f"[DEBUG] 页面源码前6000字符:\n{full_source[:6000]}")
                print(f"[DEBUG] 页面源码总长度: {len(full_source)}")
            except Exception as e:
                print(f"[DEBUG] 打印调试信息失败: {e}")
            take_screenshot(driver, "ERROR-no-server-id")
            raise Exception("无法提取服务器 ID")

        manage_url = f"{BASE_URL}/service/{sid}/manage"
        print(f"[INFO] 🚀 访问管理页面: {BASE_URL}/service/***/manage")

        driver.get(manage_url)
        time.sleep(3)
        conn_err = detect_connection_error(driver)
        if conn_err:
            print(f"[ERROR] ❌ 管理页面连接错误: {conn_err}")
            take_screenshot(driver, "ERROR-manage-connection")
            raise Exception(f"管理页面连接错误: {conn_err}")
        take_screenshot(driver, "09-manage-page")

        # ---------- 4. 获取续订前到期时间 ----------
        due_date_before_raw, due_date_before_std = get_current_due_date(driver)
        print(f"[INFO] 续订前到期时间: {due_date_before_raw}")

        # ---------- 5. 续期操作 ----------
        renew_executed = False
        restricted = False
        days_left = None
        threshold = None

        try:
            print("[INFO] 🔄 查找并点击 Renew 按钮...")

            renew_btn = None
            selectors = [
                ("css selector", "button[onclick*='showRenewAlert']"),
                ("xpath", "//button[.//i[contains(@class, 'bx-recycle')]]"),
                ("xpath", "//button[contains(text(),'Renew')]"),
            ]
            for by, value in selectors:
                try:
                    renew_btn = driver.find_element(by, value)
                    if renew_btn.is_displayed():
                        break
                except:
                    continue

            if not renew_btn:
                take_screenshot(driver, "ERROR-renew-button-not-found")
                raise Exception("页面上未找到 Renew 按钮")

            onclick_val = renew_btn.get_attribute("onclick") or ""
            print(f"[INFO] Renew 按钮 onclick: {onclick_val}")

            param_match = re.search(
                r'showRenewAlert\((\d+),\s*(\d+),\s*(true|false)\)', onclick_val
            )
            if param_match:
                days_left = int(param_match.group(1))
                threshold = int(param_match.group(2))
                is_free = param_match.group(3) == "true"
                print(f"[INFO] 到期剩余: {days_left} 天, 续期阈值: ≤{threshold} 天, 免费服务: {is_free}")

            renew_btn.click()
            renew_executed = True
            print("[INFO] ✅ Renew 按钮已点击")
            time.sleep(3)
            take_screenshot(driver, "10-renew-clicked")

            time.sleep(1)

            restriction_h3 = driver.execute_script(
                "var el = document.querySelector('.fixed.inset-0 h3');"
                "return el ? el.textContent.trim() : '';"
            )
            if 'Renewal Restricted' in restriction_h3:
                restricted = True
                alert_text = driver.execute_script(
                    "var el = document.querySelector('.fixed.inset-0 p');"
                    "return el ? el.textContent.trim() : '';"
                )
                print(f"[INFO] ⚠️ 触发限制弹窗: {alert_text}")
                take_screenshot(driver, "11-renewal-restricted-popup")

                try:
                    ok_btn = driver.find_element("xpath", "//button[contains(text(),'OK')]")
                    ok_btn.click()
                    time.sleep(1)
                    print("[INFO] 已关闭限制弹窗")
                except:
                    pass
            else:
                print("[INFO] 📦 等待续期模态框...")
                modal_selector = f"div#renewService-{sid}"
                driver.wait_for_element_visible(modal_selector, timeout=10)
                take_screenshot(driver, "11-renew-modal-opened")

                print("[INFO] 📦 点击 Create Invoice...")
                submit_btn = driver.find_element(by="css selector", value=f"{modal_selector} button[type='submit']")
                submit_btn.click()
                time.sleep(3)
                take_screenshot(driver, "12-invoice-created")

                print("[INFO] 💳 等待支付页面...")
                time.sleep(5)
                take_screenshot(driver, "13-invoice-page")

                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
                take_screenshot(driver, "14-scrolled-to-bottom")

                print("[INFO] ✅ Pay 按钮已点击")
                pay_clicked = driver.execute_script("""
                    var btn = document.querySelector('button[type="submit"]');
                    if(btn && btn.innerText.includes('Pay')) {
                        btn.click();
                        return true;
                    }
                    return false;
                """)

                if pay_clicked:
                    print("[INFO] ⏳ 等待支付完成...")
                    time.sleep(5)
                    take_screenshot(driver, "15-pay-clicked")
                else:
                    print("[WARN] 未找到 Pay 按钮，可能免费服务自动完成")
                    take_screenshot(driver, "15-no-pay-button")

        except Exception as e:
            print(f"[ERROR] ❌ 续期过程出错: {e}")
            take_screenshot(driver, "ERROR-renew-process")
            raise e

        # ---------- 6. 获取续订后到期时间 ----------
        driver.get(manage_url)
        time.sleep(3)
        due_date_after_raw, due_date_after_std = get_current_due_date(driver)
        print(f"[INFO] 续订后到期时间: {due_date_after_raw}")
        final_screenshot = take_screenshot(driver, "16-final-due-date")

        if due_date_after_std:
            print(f"到期时间(标准): {due_date_after_std}")
        else:
            # raw 可能是 "28 Apr 2026" 等格式，尝试再解析一次
            fallback = parse_due_date(due_date_after_raw)
            if fallback:
                due_date_after_std = fallback
                print(f"到期时间(标准): {fallback}")
            else:
                # 续期被限制时，关弹窗后可能拿不到到期时间，用续订前的值兜底
                if due_date_before_std:
                    due_date_after_std = due_date_before_std
                    print(f"到期时间(标准): {due_date_before_std} (使用续订前值)")
                else:
                    print(f"[WARN] 到期时间解析失败，原始值: {due_date_after_raw}")

        # 专用行供 YAML grep 提取
        if due_date_after_std:
            print(f"[CRON_DUE] {due_date_after_std}")

        # ---------- 7. 判断结果状态 ----------
        if restricted and not renew_executed:
            result_status = "ℹ️ 暂无可续期"
        elif restricted and renew_executed:
            result_status = "ℹ️ 暂无可续期"
        elif due_date_before_std and due_date_after_std:
            if due_date_after_std > due_date_before_std:
                result_status = "✅ 续订成功"
            else:
                result_status = "❌ 续订失败"
        elif renew_executed and not restricted:
            result_status = "⚠️ 续期已执行，请确认"
        else:
            result_status = "❌ 续订失败"

        # ---------- 8. 发送 TG 通知 ----------
        bj_time = get_bj_time()
        change_info = ""
        if due_date_before_raw != "N/A" and due_date_after_raw != "N/A":
            if due_date_before_raw == due_date_after_raw:
                change_info = due_date_after_raw
            else:
                change_info = f"{due_date_before_raw} → {due_date_after_raw}"
        else:
            change_info = due_date_after_raw

        extra_info = ""
        if restricted and days_left is not None and threshold is not None:
            extra_info = f"\n剩余: {days_left} 天 (需 ≤{threshold} 天可续)"

        tg_caption = (
            f"{result_status}\n\n"
            f"账号: `{HIDEN_EMAIL}`\n"
            f"服务器: `Free Server #{sid}`\n"
            f"到期: {change_info}{extra_info}\n"
            f"时间: {bj_time}\n\n"
            f"HidenCloud Auto Renew"
        )
        send_tg_notification(tg_caption, photo_path=final_screenshot)

        print(f"[INFO] 🎉 任务完成 — {result_status}")

    except Exception as e:
        print(f"[ERROR] ❌ 脚本执行失败: {e}")
        take_screenshot(driver, "CRITICAL-ERROR")
        send_tg_notification(f"❌ HidenCloud 续期失败\n错误: {str(e)[:100]}")
        raise
    finally:
        try:
            driver.quit()
        except Exception:
            pass

if __name__ == "__main__":
    main()
