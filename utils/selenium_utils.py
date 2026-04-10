import time
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options as ChromeOptions

logger = logging.getLogger(__name__)

def setup_driver(command_executor_url):
    """Conecta al contenedor Docker a través de Remote WebDriver."""
    chrome_options = ChromeOptions()
    chrome_options.page_load_strategy = 'eager'
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    
    try:
        driver = webdriver.Remote(
            command_executor=command_executor_url,
            options=chrome_options
        )
        return driver
    except Exception as e:
        logger.error(f"Error al conectar con Remote WebDriver: {e}")
        return None

def block_heavy_content(driver):
    try:
        driver.execute_cdp_cmd('Network.setBlockedURLs', {"urls": ["*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp", "*.svg"]})
        driver.execute_cdp_cmd('Network.enable', {})
    except Exception:
        pass

def close_cookie_popup(driver, wait_short):
    if not driver: return
    xpath_accept = "//button[contains(@aria-label, 'Accept cookies') or contains(@aria-label,'Aceptar cookies') or contains(text(), 'Accept') or contains(text(), 'Aceptar') or contains(@id, 'onetrust-accept')]"
    try:
        if not wait_short: wait_short = WebDriverWait(driver, 2)
        cookie_button = wait_short.until(EC.element_to_be_clickable((By.XPATH, xpath_accept)))
        cookie_button.click()
        time.sleep(1)
    except:
        pass