import time
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options as ChromeOptions

logger = logging.getLogger(__name__)

def setup_driver(config_selenium):
    logger.info("Conectando a Chrome...")
    chrome_options = ChromeOptions()
    chrome_options.add_experimental_option("debuggerAddress", config_selenium['debugger_address'])
    chrome_options.page_load_strategy = 'eager' # Evita esperar a que carguen analíticas
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        return driver
    except WebDriverException as e:
        logger.error(f"Error de WebDriver: {e}")
        return None

def block_heavy_content(driver):
    """Comando interno para bloquear descarga de imágenes y ahorrar red"""
    try:
        driver.execute_cdp_cmd('Network.setBlockedURLs', {"urls": ["*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp", "*.svg"]})
        driver.execute_cdp_cmd('Network.enable', {})
    except Exception as e:
        pass

def close_cookie_popup(driver, wait_short):
    if not driver: return
    xpath_accept = "//button[contains(@aria-label, 'Accept cookies') or contains(@aria-label,'Aceptar cookies') or contains(text(), 'Accept') or contains(text(), 'Aceptar') or contains(@id, 'onetrust-accept')]"
    try:
        cookie_button = wait_short.until(EC.element_to_be_clickable((By.XPATH, xpath_accept)))
        cookie_button.click()
        time.sleep(1)
    except:
        pass