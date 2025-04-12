"""
Medical Web Scraper Agent using LangChain with Automated CAPTCHA Solving
This module provides a specialized agent for scraping medical websites with CAPTCHA bypass.
"""

import os
import time
import json
import random
import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import urljoin
import logging
import base64
import io
from PIL import Image

# Selenium imports for browser automation
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

# Updated imports for Pydantic v2
from pydantic import BaseModel, Field
from langchain.tools import BaseTool, Tool
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain_openai import ChatOpenAI
from langchain.memory import ConversationBufferMemory
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from typing import Optional, List, Dict, Any

# For 2Captcha integration
from twocaptcha import TwoCaptcha

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# List of user agents to rotate
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.59'
]

class WebPage(BaseModel):
    """Information about a web page"""
    url: str = Field(description="URL of the web page")
    content: str = Field(description="HTML content of the page")

class CaptchaSolver:
    """Manages CAPTCHA solving using various services."""
    
    def __init__(self, api_key=None):
        """Initialize with API key for CAPTCHA solving service."""
        self.api_key = api_key or os.environ.get('TWOCAPTCHA_API_KEY')
        if self.api_key:
            self.solver = TwoCaptcha(self.api_key)
        else:
            self.solver = None
            logger.warning("No CAPTCHA API key provided. Automated solving will not work.")
    
    def solve_image_captcha(self, image_data=None, image_url=None):
        """Solve an image-based CAPTCHA."""
        if not self.solver:
            return None
            
        try:
            if image_url:
                # Solve from URL
                result = self.solver.normal(image_url)
                return result.get('code')
            elif image_data:
                # Solve from image data
                result = self.solver.normal(image_data)
                return result.get('code')
            return None
        except Exception as e:
            logger.error(f"Error solving image CAPTCHA: {str(e)}")
            return None
    
    def solve_recaptcha_v2(self, site_key, page_url):
        """Solve a reCAPTCHA v2 challenge."""
        if not self.solver:
            return None
            
        try:
            result = self.solver.recaptcha(
                sitekey=site_key,
                url=page_url
            )
            return result.get('code')
        except Exception as e:
            logger.error(f"Error solving reCAPTCHA: {str(e)}")
            return None
    
    def solve_hcaptcha(self, site_key, page_url):
        """Solve an hCaptcha challenge."""
        if not self.solver:
            return None
            
        try:
            result = self.solver.hcaptcha(
                sitekey=site_key,
                url=page_url
            )
            return result.get('code')
        except Exception as e:
            logger.error(f"Error solving hCaptcha: {str(e)}")
            return None

class BrowserManager:
    """Manages browser sessions for scraping with automated CAPTCHA solving."""
    
    def __init__(self, captcha_solver=None):
        self.driver = None
        self.captcha_solver = captcha_solver
        
    def initialize_browser(self, headless=True):
        """Initialize a Chrome browser instance."""
        try:
            chrome_options = Options()
            if headless:
                chrome_options.add_argument("--headless")
            
            # Add browser options to avoid detection
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument(f"--user-agent={random.choice(USER_AGENTS)}")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option("useAutomationExtension", False)
            
            # Initialize Chrome WebDriver
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Set window size
            self.driver.set_window_size(1920, 1080)
            
            # Execute CDP commands to avoid detection
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                """
            })
            
            logger.info("Browser initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing browser: {str(e)}")
            return False
    
    def close_browser(self):
        """Close the browser instance."""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("Browser closed successfully")
            except Exception as e:
                logger.error(f"Error closing browser: {str(e)}")
    
    def fetch_page_with_browser(self, url):
        """Fetch a page using Selenium browser automation with CAPTCHA solving."""
        if not self.driver:
            success = self.initialize_browser(headless=True)
            if not success:
                return {"url": url, "content": "Failed to initialize browser"}
        
        try:
            logger.info(f"Navigating to {url}")
            self.driver.get(url)
            
            # Random wait to mimic human behavior (between 2 and 5 seconds)
            time.sleep(random.uniform(5, 10))
            
            # Check if CAPTCHA or security challenge is present
            captcha_type = self._detect_captcha_type()
            if captcha_type:
                logger.info(f"Detected {captcha_type} CAPTCHA. Attempting to solve...")
                
                if captcha_type == "recaptcha_v2" and self.captcha_solver:
                    self._solve_recaptcha()
                elif captcha_type == "hcaptcha" and self.captcha_solver:
                    self._solve_hcaptcha()
                elif captcha_type == "image_captcha" and self.captcha_solver:
                    self._solve_image_captcha()
                else:
                    logger.warning(f"Cannot automatically solve {captcha_type} or no solver configured")
            
            # Wait for page to fully load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Scroll down slowly to trigger lazy loading content
            self._scroll_page()
            
            # Get the page content
            page_content = self.driver.page_source
            
            return {"url": url, "content": page_content}
            
        except TimeoutException:
            return {"url": url, "content": "Timeout waiting for page to load"}
        except WebDriverException as e:
            return {"url": url, "content": f"Browser error: {str(e)}"}
        except Exception as e:
            return {"url": url, "content": f"Error fetching {url}: {str(e)}"}
    
    def _detect_captcha_type(self):
        """Detect the type of CAPTCHA present on the page."""
        try:
            # Check for reCAPTCHA v2
            if len(self.driver.find_elements(By.CSS_SELECTOR, ".g-recaptcha")) > 0:
                return "recaptcha_v2"
                
            # Check for hCaptcha
            if len(self.driver.find_elements(By.CSS_SELECTOR, ".h-captcha")) > 0:
                return "hcaptcha"
            
            # Check for common image captcha elements
            image_captcha_selectors = [
                "img[id*='captcha']", 
                "img[src*='captcha']",
                "input[id*='captcha']"
            ]
            
            for selector in image_captcha_selectors:
                if len(self.driver.find_elements(By.CSS_SELECTOR, selector)) > 0:
                    return "image_captcha"
            
            # Other security challenge indicators
            security_indicators = [
                "//div[contains(@class, 'security-check')]",
                "//h1[contains(text(), 'Security')]",
                "//title[contains(text(), 'Security')]",
                "//div[contains(text(), 'checking your browser')]"
            ]
            
            for indicator in security_indicators:
                if len(self.driver.find_elements(By.XPATH, indicator)) > 0:
                    return "security_challenge"
            
            return None
        except Exception as e:
            logger.error(f"Error detecting CAPTCHA: {str(e)}")
            return None
    
    def _solve_recaptcha(self):
        """Solve reCAPTCHA using 2Captcha service."""
        try:
            # Find the sitekey
            site_key = self.driver.execute_script("""
                return document.querySelector('.g-recaptcha').getAttribute('data-sitekey')
            """)
            
            if not site_key:
                logger.warning("Could not find reCAPTCHA site key")
                return False
                
            # Get the current URL
            page_url = self.driver.current_url
            
            # Solve the reCAPTCHA
            token = self.captcha_solver.solve_recaptcha_v2(site_key, page_url)
            if not token:
                logger.warning("Failed to solve reCAPTCHA")
                return False
                
            # Insert the token
            self.driver.execute_script(f"""
                document.getElementById('g-recaptcha-response').innerHTML = '{token}';
                
                // Trigger form submission
                let forms = document.getElementsByTagName('form');
                if (forms.length > 0) {{
                    forms[0].submit();
                }}
            """)
            
            # Wait for form submission to complete
            time.sleep(15)
            return True
            
        except Exception as e:
            logger.error(f"Error solving reCAPTCHA: {str(e)}")
            return False
    
    def _solve_hcaptcha(self):
        """Solve hCaptcha using 2Captcha service."""
        try:
            # Find the sitekey
            site_key = self.driver.execute_script("""
                return document.querySelector('.h-captcha').getAttribute('data-sitekey')
            """)
            
            if not site_key:
                logger.warning("Could not find hCaptcha site key")
                return False
                
            # Get the current URL
            page_url = self.driver.current_url
            
            # Solve the hCaptcha
            token = self.captcha_solver.solve_hcaptcha(site_key, page_url)
            if not token:
                logger.warning("Failed to solve hCaptcha")
                return False
                
            # Insert the token
            self.driver.execute_script(f"""
                document.querySelector('[name="h-captcha-response"]').innerHTML = '{token}';
                
                // Trigger form submission
                let forms = document.getElementsByTagName('form');
                if (forms.length > 0) {{
                    forms[0].submit();
                }}
            """)
            
            # Wait for form submission to complete
            time.sleep(15)
            return True
            
        except Exception as e:
            logger.error(f"Error solving hCaptcha: {str(e)}")
            return False
    
    def _solve_image_captcha(self):
        """Solve simple image CAPTCHA using 2Captcha service."""
        try:
            # Find the captcha image
            captcha_img = self.driver.find_element(By.CSS_SELECTOR, "img[id*='captcha'], img[src*='captcha']")
            if not captcha_img:
                logger.warning("Could not find captcha image")
                return False
            
            # Get the image data
            img_src = captcha_img.get_attribute("src")
            
            # If it's a data URL
            if img_src.startswith('data:image'):
                # Extract base64 data
                img_data = img_src.split(',')[1]
                solution = self.captcha_solver.solve_image_captcha(image_data=img_data)
            else:
                # It's a URL
                solution = self.captcha_solver.solve_image_captcha(image_url=img_src)
            
            if not solution:
                logger.warning("Failed to solve image CAPTCHA")
                return False
            
            # Find the input field
            input_field = self.driver.find_element(By.CSS_SELECTOR, "input[id*='captcha']")
            if not input_field:
                logger.warning("Could not find captcha input field")
                return False
            
            # Enter the solution
            input_field.send_keys(solution)
            
            # Find the submit button and click it
            submit_buttons = self.driver.find_elements(By.XPATH, "//button[@type='submit'] | //input[@type='submit']")
            if submit_buttons:
                submit_buttons[0].click()
                time.sleep(3)  # Wait for the form to submit
                return True
            else:
                logger.warning("Could not find submit button")
                return False
            
        except Exception as e:
            logger.error(f"Error solving image CAPTCHA: {str(e)}")
            return False
    
    def _scroll_page(self):
        """Scroll down the page to simulate human behavior and trigger lazy loading."""
        try:
            # Get scroll height
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            
            # Number of scroll steps
            num_steps = random.randint(3, 6)
            
            for i in range(num_steps):
                # Scroll down in steps
                target_height = int(last_height * (i + 1) / num_steps)
                self.driver.execute_script(f"window.scrollTo(0, {target_height});")
                
                # Random wait between scrolls
                time.sleep(random.uniform(0.5, 1.5))
            
            # Scroll back up a bit (like a human would)
            self.driver.execute_script(f"window.scrollTo(0, {int(last_height * 0.8)});")
            time.sleep(random.uniform(0.5, 1.0))
            
        except Exception as e:
            logger.warning(f"Error while scrolling: {str(e)}")

# Create instances of solvers and managers
captcha_solver = CaptchaSolver(api_key=os.environ.get('TWOCAPTCHA_API_KEY'))
browser_manager = BrowserManager(captcha_solver=captcha_solver)

def fetch_webpage(url: str) -> Dict[str, str]:
    """Fetch the web page content with proper handling using both requests and browser automation."""
    try:
        # Try with requests first (faster)
        headers = {
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        # Add delay to respect website's resources (random between 1-3 seconds)
        time.sleep(random.uniform(3, 5))
        
        response = requests.get(url, headers=headers, timeout=10)
        
        # Check if response might contain anti-bot measures
        if response.status_code == 200 and len(response.text) > 500:
            # Check for indicators of anti-bot systems
            indicators = ['captcha', 'security check', 'bot detection', 'challenge']
            if not any(ind in response.text.lower() for ind in indicators):
                return {"url": url, "content": response.text}
        
        # If requests method fails or seems to hit anti-bot, use browser automation
        logger.info(f"Using browser automation for {url}")
        return browser_manager.fetch_page_with_browser(url)
    
    except requests.exceptions.RequestException as e:
        # If requests method fails completely, try browser automation
        logger.warning(f"Request error: {str(e)}. Trying browser automation.")
        return browser_manager.fetch_page_with_browser(url)
    
    except Exception as e:
        return {"url": url, "content": f"Error fetching {url}: {str(e)}"}

def parse_html(html_content: str, selector_type: str = "css", selector: str = None) -> str:
    """Parse HTML and extract data based on provided selectors."""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        if not selector:
            return str(soup)
        
        if selector_type.lower() == "css":
            elements = soup.select(selector)
            return "\n".join([str(element) for element in elements])
        else:
            # Basic representation if not using CSS
            return str(soup)
            
    except Exception as e:
        return f"Error parsing HTML: {str(e)}"

def extract_links(html_content: str, base_url: str, pattern: str = None) -> str:
    """Extract links from HTML content."""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        links = []
        
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            full_url = urljoin(base_url, href)
            
            if pattern is None or pattern in full_url:
                links.append({
                    "text": a_tag.get_text().strip(),
                    "url": full_url
                })
        
        return json.dumps(links, indent=2)
    
    except Exception as e:
        return f"Error extracting links: {str(e)}"

def save_data(data: str, filename: str, format: str = "json") -> str:
    """Save data to file in specified format."""
    try:
        base_filename = filename
        format = format.lower()
        
        if format == "json":
            # Ensure data is valid JSON
            if isinstance(data, str):
                try:
                    json_data = json.loads(data)
                except json.JSONDecodeError:
                    json_data = {"text": data}
            else:
                json_data = data
            
            with open(f"{base_filename}.json", 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            return f"Data saved to {base_filename}.json"
        
        elif format == "csv":
            # Handle CSV saving
            if isinstance(data, str):
                try:
                    # Try to parse as JSON first
                    parsed_data = json.loads(data)
                    df = pd.DataFrame(parsed_data)
                except:
                    # Fallback to simple text saving
                    with open(f"{base_filename}.csv", 'w', encoding='utf-8') as f:
                        f.write(data)
                    return f"Data saved to {base_filename}.csv"
            else:
                df = pd.DataFrame(data)
            
            df.to_csv(f"{base_filename}.csv", index=False)
            return f"Data saved to {base_filename}.csv"
        
        else:
            # Default to text
            with open(f"{base_filename}.txt", 'w', encoding='utf-8') as f:
                f.write(str(data))
            return f"Data saved to {base_filename}.txt"
            
    except Exception as e:
        return f"Error saving data: {str(e)}"
    
# Wrapper function for save_data with structured parameters
def save_data_with_params(data_and_params: str) -> str:
    """Save data to file with parameters specified in JSON string."""
    try:
        # Parse the input JSON
        params = json.loads(data_and_params)
        
        # Extract parameters
        data = params.get("data", "")
        filename = params.get("filename", "output_data")
        format = params.get("format", "json")
        
        # Call the original save_data function
        return save_data(data, filename, format)
        
    except json.JSONDecodeError:
        return "Error: Input must be a valid JSON string with 'data' and 'filename' fields"
    except Exception as e:
        return f"Error saving data: {str(e)}"

def extract_medical_data(html_content: str, data_type: str = "generic") -> str:
    """Extract structured medical data based on the specified type."""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        data = {}
        
        if data_type == "generic":
            # Generic name often in title or header
            title_element = soup.find('h1') or soup.find('title')
            if title_element:
                data["name"] = title_element.get_text().strip()
            
            # Common medical information sections
            for section in ["indications", "dosage", "side-effects", "contraindications"]:
                section_element = soup.find(id=section) or soup.find(class_=section) or soup.find(string=lambda text: section.replace("-", " ") in text.lower() if text else False)
                
                if section_element:
                    # Try to get the content following this section
                    parent = section_element.parent
                    next_elements = parent.find_next_siblings()
                    content = "\n".join([el.get_text().strip() for el in next_elements if el.get_text().strip()])
                    data[section] = content
        
        return json.dumps(data, indent=2)
        
    except Exception as e:
        return f"Error extracting medical data: {str(e)}"

class MedicalWebScraperAgent:
    """Agent that coordinates tools for medical web scraping."""

    def __init__(self, model_name="gpt-4o-mini-2024-07-18"):
        """Initialize the medical web scraper agent with necessary tools."""
        
        # Define tools using the Tool class
        self.tools = [
            Tool(
                name="web_scraper",
                func=fetch_webpage,
                description="Scrapes content from a given URL with proper handling of rate limits and automated CAPTCHA solving"
            ),
            Tool(
                name="html_parser",
                func=parse_html,
                description="Parses HTML content and extracts structured data based on CSS selectors or XPath"
            ),
            Tool(
                name="link_extractor",
                func=extract_links,
                description="Extracts links from HTML content with options to filter by URL patterns"
            ),
            Tool(
                name="data_saver",
                func=save_data_with_params,
                description="""Saves extracted data to files in various formats (JSON, CSV). 
                Requires a JSON string with 'data', 'filename', and optional 'format' fields. 
                Example: {"data": "content to save", "filename": "output_file", "format": "json"}"""
            ),
            Tool(
                name="medical_data_extractor",
                func=extract_medical_data,
                description="Extracts structured medical information like generic names, indications, dosages, etc."
            )
        ]
        
        # Initialize LLM
        self.llm = ChatOpenAI(
            temperature=0,
            model=model_name
        )
        
        # Set up memory
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )
        
        # Create prompt template
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a specialized web scraping agent focused on medical information extraction.
            Your primary goal is to help users obtain structured medical data from websites.
            
            When scraping medical websites:
            1. Understand the structure of the website first
            2. Navigate pagination systematically
            3. Extract links to detailed information pages
            4. For each detailed page, extract structured information
            5. Organize and save the data in a clear format
            
            Always be respectful of websites by:
            - Adding delays between requests
            - Not making excessive requests in short periods
            - Following robots.txt guidelines
            
            For medical data, ensure you extract accurate and complete information about:
            - Generic names and brand names
            - Active ingredients and their amounts
            - Indications and usage guidelines
            - Dosage information for different conditions
            - Side effects and contraindications
            - Manufacturer information when available
            
            You have access to specialized tools for web scraping, HTML parsing, link extraction,
            medical data extraction, and data saving. Use them effectively to complete scraping tasks.
            
            IMPORTANT: The scraper has automated CAPTCHA solving capabilities. When CAPTCHAs are encountered,
            the system will attempt to solve them automatically. If automatic solving fails, notify the user.
            """),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        
        # Create agent
        self.agent = create_openai_functions_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=self.prompt
        )
        
        # Create agent executor
        self.agent_executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            memory=self.memory,
            verbose=True,
            handle_parsing_errors=True
        )
    
    def scrape_medical_site(self, url):
        """Convenience method to scrape a specific medical site."""
        prompt = f"""
        Please scrape comprehensive medical data from {url}.
        
        Extract structured information including:
        - Generic name/title
        - Active ingredients
        - Indications
        - Dosage information
        - Side effects
        - Contraindications
        
        Compile this data into a structured format and save it as JSON.
        """
        return self.agent_executor.invoke({"input": prompt})
        
    def __del__(self):
        """Cleanup method to ensure browser is closed."""
        browser_manager.close_browser()