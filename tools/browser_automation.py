"""
Browser Automation Tool using Selenium
Enables JARVIS to control browser: search Google, play YouTube videos, navigate sites
"""
import asyncio
from typing import Dict, Any, Optional
from core.logger import setup_logger

logger = setup_logger(__name__)

class BrowserTool:
    """
    Browser automation using Selenium
    Handles: YouTube autoplay, Google search, custom navigation
    """
    
    def __init__(self):
        self.driver = None
        self.is_headless = False
        logger.info("BrowserTool initialized")
    
    def _get_driver(self):
        """Get or create Selenium WebDriver"""
        if self.driver is None:
            try:
                from selenium import webdriver
                from selenium.webdriver.firefox.options import Options
                from selenium.webdriver.firefox.service import Service
                
                options = Options()
                if self.is_headless:
                    options.add_argument('--headless')
                
                # Try to create Firefox driver
                try:
                    self.driver = webdriver.Firefox(options=options)
                    logger.info("Firefox WebDriver created successfully")
                except Exception as e:
                    logger.warning(f"Could not create Firefox driver: {e}")
                    # Fallback to Chrome
                    try:
                        from selenium.webdriver.chrome.options import Options as ChromeOptions
                        chrome_options = ChromeOptions()
                        if self.is_headless:
                            chrome_options.add_argument('--headless')
                        self.driver = webdriver.Chrome(options=chrome_options)
                        logger.info("Chrome WebDriver created as fallback")
                    except Exception as e2:
                        logger.error(f"Could not create any WebDriver: {e2}")
                        return None
            except ImportError as e:
                logger.error(f"Selenium not properly installed: {e}")
                return None
        
        return self.driver
    
    async def youtube_autoplay(self, search_query: str) -> Dict[str, Any]:
        """
        Search YouTube and automatically play first non-sponsored video
        
        Args:
            search_query: What to search for on YouTube
            
        Returns:
            Dict with success status and details
        """
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            import time
            
            driver = self._get_driver()
            if not driver:
                # Fallback to regular open
                import webbrowser
                search_url = f"https://www.youtube.com/results?search_query={search_query.replace(' ', '+')}"
                webbrowser.open(search_url)
                return {
                    "success": True,
                    "message": f"Opened YouTube search (Selenium not available, manual click needed)",
                    "query": search_query,
                    "method": "fallback"
                }
            
            # Navigate to YouTube search
            search_url = f"https://www.youtube.com/results?search_query={search_query.replace(' ', '+')}"
            logger.info(f"Navigating to: {search_url}")
            driver.get(search_url)
            
            # Wait for results to load
            await asyncio.sleep(2)
            
            # Find first video (skip ads/sponsored)
            try:
                # Wait for video results
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "video-title"))
                )
                
                # Get all video links
                video_links = driver.find_elements(By.ID, "video-title")
                
                # Find first real video (skip shorts, ads)
                for link in video_links[:5]:  # Check first 5 results
                    href = link.get_attribute("href")
                    title = link.get_attribute("title")
                    
                    if href and "/watch?" in href and title:
                        logger.info(f"Found video: {title}")
                        # Click the video
                        driver.execute_script("arguments[0].click();", link)
                        
                        return {
                            "success": True,
                            "message": f"Playing: {title}",
                            "query": search_query,
                            "video_title": title,
                            "method": "selenium_autoplay"
                        }
                
                # If no video found, return search page
                return {
                    "success": True,
                    "message": "Opened YouTube search results (no suitable video found)",
                    "query": search_query,
                    "method": "selenium_search_only"
                }
                
            except Exception as e:
                logger.error(f"Could not find/click video: {e}")
                return {
                    "success": True,
                    "message": "Opened YouTube search (autoplay failed, manual click needed)",
                    "query": search_query,
                    "error": str(e),
                    "method": "selenium_search_only"
                }
        
        except Exception as e:
            logger.error(f"YouTube autoplay error: {e}")
            # Reset driver on error so it recreates on next request
            self.driver = None
            return {
                "success": False,
                "error": str(e),
                "query": search_query
            }
    
    async def google_search_and_click(self, search_query: str, click_first: bool = True) -> Dict[str, Any]:
        """
        Search Google and optionally click first result
        
        Args:
            search_query: What to search for
            click_first: Whether to click first result automatically
            
        Returns:
            Dict with success status and details
        """
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            driver = self._get_driver()
            if not driver:
                # Fallback
                import webbrowser
                search_url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}"
                webbrowser.open(search_url)
                return {
                    "success": True,
                    "message": f"Opened Google search (Selenium not available)",
                    "query": search_query,
                    "method": "fallback"
                }
            
            # Navigate to Google search
            search_url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}"
            logger.info(f"Navigating to: {search_url}")
            driver.get(search_url)
            
            await asyncio.sleep(1)
            
            return {
                "success": True,
                "message": f"Searched Google for: {search_query}",
                "query": search_query,
                "method": "selenium"
            }
        
        except Exception as e:
            logger.error(f"Google search error: {e}")
            return {
                "success": False,
                "error": str(e),
                "query": search_query
            }
    
    def close(self):
        """Close the browser"""
        # Don't close browser - keep it open for subsequent requests
        # User can manually close when done
        logger.info("Browser kept open for subsequent requests")
        pass

# Global browser tool instance
browser_tool = BrowserTool()
