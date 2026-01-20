import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import logging
import re

logger = logging.getLogger(__name__)

class ScraperService:
    def __init__(self):
        self.ua = UserAgent()

    async def scrape_url(self, url: str):
        """
        Scrapes a given URL using Playwright to handle dynamic content.
        Smartly detects platform based on URL.
        """
        async with async_playwright() as p:
            # Launch with anti-detection args
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=self.ua.random,
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()
            
            try:
                logger.info(f"Navigating to {url}")
                if "google.com/maps" in url or "goo.gl" in url:
                    raw_text = await self.scrape_google_maps(page, url)
                    status = "success" if raw_text else "failed"
                    return {
                        "url": url,
                        "raw_text": raw_text,
                        "status": status
                    }
        
                await page.goto(url, wait_until="networkidle", timeout=60000)
                
                # Basic scroll to load more content
                for _ in range(3):
                    await page.keyboard.press("End")
                    await asyncio.sleep(2)
                
                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # Remove scripts and styles
                for script in soup(["script", "style"]):
                    script.decompose()
                    
                text = soup.get_text(separator='\n')
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                cleaned_text = '\n'.join(lines[:500])
                
                return {
                    "url": url,
                    "raw_text": cleaned_text,
                    "status": "success"
                }

            except Exception as e:
                logger.error(f"Error scraping {url}: {e}")
                return {
                    "url": url,
                    "error": str(e),
                    "status": "failed"
                }
            finally:
                await browser.close()

    async def scrape_google_maps(self, page, url):
        """
        Scrape Google Maps reviews - hybrid approach combining proven techniques.
        Uses working text extraction with improved review identification.
        """
        logger.info(f"Scraping Google Maps reviews: {url}")
        
        try:
            # Step 1: Navigate
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            
            # Step 2: Handle consent
            try:
                consent_button = page.locator('button:has-text("Accept all"), button:has-text("全部接受")')
                await consent_button.first.click(timeout=3000)
                logger.info("Clicked consent")
                await page.wait_for_timeout(1000)
            except:
                pass
            
            # Step 3: Try to click Reviews tab
            try:
                review_button = page.locator('button:has-text("評論"), button:has-text("Reviews"), button[aria-label*="Reviews"], button[aria-label*="評論"]')
                if await review_button.count() > 0:
                    await review_button.first.click(timeout=5000)
                    logger.info("Clicked Reviews tab")
                    await page.wait_for_timeout(2000)
            except:
                logger.info("Could not click Reviews tab or already on reviews")
            
            # Step 4: Expand "More reviews" if present
            try:
                more_button = page.locator('button:has-text("更多評論"), button:has-text("More reviews"), button:has-text("所有評論"), button:has-text("All reviews")')
                if await more_button.count() > 0:
                    await more_button.first.click(timeout=3000)
                    logger.info("Clicked 'More reviews'")
                    await page.wait_for_timeout(2000)
            except:
                pass
            
            # Step 5: Find and scroll reviews container
            # Try multiple container selectors
            scrolled = False
            container_selectors = [
                'div[role="feed"]',
                '.m6QErb', 
                'div[aria-label*="評論"]',
                'div[aria-label*="Reviews"]',
                'div.DxyBCb'
            ]
            
            for selector in container_selectors:
                try:
                    container = await page.query_selector(selector)
                    if container:
                        logger.info(f"Found container: {selector}, scrolling...")
                        
                        # Scroll within container
                        for i in range(12):
                            prev_height = await page.evaluate(f'document.querySelector("{selector}").scrollHeight')
                            await page.evaluate(f'document.querySelector("{selector}").scrollTop = document.querySelector("{selector}").scrollHeight')
                            await page.wait_for_timeout(1500)
                            new_height = await page.evaluate(f'document.querySelector("{selector}").scrollHeight')
                            
                            if new_height == prev_height:
                                logger.info(f"Scroll complete at iteration {i+1}")
                                break
                        
                        scrolled = True
                        break
                except Exception as e:
                    continue
            
            if not scrolled:
                # Fallback: page scroll
                logger.info("Using fallback page scroll")
                for _ in range(8):
                    await page.mouse.wheel(0, 3000)
                    await page.wait_for_timeout(1500)
            
            # Step 6: Extract content with improved parsing
            await page.wait_for_timeout(1000)
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            # Try to extract individual reviews with common selectors
            reviews_text = []
            
            # Look for review text elements
            text_selectors = [
                ('span', {'class': re.compile(r'wiI7pd|MyEned', re.I)}),
                ('div', {'class': re.compile(r'.*review.*text', re.I)}),
                ('span', {'class': re.compile(r'.*review.*', re.I)}),
            ]
            
            for tag, attrs in text_selectors:
                elements = soup.find_all(tag, attrs)
                if elements:
                    logger.info(f"Found {len(elements)} elements with {tag} {attrs}")
                    for elem in elements[:30]:  # Limit to 30
                        text = elem.get_text(strip=True, separator=' ')
                        # Filter: must be substantial text (> 20 chars) and not menu items
                        if (len(text) > 20 and 
                            not text in ['搜尋', 'Google', '地圖', 'Maps', '路線', 'Directions'] and
                            not text.startswith('http')):
                            reviews_text.append(text)
                    if reviews_text:
                        break
            
            # If structured extraction worked, format nicely
            if reviews_text:
                formatted = '\n\n---評論---\n\n'.join(reviews_text)
                logger.info(f"Extracted {len(reviews_text)} reviews via selectors, {len(formatted)} chars")
                
                # Save debug screenshot
                try:
                    await page.screenshot(path="scraper_debug.png")
                except:
                    pass
                
                return formatted
            
            # Fallback: extract from feed or all text
            logger.info("Using fallback text extraction")
            feed = soup.find('div', role='feed')
            if feed:
                text = feed.get_text(separator='\n', strip=True)
                if len(text) > 100:
                    logger.info(f"Extracted {len(text)} chars from feed")
                    return text
            
            # Last resort: clean all visible text
            for tag in soup(['script', 'style', 'meta', 'link']):
                tag.decompose()
            
            text = soup.get_text(separator='\n', strip=True)
            lines = [line for line in text.splitlines() if line.strip() and len(line) > 10]
            
            # Filter out common navigation items
            filtered = [
                line for line in lines 
                if not any(word in line for word in ['搜尋', 'Google 應用程式', '收合側邊面板', '顯示你的位置'])
            ]
            
            result = '\n'.join(filtered[:200])  # Limit lines
            logger.info(f"Fallback extraction: {len(result)} chars")
            
            # Save debug screenshot
            try:
                await page.screenshot(path="scraper_debug.png")
            except:
                pass
            
            return result
            
        except Exception as e:
            logger.error(f"Google Maps scraping error: {e}")
            import traceback
            traceback.print_exc()
            return ""
