import os
import json
import time
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options as ChromeOptions

logger = logging.getLogger(__name__)

def setup_driver(command_executor_url):
    """Conecta al contenedor Docker a través de Remote WebDriver con camuflaje."""
    chrome_options = ChromeOptions()
    chrome_options.page_load_strategy = 'eager'
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument("--window-size=1920,1080")
    
    # --- CAPA 1: STEALTH OPTIONS (Ocultar Selenium) ---
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("--start-maximized")

    
    try:
        driver = webdriver.Remote(
            command_executor=command_executor_url,
            options=chrome_options
        )
        return driver
    except Exception as e:
        logger.error(f"Error al conectar con Remote WebDriver: {e}")
        return None

def apply_stealth(driver):
    """CAPA 2: Inyección CDP. Borra las variables de entorno que delatan al bot."""
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.navigator.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['es-MX', 'es', 'en-US', 'en'] });
            """
        })
    except Exception as e:
        logger.warning(f"No se pudo aplicar CDP Stealth: {e}")

def load_cookies(driver, platform_name):
    """CAPA 3: Inyecta las cookies de sesión guardadas en JSON."""
    cookie_path = f"cookies/{platform_name}.json"
    if not os.path.exists(cookie_path):
        return False
        
    try:
        with open(cookie_path, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
            
        count = 0
        for cookie in cookies:
            # Eliminar campos que Selenium no acepta o causan conflicto
            if 'sameSite' in cookie: del cookie['sameSite']
            if 'storeId' in cookie: del cookie['storeId']
            if 'hostOnly' in cookie: del cookie['hostOnly']
            if 'session' in cookie: del cookie['session']
            if 'id' in cookie: del cookie['id']
            
            try:
                driver.add_cookie(cookie)
                count += 1
            except Exception:
                pass # Ignorar si una cookie específica falla
                
        logger.info(f"🍪 Se inyectaron {count} cookies para {platform_name.upper()}.")
        return True
    except Exception as e:
        logger.error(f"Error cargando cookies para {platform_name}: {e}")
        return False

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