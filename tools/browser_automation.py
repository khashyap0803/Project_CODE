"""
Browser Automation Tool using Selenium
Enables JARVIS to control browser: search Google, play YouTube videos, navigate sites
Uses user's actual browser profile for native experience
"""
import asyncio
import time
import subprocess
import os
from typing import Dict, Any, Optional
from core.logger import setup_logger

logger = setup_logger(__name__)


class BrowserTool:
    """
    Browser automation using Selenium with user's native browser
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
        """Get or create Selenium WebDriver using user's native browser"""
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
            from selenium.webdriver.chrome.options import Options as ChromeOptions
            
            # Try Chrome first (better YouTube compatibility)
            try:
                chrome_options = ChromeOptions()
                
                # Essential options - NO sandbox flags that break window decorations
                chrome_options.add_argument("--start-maximized")
                chrome_options.add_argument("--disable-infobars")
                
                # Hide automation but keep window decorations intact
                chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
                chrome_options.add_experimental_option('useAutomationExtension', False)
                
                # Don't use: --no-sandbox, --disable-dev-shm-usage (breaks window controls)
                
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
            
            # Fallback to Firefox
            try:
                firefox_options = FirefoxOptions()
                self.driver = webdriver.Firefox(options=firefox_options)
                self._browser_type = 'firefox'
                logger.info("Firefox WebDriver created")
                return self.driver
                
            except Exception as e:
                logger.warning(f"Could not create Firefox driver: {e}")
            
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
                # Skip button selectors
                skip_selectors = [
                    "button.ytp-skip-ad-button",
                    "button.ytp-ad-skip-button",
                    "button.ytp-ad-skip-button-modern",
                    ".ytp-ad-skip-button-slot button",
                    ".ytp-skip-ad-button",
                    ".ytp-ad-skip-button-container button",
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
                
                # Try XPath for "Skip" text
                try:
                    skip_btns = self.driver.find_elements(By.XPATH, "//button[contains(., 'Skip')]")
                    for btn in skip_btns:
                        if btn.is_displayed():
                            btn.click()
                            logger.info("Clicked skip ad via text")
                            return True
                except:
                    pass
                
                # Check if ad is playing
                try:
                    ad_badge = self.driver.find_element(By.CSS_SELECTOR, ".ytp-ad-simple-ad-badge, .ad-showing")
                    await asyncio.sleep(0.5)
                    continue
                except:
                    # No ad, done
                    return True
                
                await asyncio.sleep(0.3)
                
            except Exception as e:
                await asyncio.sleep(0.5)
        
        return False
    
    async def _continuous_ad_monitor(self):
        """Background task to continuously skip ads"""
        while self._check_session_valid():
            try:
                from selenium.webdriver.common.by import By
                
                if 'youtube.com' not in self.driver.current_url:
                    await asyncio.sleep(2)
                    continue
                
                # Try to skip any visible ad
                for selector in ["button.ytp-skip-ad-button", "button.ytp-ad-skip-button", ".ytp-skip-ad-button"]:
                    try:
                        skip_btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                        if skip_btn.is_displayed() and skip_btn.is_enabled():
                            skip_btn.click()
                            logger.info("Auto-skipped ad")
                            break
                    except:
                        continue
                
                await asyncio.sleep(1)
                
            except:
                await asyncio.sleep(2)
    
    def _start_ad_monitor(self):
        """Start background ad monitor"""
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
            
            await asyncio.sleep(2)
            
            # Find and click first video
            video_title = "Video"
            for selector in ["ytd-video-renderer #video-title", "a#video-title"]:
                try:
                    video_link = driver.find_element(By.CSS_SELECTOR, selector)
                    video_title = video_link.get_attribute("title") or video_link.text or "Video"
                    logger.info(f"Found video: {video_title}")
                    video_link.click()
                    break
                except:
                    continue
            
            await asyncio.sleep(2)
            
            # Skip ads
            await self._skip_youtube_ads(timeout=15)
            
            # Start background ad monitor
            self._start_ad_monitor()
            
            self._last_video_url = driver.current_url
            
            return {
                "success": True,
                "message": f"Playing: {video_title[:50]}",
                "video_title": video_title,
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
            
            driver = self.driver
            action = action.lower().strip()
            
            if 'youtube.com' not in driver.current_url:
                return {"success": False, "error": "Not on YouTube"}
            
            try:
                video = driver.find_element(By.CSS_SELECTOR, "video")
            except:
                return {"success": False, "error": "No video found"}
            
            if action in ['pause', 'stop']:
                driver.execute_script("arguments[0].pause();", video)
                return {"success": True, "message": "Paused"}
            
            elif action in ['play', 'resume']:
                driver.execute_script("arguments[0].play();", video)
                return {"success": True, "message": "Playing"}
            
            elif action == 'toggle':
                is_paused = driver.execute_script("return arguments[0].paused;", video)
                if is_paused:
                    driver.execute_script("arguments[0].play();", video)
                    return {"success": True, "message": "Playing"}
                else:
                    driver.execute_script("arguments[0].pause();", video)
                    return {"success": True, "message": "Paused"}
            
            elif action == 'mute':
                driver.execute_script("arguments[0].muted = true;", video)
                return {"success": True, "message": "Muted"}
            
            elif action == 'unmute':
                driver.execute_script("arguments[0].muted = false;", video)
                return {"success": True, "message": "Unmuted"}
            
            elif action == 'volume_up':
                current = driver.execute_script("return arguments[0].volume;", video)
                new_vol = min(1.0, current + 0.1)
                driver.execute_script(f"arguments[0].volume = {new_vol};", video)
                return {"success": True, "message": f"Volume {int(new_vol * 100)}%"}
            
            elif action == 'volume_down':
                current = driver.execute_script("return arguments[0].volume;", video)
                new_vol = max(0.0, current - 0.1)
                driver.execute_script(f"arguments[0].volume = {new_vol};", video)
                return {"success": True, "message": f"Volume {int(new_vol * 100)}%"}
            
            elif action == 'fullscreen':
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, ".ytp-fullscreen-button")
                    btn.click()
                except:
                    driver.find_element(By.TAG_NAME, "body").send_keys("f")
                return {"success": True, "message": "Fullscreen"}
            
            elif action == 'seek_forward':
                current = driver.execute_script("return arguments[0].currentTime;", video)
                driver.execute_script(f"arguments[0].currentTime = {current + 10};", video)
                return {"success": True, "message": "+10s"}
            
            elif action == 'seek_backward':
                current = driver.execute_script("return arguments[0].currentTime;", video)
                driver.execute_script(f"arguments[0].currentTime = {max(0, current - 10)};", video)
                return {"success": True, "message": "-10s"}
            
            elif action == 'skip_ad':
                skipped = await self._skip_youtube_ads(timeout=5)
                return {"success": True, "message": "Skipped" if skipped else "No ad"}
            
            elif action in ['next', 'next_video']:
                await self._skip_youtube_ads(timeout=3)
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, ".ytp-next-button")
                    btn.click()
                except:
                    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.SHIFT + "n")
                await asyncio.sleep(2)
                await self._skip_youtube_ads(timeout=10)
                return {"success": True, "message": "Next video"}
            
            elif action in ['previous', 'prev']:
                await self._skip_youtube_ads(timeout=3)
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.SHIFT + "p")
                await asyncio.sleep(2)
                await self._skip_youtube_ads(timeout=10)
                return {"success": True, "message": "Previous video"}
            
            elif action == 'restart':
                driver.execute_script("arguments[0].currentTime = 0;", video)
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
            if action in ['new_tab', 'open_browser', 'open']:
                driver = self._get_driver()
                if not driver:
                    return {"success": False, "error": "Could not open browser"}
                if url:
                    driver.get(url)
                return {"success": True, "message": "Opened"}
            
            elif action == 'close_tab':
                if len(self.driver.window_handles) > 1:
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[-1])
                else:
                    self.driver.quit()
                    self.driver = None
                    self._browser_type = None
                return {"success": True, "message": "Closed"}
            
            elif action == 'switch_tab':
                handles = self.driver.window_handles
                current = self.driver.current_window_handle
                idx = (handles.index(current) + 1) % len(handles)
                self.driver.switch_to.window(handles[idx])
                return {"success": True, "message": f"Tab {idx + 1}"}
            
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
                    driver.get(url)
                    return {"success": True, "message": "Opened"}
                return {"success": False, "error": "No browser"}
            
            elif action in ['close_browser', 'close']:
                if self.driver:
                    self.driver.quit()
                    self.driver = None
                    self._browser_type = None
                return {"success": True, "message": "Closed"}
            
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
            return {"active": True, "browser": self._browser_type, "url": self.driver.current_url}
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
