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
    logger.info("Conectando a la instancia de Chrome en modo depuración remota...")
    chrome_options = ChromeOptions()
    chrome_options.add_experimental_option("debuggerAddress", config_selenium['debugger_address'])
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        try:
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        except Exception as e:
            logger.warning(f"No se pudo ocultar webdriver: {e}")
        logger.info("Conectado a la instancia remota de Chrome.")
        return driver
    except WebDriverException as e:
        logger.error(f"Error de WebDriver al conectar: {e}. Asegúrate de usar --remote-debugging-port.")
        return None

def close_cookie_popup(driver, wait_short):
    if not driver: return
    xpath_accept = "//button[contains(@aria-label, 'Accept cookies') or contains(@aria-label,'Aceptar cookies') or contains(text(), 'Accept') or contains(text(), 'Aceptar') or contains(@id, 'onetrust-accept')]"
    try:
        cookie_button = wait_short.until(EC.element_to_be_clickable((By.XPATH, xpath_accept)))
        cookie_button.click()
        logger.info("Pop-up de cookies cerrado.")
        time.sleep(1)
    except TimeoutException:
        pass
    except Exception as e:
        logger.warning(f"Error al cerrar pop-up de cookies: {e}")