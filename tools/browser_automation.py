"""
Browser Automation Tool using Selenium
Enables JARVIS to control browser: search Google, play YouTube videos, navigate sites
Comprehensive media controls, ad skipping, and browser management
"""
import asyncio
import time
from typing import Dict, Any, Optional
from core.logger import setup_logger

logger = setup_logger(__name__)


class BrowserTool:
    """
    Browser automation using Selenium
    Handles: YouTube autoplay, ad skipping, media controls, Google search, navigation
    """
    
    def __init__(self):
        self.driver = None
        self.is_headless = False
        self._last_video_url = None
        self._browser_type = None
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
        """Get or create Selenium WebDriver with proper session management"""
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
            
            # Try Firefox first
            try:
                firefox_options = FirefoxOptions()
                if self.is_headless:
                    firefox_options.add_argument('--headless')
                
                self.driver = webdriver.Firefox(options=firefox_options)
                self._browser_type = 'firefox'
                logger.info("Firefox WebDriver created successfully")
                return self.driver
            except Exception as e:
                logger.warning(f"Could not create Firefox driver: {e}")
            
            # Fallback to Chrome
            try:
                chrome_options = ChromeOptions()
                if self.is_headless:
                    chrome_options.add_argument('--headless')
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument('--disable-dev-shm-usage')
                chrome_options.add_argument('--disable-blink-features=AutomationControlled')
                chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
                chrome_options.add_experimental_option('useAutomationExtension', False)
                chrome_options.add_argument('--start-maximized')
                
                self.driver = webdriver.Chrome(options=chrome_options)
                self._browser_type = 'chrome'
                
                # Hide webdriver flag
                self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                    'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
                })
                
                logger.info("Chrome WebDriver created as fallback")
                return self.driver
            except Exception as e2:
                logger.error(f"Could not create any WebDriver: {e2}")
                return None
                
        except ImportError as e:
            logger.error(f"Selenium not properly installed: {e}")
            return None
    
    async def _skip_youtube_ads(self, timeout: int = 30) -> bool:
        """Skip YouTube ads by clicking skip button or waiting for ad to finish"""
        if not self.driver:
            return False
            
        from selenium.webdriver.common.by import By
        
        start_time = time.time()
        ad_found = False
        
        while time.time() - start_time < timeout:
            try:
                # Check for skip ad button (multiple possible selectors)
                skip_selectors = [
                    "button.ytp-skip-ad-button",
                    "button.ytp-ad-skip-button",
                    "button.ytp-ad-skip-button-modern",
                    ".ytp-ad-skip-button-slot button",
                    ".ytp-skip-ad-button",
                    ".ytp-ad-skip-button-text",
                ]
                
                for selector in skip_selectors:
                    try:
                        skip_btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                        if skip_btn.is_displayed() and skip_btn.is_enabled():
                            await asyncio.sleep(0.5)
                            skip_btn.click()
                            logger.info("Clicked skip ad button")
                            ad_found = True
                            await asyncio.sleep(1)
                            return True
                    except:
                        continue
                
                # Check for "Skip Ads" button with different text
                try:
                    skip_btns = self.driver.find_elements(By.XPATH, 
                        "//*[contains(text(), 'Skip') and (contains(text(), 'Ad') or contains(text(), 'ad'))]")
                    for btn in skip_btns:
                        if btn.is_displayed():
                            btn.click()
                            logger.info("Clicked skip ad via text match")
                            return True
                except:
                    pass
                
                # Check if there's an ad playing but no skip button yet
                ad_indicators = [
                    ".ytp-ad-player-overlay",
                    ".ytp-ad-overlay-container",
                    ".ad-showing",
                    ".ytp-ad-text",
                    "div.ytp-ad-module",
                ]
                
                is_ad_playing = False
                for indicator in ad_indicators:
                    try:
                        ad_elem = self.driver.find_element(By.CSS_SELECTOR, indicator)
                        if ad_elem.is_displayed():
                            is_ad_playing = True
                            ad_found = True
                            break
                    except:
                        continue
                
                # Check for video-ads class on player
                try:
                    player = self.driver.find_element(By.CLASS_NAME, "html5-video-player")
                    player_class = player.get_attribute("class") or ""
                    if "ad-showing" in player_class or "ad-interrupting" in player_class:
                        is_ad_playing = True
                        ad_found = True
                except:
                    pass
                
                # If no ad is playing, we're done
                if not is_ad_playing:
                    if ad_found:
                        logger.info("Ad finished playing")
                    return True
                
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.debug(f"Ad skip check error: {e}")
                await asyncio.sleep(1)
        
        logger.warning(f"Ad skip timeout after {timeout}s")
        return ad_found
    
    async def youtube_autoplay(self, search_query: str) -> Dict[str, Any]:
        """Search YouTube and automatically play first non-sponsored video"""
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            driver = self._get_driver()
            if not driver:
                import webbrowser
                search_url = f"https://www.youtube.com/results?search_query={search_query.replace(' ', '+')}"
                webbrowser.open(search_url)
                return {
                    "success": True,
                    "message": f"Opened YouTube search (Selenium not available)",
                    "query": search_query,
                    "method": "fallback"
                }
            
            search_url = f"https://www.youtube.com/results?search_query={search_query.replace(' ', '+')}"
            logger.info(f"Navigating to: {search_url}")
            driver.get(search_url)
            
            await asyncio.sleep(2)
            
            # Handle cookie consent if present
            try:
                consent_buttons = driver.find_elements(By.XPATH, 
                    "//button[contains(., 'Accept') or contains(., 'Reject')]")
                for btn in consent_buttons:
                    if btn.is_displayed():
                        btn.click()
                        await asyncio.sleep(1)
                        break
            except:
                pass
            
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "video-title"))
                )
                
                video_links = driver.find_elements(By.ID, "video-title")
                
                for link in video_links[:5]:
                    href = link.get_attribute("href")
                    title = link.get_attribute("title")
                    
                    if href and "/watch?" in href and title:
                        if "/shorts/" in href:
                            continue
                        
                        logger.info(f"Found video: {title}")
                        self._last_video_url = href
                        
                        driver.execute_script("arguments[0].click();", link)
                        await asyncio.sleep(3)
                        await self._skip_youtube_ads(timeout=20)
                        
                        try:
                            video_elem = driver.find_element(By.TAG_NAME, "video")
                            is_paused = driver.execute_script("return arguments[0].paused;", video_elem)
                            if is_paused:
                                driver.execute_script("arguments[0].play();", video_elem)
                        except:
                            pass
                        
                        return {
                            "success": True,
                            "message": f"Playing: {title}",
                            "query": search_query,
                            "video_title": title,
                            "video_url": href,
                            "method": "selenium_autoplay"
                        }
                
                return {
                    "success": True,
                    "message": "Opened YouTube search results",
                    "query": search_query,
                    "method": "selenium_search_only"
                }
                
            except Exception as e:
                logger.error(f"Could not find/click video: {e}")
                return {
                    "success": True,
                    "message": "Opened YouTube search",
                    "query": search_query,
                    "error": str(e),
                    "method": "selenium_search_only"
                }
        
        except Exception as e:
            logger.error(f"YouTube autoplay error: {e}")
            self.driver = None
            self._browser_type = None
            return {"success": False, "error": str(e), "query": search_query}
    
    async def youtube_control(self, action: str) -> Dict[str, Any]:
        """Control YouTube playback: play, pause, next, previous, mute, volume, etc."""
        if not self._check_session_valid():
            return {"success": False, "error": "No active browser session. Play a video first."}
        
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys
            
            driver = self.driver
            current_url = driver.current_url
            
            if 'youtube.com' not in current_url:
                return {"success": False, "error": "Not on YouTube. Play a video first."}
            
            try:
                video = driver.find_element(By.TAG_NAME, "video")
            except:
                return {"success": False, "error": "No video element found."}
            
            action = action.lower().strip()
            
            if action in ['play', 'resume']:
                driver.execute_script("arguments[0].play();", video)
                return {"success": True, "message": "Video playing"}
            
            elif action == 'pause':
                driver.execute_script("arguments[0].pause();", video)
                return {"success": True, "message": "Video paused"}
            
            elif action == 'toggle':
                is_paused = driver.execute_script("return arguments[0].paused;", video)
                if is_paused:
                    driver.execute_script("arguments[0].play();", video)
                    return {"success": True, "message": "Video resumed"}
                else:
                    driver.execute_script("arguments[0].pause();", video)
                    return {"success": True, "message": "Video paused"}
            
            elif action == 'mute':
                driver.execute_script("arguments[0].muted = true;", video)
                return {"success": True, "message": "Video muted"}
            
            elif action == 'unmute':
                driver.execute_script("arguments[0].muted = false;", video)
                return {"success": True, "message": "Video unmuted"}
            
            elif action == 'volume_up':
                current_vol = driver.execute_script("return arguments[0].volume;", video)
                new_vol = min(1.0, current_vol + 0.1)
                driver.execute_script(f"arguments[0].volume = {new_vol};", video)
                return {"success": True, "message": f"Volume: {int(new_vol * 100)}%"}
            
            elif action == 'volume_down':
                current_vol = driver.execute_script("return arguments[0].volume;", video)
                new_vol = max(0.0, current_vol - 0.1)
                driver.execute_script(f"arguments[0].volume = {new_vol};", video)
                return {"success": True, "message": f"Volume: {int(new_vol * 100)}%"}
            
            elif action == 'fullscreen':
                try:
                    driver.find_element(By.CSS_SELECTOR, ".ytp-fullscreen-button").click()
                except:
                    body = driver.find_element(By.TAG_NAME, "body")
                    body.send_keys("f")
                return {"success": True, "message": "Toggled fullscreen"}
            
            elif action in ['seek_forward', 'forward', 'skip_forward']:
                driver.execute_script("arguments[0].currentTime += 10;", video)
                return {"success": True, "message": "Skipped forward 10 seconds"}
            
            elif action in ['seek_backward', 'backward', 'rewind']:
                driver.execute_script("arguments[0].currentTime -= 10;", video)
                return {"success": True, "message": "Rewound 10 seconds"}
            
            elif action == 'skip_ad':
                skipped = await self._skip_youtube_ads(timeout=10)
                if skipped:
                    return {"success": True, "message": "Ad skipped/finished"}
                return {"success": False, "error": "No skippable ad found"}
            
            elif action in ['next', 'next_video']:
                try:
                    next_btn = driver.find_element(By.CSS_SELECTOR, ".ytp-next-button")
                    next_btn.click()
                    await asyncio.sleep(2)
                    await self._skip_youtube_ads(timeout=10)
                    return {"success": True, "message": "Playing next video"}
                except:
                    body = driver.find_element(By.TAG_NAME, "body")
                    body.send_keys(Keys.SHIFT + "n")
                    return {"success": True, "message": "Attempting next video"}
            
            elif action in ['previous', 'prev', 'previous_video']:
                body = driver.find_element(By.TAG_NAME, "body")
                body.send_keys(Keys.SHIFT + "p")
                return {"success": True, "message": "Attempting previous video"}
            
            elif action == 'restart':
                driver.execute_script("arguments[0].currentTime = 0;", video)
                return {"success": True, "message": "Video restarted"}
            
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
            
        except Exception as e:
            logger.error(f"YouTube control error: {e}")
            return {"success": False, "error": str(e)}
    
    async def browser_control(self, action: str, url: str = None) -> Dict[str, Any]:
        """Browser controls: new_tab, close_tab, back, forward, refresh, maximize, minimize"""
        if action not in ['new_tab', 'goto'] and not self._check_session_valid():
            return {"success": False, "error": "No active browser session"}
        
        try:
            action = action.lower().strip()
            
            if action == 'new_tab':
                driver = self._get_driver()
                if not driver:
                    return {"success": False, "error": "Could not create browser"}
                if url:
                    driver.execute_script(f"window.open('{url}', '_blank');")
                else:
                    driver.execute_script("window.open('about:blank', '_blank');")
                driver.switch_to.window(driver.window_handles[-1])
                return {"success": True, "message": "Opened new tab"}
            
            elif action == 'close_tab':
                if len(self.driver.window_handles) > 1:
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[-1])
                    return {"success": True, "message": "Tab closed"}
                else:
                    return {"success": False, "error": "Cannot close last tab"}
            
            elif action == 'switch_tab':
                handles = self.driver.window_handles
                current = self.driver.current_window_handle
                current_idx = handles.index(current)
                next_idx = (current_idx + 1) % len(handles)
                self.driver.switch_to.window(handles[next_idx])
                return {"success": True, "message": f"Switched to tab {next_idx + 1}"}
            
            elif action == 'back':
                self.driver.back()
                return {"success": True, "message": "Navigated back"}
            
            elif action == 'forward':
                self.driver.forward()
                return {"success": True, "message": "Navigated forward"}
            
            elif action == 'refresh':
                self.driver.refresh()
                return {"success": True, "message": "Page refreshed"}
            
            elif action == 'maximize':
                self.driver.maximize_window()
                return {"success": True, "message": "Window maximized"}
            
            elif action == 'minimize':
                self.driver.minimize_window()
                return {"success": True, "message": "Window minimized"}
            
            elif action == 'goto' and url:
                driver = self._get_driver()
                if not driver:
                    return {"success": False, "error": "Could not create browser"}
                driver.get(url)
                return {"success": True, "message": f"Navigated to {url}"}
            
            elif action == 'close_browser':
                if self.driver:
                    self.driver.quit()
                    self.driver = None
                    self._browser_type = None
                    return {"success": True, "message": "Browser closed"}
                return {"success": True, "message": "No browser to close"}
            
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
            
        except Exception as e:
            logger.error(f"Browser control error: {e}")
            return {"success": False, "error": str(e)}
    
    async def google_search_and_click(self, search_query: str, click_first: bool = True) -> Dict[str, Any]:
        """Search Google"""
        try:
            from selenium.webdriver.common.by import By
            
            driver = self._get_driver()
            if not driver:
                import webbrowser
                search_url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}"
                webbrowser.open(search_url)
                return {"success": True, "message": "Opened Google search", "method": "fallback"}
            
            search_url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}"
            logger.info(f"Navigating to: {search_url}")
            driver.get(search_url)
            await asyncio.sleep(1)
            
            return {"success": True, "message": f"Searched Google for: {search_query}", "method": "selenium"}
        
        except Exception as e:
            logger.error(f"Google search error: {e}")
            return {"success": False, "error": str(e)}
    
    def get_status(self) -> Dict[str, Any]:
        """Get current browser status"""
        if not self._check_session_valid():
            return {"active": False, "browser": None, "url": None}
        
        try:
            return {
                "active": True,
                "browser": self._browser_type,
                "url": self.driver.current_url,
                "title": self.driver.title,
                "tabs": len(self.driver.window_handles)
            }
        except:
            return {"active": False, "browser": None, "url": None}
    
    def close(self):
        """Close the browser completely"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
            self._browser_type = None
        logger.info("Browser closed")


# Global browser tool instance
browser_tool = BrowserTool()
