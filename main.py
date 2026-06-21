#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import time
import random
import subprocess
import requests
from datetime import datetime, timezone, timedelta
from seleniumbase import SB

# ================= 配置区 =================
TARGET_URL = "https://magmanode.com/login"
SERVICES_URL = "https://magmanode.com/services"
SERVER_URL_TEMPLATE = "https://magmanode.com/server?id={server_id}"

MAGMANODE_CREDENTIAL = os.environ.get("MAGMANODE", "")
PROXY = os.environ.get("MAGMA_PROXY", "")

TG_TOKEN = os.environ.get("BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")
NETWORK_MODE = os.environ.get("NETWORK_MODE", "").strip()

# ================= 辅助函数 =================
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def tg_time_str():
    beijing_tz = timezone(timedelta(hours=8))
    return datetime.now(beijing_tz).strftime("%Y-%m-%d %H:%M:%S")

def mask_server_url(value):
    if not value:
        return value
    return re.sub(r"(server\?id=)\d+", r"\1***", value)

def extract_server_id(value):
    if not value:
        return "未知"
    match = re.search(r"server\?id=(\d+)", value)
    if match:
        return match.group(1)
    return "未知"

def mask_server_id(server_id):
    if not server_id or server_id == "未知":
        return "未知"
    if len(server_id) <= 3:
        return "***"
    return f"{server_id[:1]}***{server_id[-2:]}"

def build_server_url(server_id):
    return SERVER_URL_TEMPLATE.format(server_id=server_id)

def get_network_mode():
    if NETWORK_MODE:
        mode = NETWORK_MODE
    else:
        mode = "代理" if PROXY else "直连"
    return "直连 ⚠️" if mode == "直连" else mode

def is_login_page_url(url):
    if not url:
        return False
    normalized = url.lower()
    return "/login" in normalized or "sign in" in normalized

def parse_credentials(raw_value):
    if "-----" not in raw_value:
        return "", ""
    account, password = raw_value.split("-----", 1)
    return account.strip(), password.strip()

def send_tg_photo(caption, image_path):
    if not TG_TOKEN or not TG_CHAT_ID or not os.path.exists(image_path):
        return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
        with open(image_path, "rb") as f:
            requests.post(url, data={"chat_id": TG_CHAT_ID, "caption": caption}, files={"photo": f}, timeout=30)
        print("📨 TG 图片推送成功！")
    except Exception as e:
        print(f"⚠️ TG 推送失败: {e}")

def send_tg_text(text):
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TG_CHAT_ID, "text": text}, timeout=30)
        print("📨 TG 文本推送成功！")
    except Exception as e:
        print(f"⚠️ TG 文本推送失败: {e}")

def build_tg_message(server_id="未知", status="未知", result="未知", failure_reason=None):
    lines = [
        "🎮 Magma 保活通知",
        f"⏰通知时间: {tg_time_str()}",
        f"🌐 网络模式：{get_network_mode()}",
        f"🖥 服务器: {server_id}",
        f"📌 状态：{status}",
        f"📊 执行结果: {result}",
    ]
    if failure_reason:
        lines.append(f"❌ 失败原因：{failure_reason}")
    return "\n".join(lines)

def safe_current_url(sb):
    try:
        return sb.get_current_url()
    except Exception:
        return ""

def is_cloudflare_challenge_page(sb):
    try:
        title = (sb.get_title() or "").strip().lower()
        if title == "just a moment...":
            return True
    except Exception:
        pass

    try:
        page_source = sb.get_page_source().lower()
        return "challenges.cloudflare.com" in page_source or "cf-turnstile" in page_source
    except Exception:
        return False

def notify_failure(sb, image_path, status, failure_reason):
    server_id = extract_server_id(safe_current_url(sb))
    send_tg_photo(
        build_tg_message(
            server_id=server_id,
            status=status,
            result="❌ 重启失败",
            failure_reason=failure_reason,
        ),
        image_path,
    )

ADBLOCK_JS = """
(function() {
    try {
        window.open = function() { return null; };
        window.close = function() { return null; };

        document.querySelectorAll('[data-google-vignette], [data-google-interstitial], [class*="google-anno"], [id*="google-anno"]').forEach(function(el) {
            try { el.remove(); } catch (err) {}
        });

        var selectors = [
            'iframe',
            '[data-google-vignette]',
            '[data-google-interstitial]',
            '[class*="google-anno"]',
            '[id*="google-anno"]',
            '[class*="modal"]',
            '[class*="popup"]',
            '[class*="overlay"]',
            '[class*="advert"]',
            '[class*="banner"]',
            '[id*="modal"]',
            '[id*="popup"]',
            '[id*="overlay"]',
            '[id*="advert"]',
            '[id*="banner"]'
        ];

        selectors.forEach(function(selector) {
            document.querySelectorAll(selector).forEach(function(el) {
                try {
                    var style = window.getComputedStyle(el);
                    var zIndex = parseInt(style.zIndex || '0', 10);
                    var isFloating = style.position === 'fixed' || style.position === 'sticky';
                    var isLarge = el.offsetWidth >= window.innerWidth * 0.3 || el.offsetHeight >= window.innerHeight * 0.3;
                    if (el.tagName === 'IFRAME' || isFloating || zIndex >= 999 || isLarge) {
                        el.remove();
                    }
                } catch (err) {}
            });
        });

        document.querySelectorAll('*').forEach(function(el) {
            try {
                var style = window.getComputedStyle(el);
                var zIndex = parseInt(style.zIndex || '0', 10);
                if ((style.position === 'fixed' || style.position === 'sticky') && zIndex >= 9999) {
                    el.remove();
                }
            } catch (err) {}
        });
    } catch (err) {}
})();
"""

def clear_overlays(sb):
    try:
        sb.execute_script(ADBLOCK_JS)
        print("🧹 已执行广告和遮罩清理脚本")
    except Exception as e:
        print(f"⚠️ 清理广告和遮罩失败: {e}")

def capture_step(sb, file_name):
    try:
        sb.save_screenshot(file_name)
        print(f"📸 已保存截图: {file_name}")
    except Exception as e:
        print(f"⚠️ 保存截图失败 {file_name}: {e}")

def strip_google_vignette(url):
    return url.replace("#google_vignette", "")

def recover_from_google_vignette(sb, fallback_url=None, wait_seconds=4):
    try:
        current_url = sb.get_current_url()
    except Exception:
        return False

    if "#google_vignette" not in current_url:
        return False

    target_url = strip_google_vignette(current_url)
    if fallback_url:
        target_url = strip_google_vignette(fallback_url)

    print(f"🚫 检测到 Google vignette 广告页，恢复到: {target_url}")
    try:
        sb.execute_script("window.location.replace(arguments[0]);", target_url)
    except Exception:
        try:
            sb.open(target_url)
        except Exception:
            return False

    sb.sleep(wait_seconds)
    clear_overlays(sb)
    return True

def nudge_page_down(sb):
    try:
        sb.execute_script("window.scrollBy(0, 520);")
        sb.sleep(1)
        sb.execute_script("window.scrollBy(0, 320);")
        sb.sleep(1)
        print("📜 已将页面向下滚动，避开顶部弹窗遮挡")
    except Exception as e:
        print(f"⚠️ 页面滚动失败: {e}")

def restore_expired_service(sb):
    expired_badges = sb.find_elements('span.bg-red-100.text-red-800')
    has_expired = False

    for badge in expired_badges:
        try:
            if "Expired" in badge.text.strip():
                has_expired = True
                break
        except Exception:
            continue

    if not has_expired:
        return False

    print("🔘 检测到 Expired 状态，直接尝试点击 Restore...")
    nudge_page_down(sb)
    clear_overlays(sb)
    sb.sleep(2)

    restore_candidates = []
    try:
        for button in sb.find_elements("button"):
            try:
                button_name = (button.get_attribute("name") or "").strip()
                button_text = (button.text or "").strip()
                button_html = (button.get_attribute("outerHTML") or "")[:500]
                if button_name == "restore_server" or "Restore" in button_text or 'name="restore_server"' in button_html:
                    restore_candidates.append(button)
                    print(f"🧩 找到 Restore 候选按钮: name={button_name}, text={button_text}")
            except Exception:
                continue
    except Exception as e:
        print(f"⚠️ 枚举按钮失败: {e}")

    if not restore_candidates:
        print("⚠️ 未枚举到任何 Restore 候选按钮，打印页面片段排查")
        try:
            page_source = sb.get_page_source()
            marker = 'restore_server'
            index = page_source.find(marker)
            if index != -1:
                start = max(0, index - 400)
                end = min(len(page_source), index + 800)
                print(f"📄 restore_server 附近页面片段: {page_source[start:end]}")
            else:
                print(f"📄 页面片段: {page_source[:1500]}")
        except Exception:
            pass

    for button in restore_candidates:
        try:
            sb.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
            sb.sleep(1)
            try:
                sb.execute_script("arguments[0].click();", button)
                print("✅ 已使用 JS 点击 Restore")
                return True
            except Exception as e:
                print(f"⚠️ JS 点击失败: {e}")

            try:
                button.click()
                print("✅ 已使用元素原生点击 Restore")
                return True
            except Exception as e:
                print(f"⚠️ 元素原生点击失败: {e}")
        except Exception:
            continue

    return False

def service_is_online(sb):
    try:
        online_badges = sb.find_elements('span.bg-green-100.text-green-800')
        for badge in online_badges:
            try:
                if "Online" in (badge.text or "").strip():
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False

def wait_for_manage_ready(sb, timeout=40):
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            recover_from_google_vignette(sb, SERVICES_URL, wait_seconds=2)
            clear_overlays(sb)

            online_badges = sb.find_elements('span.bg-green-100.text-green-800')
            has_online = any("Online" in (badge.text or "").strip() for badge in online_badges)

            manage_targets = []
            for link in sb.find_elements("a"):
                try:
                    href = (link.get_attribute("href") or "").strip()
                    text = (link.text or "").strip()
                    match = re.search(r"server\?id=(\d+)", href)
                    if match and text == "Manage":
                        manage_targets.append({
                            "href": href,
                            "text": text,
                            "server_id": match.group(1),
                        })
                except Exception:
                    continue

            if has_online:
                print("✅ 检测到 Online 状态")
            if manage_targets:
                print(f"✅ 检测到 {len(manage_targets)} 个有效 Manage 候选链接")
                for target in manage_targets:
                    print(f"🧩 Manage 候选: href={mask_server_url(target['href'])}")

            if has_online or manage_targets:
                return manage_targets
        except Exception as e:
            print(f"⚠️ 等待 Manage 就绪时出错: {e}")

        sb.sleep(2)

    return []

def wait_after_restore_progress(sb, timeout=20):
    print("⏳ 检测到 Restore 后进度条阶段，等待页面处理完成...")
    end_time = time.time() + timeout

    while time.time() < end_time:
        try:
            recover_from_google_vignette(sb, SERVICES_URL, wait_seconds=1)
            clear_overlays(sb)

            page_text = ""
            try:
                page_text = (sb.get_text("body") or "").strip()
            except Exception:
                pass

            has_online = service_is_online(sb)
            has_manage = False
            for link in sb.find_elements("a"):
                try:
                    href = (link.get_attribute("href") or "").strip()
                    text = (link.text or "").strip()
                    if re.search(r"server\?id=\d+", href) and text == "Manage":
                        has_manage = True
                        break
                except Exception:
                    continue

            if has_online or has_manage:
                print("✅ Restore 后页面已完成渲染")
                return

            if "Restore" in page_text or "Progress" in page_text or "%" in page_text:
                print("⏳ Restore 进度处理中...")
        except Exception as e:
            print(f"⚠️ 等待 Restore 进度时出错: {e}")

        sb.sleep(2)

    print("⚠️ Restore 进度等待超时，继续尝试检测后续状态")

def click_manage_and_enter_server(sb, manage_targets):
    for target in manage_targets:
        try:
            text = target["text"]
            server_id = target["server_id"]
            target_href = build_server_url(server_id)
            print(f"🎯 准备进入 Manage 目标页: text={text}, server_id={mask_server_id(server_id)}")

            clear_overlays(sb)

            print(f"➡️ 直接导航到 Manage 目标页: {mask_server_url(target_href)}")
            if not open_fixed_url(sb, target_href, wait_seconds=6):
                print(f"⚠️ 直接导航 Manage 目标页失败: {mask_server_url(target_href)}")
                continue
            recover_from_google_vignette(sb, target_href, wait_seconds=3)
            clear_overlays(sb)
            if is_on_server_page(sb, server_id):
                print(f"✅ 已直接进入目标页面: {mask_server_url(safe_current_url(sb))}")
                return True

            print(f"⚠️ 首次导航未确认成功，重试打开 Manage 目标页: {mask_server_url(target_href)}")
            if not open_fixed_url(sb, target_href, wait_seconds=6):
                continue
            recover_from_google_vignette(sb, target_href, wait_seconds=3)
            clear_overlays(sb)
            if is_on_server_page(sb, server_id):
                print(f"✅ 已通过再次打开进入目标页面: {mask_server_url(safe_current_url(sb))}")
                return True
        except Exception as e:
            print(f"⚠️ 处理 Manage 链接时失败: {e}")
            try:
                switch_to_available_window(sb)
                if is_on_server_page(sb, server_id):
                    print(f"✅ Manage 跳转虽然报错，但已进入目标页面: {mask_server_url(safe_current_url(sb))}")
                    return True
            except Exception as check_error:
                print(f"⚠️ Manage 报错后检查当前页面失败: {check_error}")
            continue

    return False

def click_start_button(sb):
    recover_from_google_vignette(sb, wait_seconds=2)
    clear_overlays(sb)
    sb.sleep(2)

    start_sel = "#power-start"
    try:
        sb.wait_for_element_visible(start_sel, timeout=10)
        sb.scroll_to(start_sel)
        sb.sleep(1)
        sb.click(start_sel)
        print("✅ 已使用 Selenium 点击 START")
        return True
    except Exception as e:
        print(f"⚠️ Selenium 点击 START 失败，尝试 JS 鼠标事件: {e}")

    try:
        clicked = sb.execute_script("""
            var button = document.querySelector('#power-start');
            if (!button) {
                return false;
            }
            button.classList.remove('hidden');
            button.style.display = '';
            button.disabled = false;
            button.scrollIntoView({block: 'center'});

            ['mouseover', 'mousedown', 'mouseup', 'click'].forEach(function(type) {
                button.dispatchEvent(new MouseEvent(type, {
                    bubbles: true,
                    cancelable: true,
                    view: window
                }));
            });
            return true;
        """)
        if clicked:
            print("✅ 已使用 JS 鼠标事件点击 START")
            return True
    except Exception as e:
        print(f"⚠️ JS 鼠标事件点击 START 失败: {e}")

    start_targets = []
    try:
        for button in sb.find_elements("button"):
            try:
                action = (button.get_attribute("data-action") or "").strip()
                text = re.sub(r"\s+", " ", (button.text or "").strip()).upper()
                html = (button.get_attribute("outerHTML") or "")[:500]
                if action == "start" and text == "START":
                    start_targets.append({
                        "action": action,
                        "text": text,
                    })
                    print(f"🧩 找到有效 START 候选按钮: action={action}, text={text}")
                elif 'data-action="start"' in html and "START" in text:
                    start_targets.append({
                        "action": action or "start",
                        "text": text,
                    })
                    print(f"🧩 找到有效 START 候选按钮: action={action or 'start'}, text={text}")
            except Exception:
                continue
    except Exception as e:
        print(f"⚠️ 枚举 START 按钮失败: {e}")

    if not start_targets:
        try:
            page_source = sb.get_page_source()
            marker = 'data-action="start"'
            index = page_source.find(marker)
            if index != -1:
                start = max(0, index - 400)
                end = min(len(page_source), index + 800)
                print(f"📄 START 附近页面片段: {page_source[start:end]}")
        except Exception:
            pass

    for _ in start_targets:
        try:
            button = sb.find_element('button[data-action="start"]')
            button_text = re.sub(r"\s+", " ", (button.text or "").strip()).upper()
            if button_text != "START":
                print(f"⚠️ 当前 data-action=start 按钮文本不是 START: {button_text}")
                continue

            sb.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
            sb.sleep(1)
            try:
                sb.execute_script("arguments[0].click();", button)
                print("✅ 已使用 JS 点击 START")
                return True
            except Exception as e:
                print(f"⚠️ JS 点击 START 失败: {e}")

            try:
                button.click()
                print("✅ 已使用元素原生点击 START")
                return True
            except Exception as e:
                print(f"⚠️ 元素原生点击 START 失败: {e}")
        except Exception as e:
            print(f"⚠️ START 候选点击流程异常: {e}")
            continue

    return False

def start_server_via_api(sb, server_id):
    try:
        sb.execute_script("""
            if (typeof window.startServer === 'function') {
                window.startServer();
            } else if (typeof window.sendPowerCommand === 'function') {
                window.sendPowerCommand('start');
            }
        """)
    except Exception as e:
        print(f"⚠️ 发送开机命令失败: {e}")
        return False, "未知"

    print("⏳ 等待开机状态刷新...")
    time.sleep(5)

    status = read_server_status(sb)
    if status:
        print(f"📡 已发送开机命令，响应状态：{status}")
        return True, status

    for _ in range(6):
        time.sleep(5)
        status = read_server_status(sb)
        if status:
            print(f"📡 已发送开机命令，响应状态：{status}")
            return True, status
        try:
            sb.execute_script("""
                if (typeof window.startServer === 'function') {
                    window.startServer();
                } else if (typeof window.sendPowerCommand === 'function') {
                    window.sendPowerCommand('start');
                }
            """)
        except Exception:
            pass

    print("⚠️ 开机命令已发送，但未能获取到状态")
    return True, "未知"

def read_server_status(sb):
    try:
        status_text = sb.execute_script("""
            var el = document.querySelector('[data-server-status]');
            return el ? (el.textContent || '').trim() : '';
        """)
        return (status_text or "").strip()
    except Exception:
        return ""

def wait_for_start_confirmed(sb, timeout=60):
    print("⏳ START 已点击，等待状态刷新...")
    time.sleep(5)

    end_time = time.time() + timeout
    last_status = ""

    while time.time() < end_time:
        recover_from_google_vignette(sb, wait_seconds=1)
        clear_overlays(sb)

        status = read_server_status(sb)
        if status and status != last_status:
            print(f"📌 当前服务器状态: {status}")
            last_status = status

        normalized = status.strip().lower()
        if normalized in {"starting", "running"}:
            print(f"✅ START 已确认成功，状态变为 {status}")
            return True, status

        if normalized == "offline":
            print("⚠️ 当前状态仍是 Offline，继续等待确认...")

        time.sleep(3)

    return False, last_status or "未知"

# 强制暴露隐藏的 CF 盾
EXPAND_POPUP_JS = """
(function() {
    var iframes = document.querySelectorAll('iframe');
    iframes.forEach(function(iframe) {
        if (iframe.src && (iframe.src.includes('challenges.cloudflare.com') || iframe.src.includes('turnstile'))) {
            iframe.style.width = '300px';
            iframe.style.height = '65px';
            iframe.style.minWidth = '300px';
            iframe.style.visibility = 'visible';
            iframe.style.opacity = '1';
        }
    });
})();
"""

# 获取盾的绝对屏幕坐标
def get_turnstile_coords(sb):
    return sb.execute_script("""
        var iframes = document.querySelectorAll('iframe');
        for (var i = 0; i < iframes.length; i++) {
            var src = iframes[i].src || '';
            if (src.includes('cloudflare') || src.includes('turnstile')) {
                var rect = iframes[i].getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    var screenX = window.screenX || 0;
                    var screenY = window.screenY || 0;
                    var outerHeight = window.outerHeight;
                    var innerHeight = window.innerHeight;
                    var chromeBarHeight = outerHeight - innerHeight;
                    
                    var abs_x = Math.round(rect.x + 30) + screenX;
                    var abs_y = Math.round(rect.y + rect.height / 2) + screenY + chromeBarHeight;
                    
                    return {x: abs_x, y: abs_y};
                }
            }
        }
        return null;
    """)

# 使用 Linux 底层工具进行物理点击
def os_hardware_click(x, y):
    try:
        # 激活浏览器窗口
        result = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", "chrome"], capture_output=True, text=True)
        w_ids = result.stdout.strip().split('\n')
        if w_ids and w_ids[0]:
            subprocess.run(["xdotool", "windowactivate", w_ids[0]], stderr=subprocess.DEVNULL)
            time.sleep(0.2)
        
        # 移动并点击
        os.system(f"xdotool mousemove {int(x)} {int(y)} click 1")
        print(f"👆 已使用 xdotool 物理点击屏幕坐标 ({x}, {y})")
        return True
    except Exception as e:
        print(f"⚠️ xdotool 点击失败: {e}")
        return False

def is_fullpage_cloudflare_checkbox(sb):
    try:
        return bool(sb.execute_script("""
            var bodyText = (document.body && document.body.innerText || '').toLowerCase();
            var hasCheckbox = !!document.querySelector('input[type="checkbox"], label.cb-lb, .cb-c');
            var hasCfFrame = !!document.querySelector('iframe[src*="cloudflare"], iframe[src*="turnstile"], iframe[title*="Cloudflare"], iframe[title*="challenge"]');
            var hasCfText = bodyText.includes('verify you are human') ||
                bodyText.includes('请验证您是真人') ||
                bodyText.includes('正在验证') ||
                bodyText.includes('cloudflare');
            return (hasCheckbox && hasCfText) || (hasCfFrame && hasCfText);
        """))
    except Exception:
        return False

def get_fullpage_checkbox_coords(sb):
    return sb.execute_script("""
        function coordsFromRect(rect, offsetX) {
            var screenX = window.screenX || 0;
            var screenY = window.screenY || 0;
            var chromeBarHeight = window.outerHeight - window.innerHeight;
            return {
                x: Math.round(rect.left + offsetX) + screenX,
                y: Math.round(rect.top + rect.height / 2) + screenY + chromeBarHeight
            };
        }

        var target = document.querySelector('input[type="checkbox"], label.cb-lb, .cb-c');
        if (target) {
            var targetRect = target.getBoundingClientRect();
            if (targetRect.width > 0 && targetRect.height > 0) {
                return coordsFromRect(targetRect, Math.min(28, targetRect.width / 2));
            }
        }

        var frames = document.querySelectorAll('iframe[src*="cloudflare"], iframe[src*="turnstile"], iframe[title*="Cloudflare"], iframe[title*="challenge"]');
        for (var i = 0; i < frames.length; i++) {
            var frameRect = frames[i].getBoundingClientRect();
            if (frameRect.width > 0 && frameRect.height > 0) {
                return coordsFromRect(frameRect, Math.min(32, frameRect.width / 6));
            }
        }

        if (!target) {
            return null;
        }
        return null;
    """)

def handle_initial_cloudflare_challenge(sb, user_sel, timeout=150, restart_rounds=1):
    for round_index in range(restart_rounds + 1):
        if round_index > 0:
            print(f"🔄 前置 CF 验证上一轮未通过，重新打开登录页后重试 (第 {round_index + 1} 轮)...")
            try:
                sb.uc_open_with_reconnect(TARGET_URL, reconnect_time=6)
            except Exception as e:
                print(f"⚠️ 重新打开登录页失败，尝试普通打开: {e}")
                try:
                    sb.open(TARGET_URL)
                except Exception as open_error:
                    print(f"⚠️ 普通打开登录页也失败: {open_error}")
                    return False
            time.sleep(6)

        end_time = time.time() + timeout
        attempt = 0

        while time.time() < end_time:
            try:
                if sb.is_element_present(user_sel):
                    print("✅ 登录表单已加载，前置 CF 验证已通过或未出现")
                    return True
            except Exception:
                pass

            if not is_cloudflare_challenge_page(sb) and not is_fullpage_cloudflare_checkbox(sb):
                time.sleep(2)
                continue

            attempt += 1
            print(f"🛡️ 检测到登录页前置 Cloudflare 验证，尝试处理 (第 {attempt} 次，第 {round_index + 1} 轮)...")

            try:
                sb.uc_gui_click_captcha()
                print("⏳ 已触发 SeleniumBase UC 点击，等待验证结果...")
                time.sleep(6)
            except Exception as e:
                print(f"⚠️ UC 点击前置 CF 验证失败: {e}")

            try:
                if sb.is_element_present(user_sel):
                    print("✅ 前置 CF 验证后登录表单已出现")
                    return True
            except Exception:
                pass

            coords = get_fullpage_checkbox_coords(sb)
            if coords:
                click_x = coords['x'] + random.randint(-5, 5)
                click_y = coords['y'] + random.randint(-4, 4)
                os_hardware_click(click_x, click_y)
                print("⏳ 已物理点击前置 CF checkbox，等待页面跳转...")
                time.sleep(8)
            else:
                print("⚠️ 未获取到前置 CF checkbox 坐标，继续等待...")
                time.sleep(3)

    return False

def wait_for_login_page_ready(sb, user_sel, pass_sel, timeout=40):
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            ready_state = sb.execute_script("return document.readyState;")
            user_ready = sb.is_element_visible(user_sel)
            pass_ready = sb.is_element_visible(pass_sel)
            if ready_state == "complete" and user_ready and pass_ready:
                print("✅ 登录页表单已完整渲染")
                time.sleep(3)
                return True
        except Exception:
            pass

        time.sleep(1)

    return False

def switch_to_available_window(sb):
    try:
        handles = sb.driver.window_handles
    except Exception as e:
        print(f"⚠️ 获取浏览器窗口失败: {e}")
        return False

    if not handles:
        print("⚠️ 当前 Selenium 会话没有可用窗口")
        return False

    for handle in reversed(handles):
        try:
            sb.driver.switch_to.window(handle)
            current_url = safe_current_url(sb)
            print(f"✅ 已切换到可用浏览器窗口: {mask_server_url(current_url) or '空白页'}")
            return True
        except Exception:
            continue

    print("⚠️ 未能切换到任何可用浏览器窗口")
    return False

def open_with_window_recovery(sb, url, reconnect_time=5):
    switch_to_available_window(sb)
    try:
        sb.uc_open_with_reconnect(url, reconnect_time=reconnect_time)
        return True
    except Exception as e:
        print(f"⚠️ UC 打开页面失败，尝试恢复窗口后重新打开: {e}")

    if not switch_to_available_window(sb):
        return False

    try:
        sb.open(url)
        return True
    except Exception as e:
        print(f"⚠️ 普通打开页面失败: {e}")
        return False

def open_fixed_url(sb, url, wait_seconds=6):
    try:
        sb.open(url)
        sb.sleep(wait_seconds)
        return True
    except Exception as e:
        print(f"⚠️ 普通导航固定页面失败，尝试 JS 导航: {e}")

    try:
        sb.execute_script("window.location.assign(arguments[0]);", url)
        sb.sleep(wait_seconds)
        return True
    except Exception as e:
        print(f"⚠️ JS 导航固定页面失败: {e}")
        return False

def safe_click_selector(sb, selector, label="元素"):
    try:
        sb.click(selector)
        return True
    except Exception as e:
        print(f"⚠️ 点击 {label} 时 WebDriver 返回异常，检查页面是否已继续: {e}")
        return False

def page_has_manage_or_services(sb):
    try:
        current_url = sb.get_current_url()
        if "services" in current_url or "server?id=" in current_url:
            return True
    except Exception:
        pass

    try:
        return bool(sb.execute_script("""
            return !!document.querySelector('a[href*="server?id="], [data-server-status], button[data-action]');
        """))
    except Exception:
        return False

def is_on_server_page(sb, server_id):
    try:
        current_url = sb.get_current_url()
        if f"server?id={server_id}" in current_url:
            return True
    except Exception:
        pass

    try:
        return bool(sb.execute_script("return !!document.querySelector('[data-server-status], button[data-action]');"))
    except Exception:
        return False

# ================= 主逻辑 =================
def main():
    account, password = parse_credentials(MAGMANODE_CREDENTIAL)
    if not account or not password:
        print("❌ 缺少 MAGMANODE 环境变量，或格式不是 账号-----密码")
        sys.exit(1)

    print("🔧 启动 SeleniumBase UC 模式浏览器...")
    current_step = "启动浏览器"
    opts = {
        "uc": True, 
        "test": True, 
        "headless": False, 
        "locale": "en", 
        "chromium_arg": "--disable-dev-shm-usage,--no-sandbox,--start-maximized,--window-size=1440,1400"
    }
    if PROXY:
        opts["proxy"] = PROXY
        print(f"🛡️ 使用代理: {PROXY}")

    with SB(**opts) as sb:
        # 强制 xvfb 窗口大小
        sb.set_window_rect(0, 0, 1440, 1400)
        
        try:
            current_step = "打开登录页"
            print(f"🌐 访问目标网页: {TARGET_URL}")
            sb.uc_open_with_reconnect(TARGET_URL, reconnect_time=6)
            time.sleep(5)

            try:
                print(f"📄 当前标题: {sb.get_title()}")
                print(f"🔗 当前 URL: {sb.get_current_url()}")
            except Exception:
                pass

            current_url = sb.get_current_url()
            if "services" in current_url or "projects" in current_url:
                print("✅ 似乎已经处于登录状态！")
            else:
                current_step = "填写登录表单"
                print("🛡️ 正在解析登录表单...")
                user_sel = '#username, input[name="username"], input[type="email"], input[name="email"], input[type="text"]'
                pass_sel = '#password, input[name="password"], input[type="password"]'

                current_step = "处理登录页前置 Cloudflare 验证"
                if not handle_initial_cloudflare_challenge(sb, user_sel):
                    shot_path = "initial_cf_challenge_failed.png"
                    capture_step(sb, shot_path)
                    notify_failure(sb, shot_path, "Cloudflare验证", "登录页前置 Cloudflare 整页验证未通过")
                    sys.exit(1)

                current_step = "等待登录页渲染"
                if not wait_for_login_page_ready(sb, user_sel, pass_sel):
                    shot_path = "login_page_not_ready.png"
                    capture_step(sb, shot_path)
                    notify_failure(sb, shot_path, "Login", "登录页未在预期时间内完整渲染")
                    sys.exit(1)

                current_step = "填写登录表单"
                login_form_present = False
                try:
                    login_form_present = sb.is_element_present(user_sel)
                except Exception:
                    pass

                if not login_form_present and is_cloudflare_challenge_page(sb):
                    print("❌ 当前仍停留在 Cloudflare 验证页，未进入登录表单")
                    shot_path = "cloudflare_challenge.png"
                    capture_step(sb, shot_path)
                    notify_failure(sb, shot_path, "Cloudflare验证", "页面停留在 Just a moment，未加载登录表单")
                    sys.exit(1)

                try:
                    sb.wait_for_element(user_sel, timeout=30)
                except Exception:
                    try:
                        page_source = sb.get_page_source()
                        print(f"📄 页面片段: {page_source[:1200]}")
                    except Exception:
                        pass
                    if is_cloudflare_challenge_page(sb):
                        shot_path = "cloudflare_challenge.png"
                        capture_step(sb, shot_path)
                        notify_failure(sb, shot_path, "Cloudflare验证", "等待登录表单超时，页面仍是 Cloudflare 验证页")
                        sys.exit(1)
                    raise
                
            for login_attempt in range(1, 3):
                if login_attempt > 1:
                    print(f"🔄 第 {login_attempt} 次重试登录...")
                    sb.uc_open_with_reconnect(TARGET_URL, reconnect_time=6)
                    time.sleep(5)
                    sb.uc_gui_click_captcha()
                    time.sleep(6)
                    if is_cloudflare_challenge_page(sb):
                        print("⏳ CF 验证中，等待完成...")
                        time.sleep(10)

                print("✏️ 填写账号密码...")
                sb.type(user_sel, account)
                sb.type(pass_sel, password)
                
                print("🛡️ 开始处理 Cloudflare 验证框...")
                time.sleep(3)

                # 将 CF 盾强制滚动到页面中央，确保 xdotool 能点到物理屏幕内
                cf_iframe_sel = "iframe[src*='cloudflare'], iframe[src*='turnstile']"
                if sb.is_element_present(cf_iframe_sel):
                    sb.scroll_to(cf_iframe_sel)
                    time.sleep(1)
                    # 随便点一下页面空白处，激活窗口焦点
                    sb.click('body', timeout=2) 
                    time.sleep(1)

                sb.execute_script(EXPAND_POPUP_JS)
                time.sleep(1)

                # 尝试突破 CF 盾
                cf_passed = False
                for attempt in range(5):
                    # 校验 1：判断底层 token 是否已生成
                    is_done = sb.execute_script("var cf = document.querySelector(\"input[name='cf-turnstile-response']\"); return cf && cf.value.length > 20;")
                    if is_done:
                        print("✅ CF 盾底层验证已通过！")
                        cf_passed = True
                        break
                    
                    print(f"🖱️ 尝试验证 (第 {attempt + 1} 次)...")
                    try:
                        # 方案 A：使用 SeleniumBase 原生专杀工具
                        sb.uc_gui_click_captcha()
                        print("⏳ 触发原生点击过盾，等待反应 (4秒)...")
                        time.sleep(4)
                    except Exception as e:
                        print(f"⚠️ 原生点击抛出异常: {e}")

                    # 校验 2：原生方法点完后，再次检查是否通过
                    if sb.execute_script("var cf = document.querySelector(\"input[name='cf-turnstile-response']\"); return cf && cf.value.length > 20;"):
                        print("✅ 原生方法点击成功！")
                        cf_passed = True
                        break

                    # 方案 B：使用获取坐标的底层硬件点击
                    print("⚠️ 原生未通过，尝试 xdotool 物理点击...")
                    coords = get_turnstile_coords(sb)
                    if coords:
                        # 加入随机偏移，防止被识别为机械点击，并兼容微小的坐标误差
                        click_x = coords['x'] + random.randint(-8, 8)
                        click_y = coords['y'] + random.randint(-4, 4)
                        
                        os_hardware_click(click_x, click_y)
                        print("⏳ 等待物理点击后的验证动画 (5秒)...")
                        time.sleep(5)
                    else:
                        print("⚠️ 仍未找到盾的位置坐标，等待重试...")
                        time.sleep(3)

                # 强校验拦截：如果 5 次都没过盾，拦截提交
                if not cf_passed:
                    print("❌ 警告：5 次尝试后 CF 盾仍未通过，登录极大概率会被拦截！")
                    capture_step(sb, "cf_failed_state.png")
                    notify_failure(sb, "cf_failed_state.png", "CF验证失败", "CF 过盾失败，停止提交登录")
                    sys.exit(1) # 过盾失败，直接退出脚本，避免滥发无效请求
                else:
                    current_step = "提交登录"
                    print("📤 盾已通过，提交登录...")
                    safe_click_selector(sb, '#submit-btn, button[type="submit"], button:contains("Sign in"), button:contains("Login")', "登录按钮")
                
                print("⏳ 等待页面跳转...")
                time.sleep(10)
                switch_to_available_window(sb)

                current_step = "进入服务页面"
                print(f"🌐 打开服务页面: {SERVICES_URL}")
                if not open_with_window_recovery(sb, SERVICES_URL, reconnect_time=5):
                    shot_path = "browser_window_closed.png"
                    capture_step(sb, shot_path)
                    notify_failure(sb, shot_path, "浏览器窗口", "登录提交后浏览器窗口已关闭，无法打开 services 页面")
                    return
                sb.sleep(8)
                recover_from_google_vignette(sb, SERVICES_URL, wait_seconds=3)
                try:
                    current_url = sb.get_current_url()
                except Exception as e:
                    print(f"⚠️ 读取服务页 URL 超时或失败，尝试按页面内容继续: {e}")
                    if page_has_manage_or_services(sb):
                        current_url = SERVICES_URL
                    else:
                        raise
                print(f"🔗 服务页当前 URL: {current_url}")
                try:
                    print(f"📄 服务页标题: {sb.get_title()}")
                except Exception:
                    pass

                if is_login_page_url(current_url):
                    if login_attempt < 2:
                        print("⚠️ 登录未成功，准备重试...")
                        continue
                    shot_path = "login_not_completed.png"
                    capture_step(sb, shot_path)
                    notify_failure(sb, shot_path, "Login", "登录未成功，访问 services 时被重定向回登录页")
                    return

                break  # 登录成功，退出重试循环

            capture_step(sb, "services_page.png")

            if service_is_online(sb):
                print("✅ 服务已是 Online，跳过 Restore")
                capture_step(sb, "service_online.png")
            else:
                current_step = "点击 Restore"
                restored = restore_expired_service(sb)
                if not restored:
                    print("ℹ️ 检测到 Expired 后，仍未成功点击 Restore 按钮。")
                    shot_path = "restore_debug.png"
                    capture_step(sb, shot_path)
                    notify_failure(sb, shot_path, "Expired", "检测到 Expired，但未成功点击 Restore")
                    return

                capture_step(sb, "restore_clicked.png")
                wait_after_restore_progress(sb, timeout=20)
                print("⏳ 等待 Restore 后页面重新渲染，检测 Online / Manage...")

            current_step = "等待 Manage 就绪"
            manage_links = wait_for_manage_ready(sb)
            if not manage_links:
                shot_path = "manage_wait_debug.png"
                capture_step(sb, shot_path)
                notify_failure(sb, shot_path, "Restoring", "Restore 后未检测到 Online 或 Manage")
                return

            capture_step(sb, "manage_ready.png")
            current_step = "进入 Manage 页面"
            entered_server = click_manage_and_enter_server(sb, manage_links)
            if not entered_server:
                shot_path = "manage_click_debug.png"
                capture_step(sb, shot_path)
                notify_failure(sb, shot_path, "Online", "已检测到 Manage，但未成功进入目标 server 页面")
                return

            sb.sleep(5)
            recover_from_google_vignette(sb, wait_seconds=3)
            clear_overlays(sb)
            capture_step(sb, "server_page.png")

            current_status = read_server_status(sb)
            if current_status:
                print(f"📌 Manage 页面当前服务器状态: {current_status}")
            if current_status.strip().lower() == "running":
                current_url = sb.get_current_url()
                server_id = extract_server_id(current_url)
                send_tg_text(
                    build_tg_message(
                        server_id=server_id,
                        status=current_status,
                        result="✅ 已在运行，无需开机",
                    )
                )
                return
            if current_status.strip().lower() == "queued":
                current_url = sb.get_current_url()
                server_id = extract_server_id(current_url)
                send_tg_text(
                    build_tg_message(
                        server_id=server_id,
                        status=current_status,
                        result="❌ 开机失败",
                        failure_reason="排队中",
                    )
                )
                return

            current_url = sb.get_current_url()
            server_id = extract_server_id(current_url)
            current_step = "API START"
            api_ok, api_status = start_server_via_api(sb, server_id)
            if not api_ok:
                shot_path = "api_start_failed.png"
                capture_step(sb, shot_path)
                notify_failure(sb, shot_path, "API", "API 开机请求失败")
                return

            normalized_api_status = api_status.strip().lower()
            if normalized_api_status in {"starting", "running"}:
                start_confirmed, final_status = True, api_status
            elif normalized_api_status == "queued":
                start_confirmed, final_status = False, api_status
            else:
                start_confirmed, final_status = wait_for_start_confirmed(sb, timeout=60)
            if start_confirmed:
                shot_path = "start_success.png"
                capture_step(sb, shot_path)
                send_tg_text(
                    build_tg_message(
                        server_id=server_id,
                        status=final_status,
                        result="✅ 开机成功",
                    )
                )
            else:
                if final_status.strip().lower() == "queued":
                    send_tg_text(
                        build_tg_message(
                            server_id=server_id,
                            status=final_status,
                            result="❌ 开机失败",
                            failure_reason="排队中",
                        )
                    )
                    return
                shot_path = "warn_start_not_confirmed.png"
                capture_step(sb, shot_path)
                notify_failure(sb, shot_path, final_status, "已发送 API START，但未检测到 Starting 或 Running 状态")
                return

        except Exception as e:
            print(f"❌ 运行报错: {e}")
            capture_step(sb, "error.png")
            notify_failure(sb, "error.png", current_step, f"脚本运行异常: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()
