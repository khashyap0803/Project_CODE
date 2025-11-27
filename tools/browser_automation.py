"""
Browser Automation Tool using Selenium
Enables JARVIS to control browser: search Google, play YouTube videos, navigate sites
Uses Firefox with user's native profile for authentic browsing experience
"""
import asyncio
import time
import subprocess
import os
import shutil
from typing import Dict, Any, Optional
from core.logger import setup_logger

logger = setup_logger(__name__)


class BrowserTool:
    """
    Browser automation using Selenium with Firefox native profile
    Handles: YouTube autoplay, ad skipping, media controls, Google search, navigation
    """
    
    def __init__(self):
        self.driver = None
        self.is_headless = False
        self._last_video_url = None
        self._browser_type = None
        self._ad_skip_task = None
        logger.info("BrowserTool initialized")
    
    def _check_session_valid(self) -> bool:
        """Check if current browser session is still valid"""
        if self.driver is None:
            return False
        try:
            _ = self.driver.current_url
            return True
        except Exception as e:
            logger.warning(f"Browser session invalid: {e}")
            self.driver = None
            self._browser_type = None
            return False
    
    def _get_driver(self, force_new: bool = False):
        """Get or create Selenium WebDriver using Firefox with native profile"""
        if not force_new and self._check_session_valid():
            logger.debug("Reusing existing browser session")
            return self.driver
        
        if self.driver is not None:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
            self._browser_type = None
        
        try:
            from selenium import webdriver
            from selenium.webdriver.firefox.options import Options as FirefoxOptions
            from selenium.webdriver.firefox.service import Service as FirefoxService
            from selenium.webdriver.chrome.options import Options as ChromeOptions
            
            # Try Firefox FIRST (better for avoiding bot detection with native profile)
            try:
                firefox_options = FirefoxOptions()
                
                # Use existing Firefox profile to avoid bot detection
                # Firefox profiles are in ~/.mozilla/firefox/
                firefox_profile_path = os.path.expanduser("~/.mozilla/firefox")
                if os.path.exists(firefox_profile_path):
                    # Find the default profile
                    profiles_ini = os.path.join(firefox_profile_path, "profiles.ini")
                    default_profile = None
                    if os.path.exists(profiles_ini):
                        with open(profiles_ini, 'r') as f:
                            content = f.read()
                            # Look for Default=1 profile or any .default profile
                            import re
                            # Find profile with Default=1
                            for section in content.split('['):
                                if 'Default=1' in section:
                                    path_match = re.search(r'Path=(.+)', section)
                                    if path_match:
                                        default_profile = path_match.group(1).strip()
                                        break
                            # Fallback: find any .default profile
                            if not default_profile:
                                for entry in os.listdir(firefox_profile_path):
                                    if '.default' in entry and os.path.isdir(os.path.join(firefox_profile_path, entry)):
                                        default_profile = entry
                                        break
                    
                    if default_profile:
                        full_profile_path = os.path.join(firefox_profile_path, default_profile)
                        if os.path.isdir(full_profile_path):
                            # Use the profile directory
                            firefox_options.add_argument("-profile")
                            firefox_options.add_argument(full_profile_path)
                            logger.info(f"Using Firefox profile: {default_profile}")
                
                # Disable automation indicators
                firefox_options.set_preference("dom.webdriver.enabled", False)
                firefox_options.set_preference("useAutomationExtension", False)
                firefox_options.set_preference("marionette.enabled", False)
                
                # Disable notifications
                firefox_options.set_preference("dom.webnotifications.enabled", False)
                
                self.driver = webdriver.Firefox(options=firefox_options)
                self._browser_type = 'firefox'
                logger.info("Firefox WebDriver created with native profile")
                return self.driver
                
            except Exception as e:
                logger.warning(f"Could not create Firefox driver: {e}")
            
            # Fallback to Chrome (without user-data-dir to avoid lock issues)
            try:
                chrome_options = ChromeOptions()
                
                # Essential options
                chrome_options.add_argument("--start-maximized")
                chrome_options.add_argument("--disable-infobars")
                chrome_options.add_argument("--disable-blink-features=AutomationControlled")
                
                # Hide automation
                chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
                chrome_options.add_experimental_option('useAutomationExtension', False)
                
                self.driver = webdriver.Chrome(options=chrome_options)
                self._browser_type = 'chrome'
                
                # Hide webdriver flag
                try:
                    self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                        'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
                    })
                except:
                    pass
                
                logger.info("Chrome WebDriver created")
                return self.driver
                
            except Exception as e:
                logger.warning(f"Could not create Chrome driver: {e}")
            
            logger.error("Could not create any WebDriver")
            return None
                
        except ImportError as e:
            logger.error(f"Selenium not installed: {e}")
            return None
    
    async def _skip_youtube_ads(self, timeout: int = 30) -> bool:
        """Skip YouTube ads by clicking skip button"""
        if not self.driver:
            return False
            
        from selenium.webdriver.common.by import By
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Skip button selectors - updated for 2024/2025 YouTube
                skip_selectors = [
                    "button.ytp-skip-ad-button",
                    "button.ytp-ad-skip-button",
                    "button.ytp-ad-skip-button-modern",
                    ".ytp-ad-skip-button-slot button",
                    ".ytp-skip-ad-button",
                    ".ytp-ad-skip-button-container button",
                    "button[class*='skip']",
                    ".ytp-ad-overlay-close-button",
                ]
                
                for selector in skip_selectors:
                    try:
                        skip_btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                        if skip_btn.is_displayed() and skip_btn.is_enabled():
                            await asyncio.sleep(0.3)
                            skip_btn.click()
                            logger.info("Clicked skip ad button")
                            await asyncio.sleep(0.5)
                            return True
                    except:
                        continue
                
                # Try XPath for "Skip" text - multiple languages
                try:
                    skip_btns = self.driver.find_elements(By.XPATH, 
                        "//button[contains(., 'Skip') or contains(., 'skip') or contains(., 'SKIP')]")
                    for btn in skip_btns:
                        if btn.is_displayed():
                            btn.click()
                            logger.info("Clicked skip ad via text")
                            await asyncio.sleep(0.5)
                            return True
                except:
                    pass
                
                # Check for video ad indicator and wait
                try:
                    ad_indicator = self.driver.find_element(By.CSS_SELECTOR, ".ytp-ad-player-overlay")
                    if ad_indicator:
                        await asyncio.sleep(0.5)
                        continue
                except:
                    # No ad playing
                    return False
                
                await asyncio.sleep(0.5)
            except Exception as e:
                await asyncio.sleep(0.5)
        
        return False
    
    async def _continuous_ad_monitor(self):
        """Background task to continuously skip ads"""
        while self._check_session_valid():
            try:
                await self._skip_youtube_ads(timeout=2)
                await asyncio.sleep(3)
            except:
                break
    
    def _start_ad_monitor(self):
        """Start background ad monitoring"""
        if self._ad_skip_task is None or self._ad_skip_task.done():
            try:
                loop = asyncio.get_event_loop()
                self._ad_skip_task = loop.create_task(self._continuous_ad_monitor())
            except:
                pass
    
    async def youtube_autoplay(self, search_query: str) -> Dict[str, Any]:
        """Search YouTube and autoplay first video with ad skipping"""
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            driver = self._get_driver()
            if not driver:
                import webbrowser
                url = f"https://www.youtube.com/results?search_query={search_query.replace(' ', '+')}"
                webbrowser.open(url)
                return {"success": True, "message": "Opened", "method": "native"}
            
            # Navigate to YouTube search
            url = f"https://www.youtube.com/results?search_query={search_query.replace(' ', '+')}"
            logger.info(f"Navigating to: {url}")
            driver.get(url)
            
            # Wait for page to load
            await asyncio.sleep(3)
            
            # Accept cookies if prompted (European users)
            try:
                cookie_buttons = driver.find_elements(By.XPATH, 
                    "//button[contains(., 'Accept') or contains(., 'Agree') or contains(., 'I agree')]")
                for btn in cookie_buttons:
                    if btn.is_displayed():
                        btn.click()
                        await asyncio.sleep(1)
                        break
            except:
                pass
            
            # Find and click first video (skip ads/shorts)
            video_title = "Video"
            for selector in [
                "ytd-video-renderer #video-title",
                "a#video-title", 
                "ytd-video-renderer a#thumbnail"
            ]:
                try:
                    videos = driver.find_elements(By.CSS_SELECTOR, selector)
                    for video_link in videos:
                        href = video_link.get_attribute("href") or ""
                        # Skip shorts and ads
                        if "/shorts/" in href or "googleads" in href:
                            continue
                        if video_link.is_displayed():
                            video_title = video_link.get_attribute("title") or video_link.text or "Video"
                            logger.info(f"Found video: {video_title}")
                            video_link.click()
                            break
                    else:
                        continue
                    break
                except:
                    continue
            
            # Wait for video page to load
            await asyncio.sleep(3)
            
            # Skip ads
            await self._skip_youtube_ads(timeout=15)
            
            # Start background ad monitor
            self._start_ad_monitor()
            
            self._last_video_url = driver.current_url
            
            return {
                "success": True,
                "message": "Playing",
                "video_title": video_title[:50] if len(video_title) > 50 else video_title,
                "video_url": driver.current_url,
            }
            
        except Exception as e:
            logger.error(f"YouTube autoplay error: {e}")
            try:
                import webbrowser
                url = f"https://www.youtube.com/results?search_query={search_query.replace(' ', '+')}"
                webbrowser.open(url)
                return {"success": True, "message": "Opened", "method": "fallback"}
            except:
                return {"success": False, "error": str(e)}
    
    async def youtube_control(self, action: str) -> Dict[str, Any]:
        """Control YouTube playback"""
        if not self._check_session_valid():
            return {"success": False, "error": "No browser open"}
        
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys
            from selenium.webdriver.common.action_chains import ActionChains
            
            driver = self.driver
            action = action.lower().strip()
            
            # Check if on YouTube
            current_url = driver.current_url
            if 'youtube.com' not in current_url:
                return {"success": False, "error": "Not on YouTube"}
            
            # Try to find video element
            video = None
            try:
                video = driver.find_element(By.CSS_SELECTOR, "video")
            except:
                pass
            
            if action in ['pause', 'stop']:
                if video:
                    driver.execute_script("arguments[0].pause();", video)
                else:
                    # Use keyboard shortcut
                    driver.find_element(By.TAG_NAME, "body").send_keys("k")
                return {"success": True, "message": "Paused"}
            
            elif action in ['play', 'resume']:
                if video:
                    driver.execute_script("arguments[0].play();", video)
                else:
                    driver.find_element(By.TAG_NAME, "body").send_keys("k")
                return {"success": True, "message": "Playing"}
            
            elif action == 'toggle':
                if video:
                    is_paused = driver.execute_script("return arguments[0].paused;", video)
                    if is_paused:
                        driver.execute_script("arguments[0].play();", video)
                        return {"success": True, "message": "Playing"}
                    else:
                        driver.execute_script("arguments[0].pause();", video)
                        return {"success": True, "message": "Paused"}
                else:
                    driver.find_element(By.TAG_NAME, "body").send_keys("k")
                    return {"success": True, "message": "Toggled"}
            
            elif action == 'mute':
                if video:
                    driver.execute_script("arguments[0].muted = true;", video)
                else:
                    driver.find_element(By.TAG_NAME, "body").send_keys("m")
                return {"success": True, "message": "Muted"}
            
            elif action == 'unmute':
                if video:
                    driver.execute_script("arguments[0].muted = false;", video)
                else:
                    driver.find_element(By.TAG_NAME, "body").send_keys("m")
                return {"success": True, "message": "Unmuted"}
            
            elif action == 'volume_up':
                if video:
                    current = driver.execute_script("return arguments[0].volume;", video)
                    new_vol = min(1.0, current + 0.1)
                    driver.execute_script(f"arguments[0].volume = {new_vol};", video)
                    return {"success": True, "message": f"Volume {int(new_vol * 100)}%"}
                else:
                    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ARROW_UP)
                    return {"success": True, "message": "Volume up"}
            
            elif action == 'volume_down':
                if video:
                    current = driver.execute_script("return arguments[0].volume;", video)
                    new_vol = max(0.0, current - 0.1)
                    driver.execute_script(f"arguments[0].volume = {new_vol};", video)
                    return {"success": True, "message": f"Volume {int(new_vol * 100)}%"}
                else:
                    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ARROW_DOWN)
                    return {"success": True, "message": "Volume down"}
            
            elif action == 'fullscreen':
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, ".ytp-fullscreen-button")
                    btn.click()
                except:
                    driver.find_element(By.TAG_NAME, "body").send_keys("f")
                return {"success": True, "message": "Fullscreen"}
            
            elif action == 'seek_forward':
                if video:
                    current = driver.execute_script("return arguments[0].currentTime;", video)
                    driver.execute_script(f"arguments[0].currentTime = {current + 10};", video)
                else:
                    driver.find_element(By.TAG_NAME, "body").send_keys("l")
                return {"success": True, "message": "+10s"}
            
            elif action == 'seek_backward':
                if video:
                    current = driver.execute_script("return arguments[0].currentTime;", video)
                    driver.execute_script(f"arguments[0].currentTime = {max(0, current - 10)};", video)
                else:
                    driver.find_element(By.TAG_NAME, "body").send_keys("j")
                return {"success": True, "message": "-10s"}
            
            elif action == 'skip_ad':
                skipped = await self._skip_youtube_ads(timeout=5)
                return {"success": True, "message": "Skipped" if skipped else "No ad"}
            
            elif action in ['next', 'next_video']:
                # Skip any current ad first
                await self._skip_youtube_ads(timeout=3)
                
                # Try clicking next button
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, ".ytp-next-button")
                    if btn.is_displayed() and btn.is_enabled():
                        btn.click()
                        logger.info("Clicked next button")
                except Exception as e:
                    logger.debug(f"Next button click failed: {e}")
                    # Use keyboard shortcut - Shift+N for next in playlist
                    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.SHIFT + "n")
                
                await asyncio.sleep(2)
                await self._skip_youtube_ads(timeout=10)
                return {"success": True, "message": "Playing"}
            
            elif action in ['previous', 'prev', 'previous_video']:
                # Skip any current ad first
                await self._skip_youtube_ads(timeout=3)
                
                # Try clicking previous button - YouTube doesn't always have this
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, ".ytp-prev-button")
                    if btn.is_displayed() and btn.is_enabled():
                        btn.click()
                        logger.info("Clicked previous button")
                        await asyncio.sleep(2)
                        await self._skip_youtube_ads(timeout=10)
                        return {"success": True, "message": "Playing"}
                except:
                    pass
                
                # Fallback: Use keyboard shortcut Shift+P
                try:
                    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.SHIFT + "p")
                    await asyncio.sleep(2)
                    await self._skip_youtube_ads(timeout=10)
                    return {"success": True, "message": "Playing"}
                except:
                    pass
                
                # Final fallback: Click back twice in history (like double-clicking previous)
                try:
                    driver.back()
                    await asyncio.sleep(1)
                    # If we went to search results, that counts as going back
                    if '/watch' not in driver.current_url:
                        driver.back()
                        await asyncio.sleep(1)
                    await self._skip_youtube_ads(timeout=10)
                    return {"success": True, "message": "Playing"}
                except:
                    return {"success": False, "error": "No previous video"}
            
            elif action == 'restart':
                if video:
                    driver.execute_script("arguments[0].currentTime = 0;", video)
                else:
                    driver.find_element(By.TAG_NAME, "body").send_keys("0")
                return {"success": True, "message": "Restarted"}
            
            else:
                return {"success": False, "error": f"Unknown: {action}"}
            
        except Exception as e:
            logger.error(f"YouTube control error: {e}")
            return {"success": False, "error": str(e)}
    
    async def browser_control(self, action: str, url: str = None) -> Dict[str, Any]:
        """Browser controls"""
        action = action.lower().strip()
        
        if action not in ['new_tab', 'goto', 'open_browser', 'open'] and not self._check_session_valid():
            return {"success": False, "error": "No browser open"}
        
        try:
            if action in ['new_tab', 'open_tab']:
                driver = self._get_driver()  # Opens browser if not open
                if not driver:
                    return {"success": False, "error": "Could not open browser"}
                # Open new tab
                driver.execute_script("window.open('about:blank', '_blank');")
                # Switch to new tab
                driver.switch_to.window(driver.window_handles[-1])
                if url:
                    driver.get(url)
                return {"success": True, "message": "New tab opened"}
            
            elif action in ['open_browser', 'open']:
                driver = self._get_driver()
                if not driver:
                    return {"success": False, "error": "Could not open browser"}
                if url:
                    driver.get(url)
                else:
                    driver.get("https://www.google.com")
                return {"success": True, "message": "Browser opened"}
            
            elif action == 'close_tab':
                if len(self.driver.window_handles) > 1:
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[-1])
                    return {"success": True, "message": "Tab closed"}
                else:
                    # Last tab - close browser
                    self.driver.quit()
                    self.driver = None
                    self._browser_type = None
                    return {"success": True, "message": "Browser closed"}
            
            elif action == 'switch_tab':
                handles = self.driver.window_handles
                current = self.driver.current_window_handle
                idx = (handles.index(current) + 1) % len(handles)
                self.driver.switch_to.window(handles[idx])
                return {"success": True, "message": f"Switched to tab {idx + 1}"}
            
            elif action == 'back':
                self.driver.back()
                return {"success": True, "message": "Back"}
            
            elif action == 'forward':
                self.driver.forward()
                return {"success": True, "message": "Forward"}
            
            elif action == 'refresh':
                self.driver.refresh()
                return {"success": True, "message": "Refreshed"}
            
            elif action == 'maximize':
                self.driver.maximize_window()
                return {"success": True, "message": "Maximized"}
            
            elif action == 'minimize':
                self.driver.minimize_window()
                return {"success": True, "message": "Minimized"}
            
            elif action == 'goto' and url:
                driver = self._get_driver()
                if driver:
                    if not url.startswith('http'):
                        url = 'https://' + url
                    driver.get(url)
                    return {"success": True, "message": "Opened"}
                return {"success": False, "error": "No browser"}
            
            elif action in ['close_browser', 'close', 'quit']:
                if self.driver:
                    self.driver.quit()
                    self.driver = None
                    self._browser_type = None
                return {"success": True, "message": "Browser closed"}
            
            else:
                return {"success": False, "error": f"Unknown: {action}"}
            
        except Exception as e:
            logger.error(f"Browser control error: {e}")
            return {"success": False, "error": str(e)}
    
    async def google_search(self, query: str) -> Dict[str, Any]:
        """Search Google"""
        try:
            driver = self._get_driver()
            if driver:
                driver.get(f"https://www.google.com/search?q={query.replace(' ', '+')}")
            else:
                import webbrowser
                webbrowser.open(f"https://www.google.com/search?q={query.replace(' ', '+')}")
            return {"success": True, "message": "Searched"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_status(self) -> Dict[str, Any]:
        """Get browser status"""
        if not self._check_session_valid():
            return {"active": False}
        try:
            return {
                "active": True, 
                "browser": self._browser_type, 
                "url": self.driver.current_url,
                "tabs": len(self.driver.window_handles)
            }
        except:
            return {"active": False}
    
    def close(self):
        """Close browser"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
            self._browser_type = None


# Global instance
browser_tool = BrowserTool()
