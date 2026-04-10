import time
import argparse
import logging
import threading
import concurrent.futures

from core.config_loader import load_config
from core.logger import setup_logger
from core.filter import merge_processed_titles

from utils.selenium_utils import setup_driver
from utils.docker_utils import SeleniumContainerManager
from storage.csv_handler import CSVHandler

from scrapers.generic import GenericScraper

# Silenciar los logs molestos de reconexión de Selenium cuando matamos el contenedor
logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)
logging.getLogger("selenium.webdriver.remote.remote_connection").setLevel(logging.ERROR)

def scraper_worker(scraper_name, config, keywords, shared_job_ids, shared_results, shared_titles, data_lock):
    logger = logging.getLogger(__name__)
    container_manager = None
    driver = None
    
    try:
        # Aquí pasamos el scraper_name
        container_manager = SeleniumContainerManager(scraper_name=scraper_name, image_name=config['selenium']['image'])
        command_executor_url = container_manager.start()
        
        driver = setup_driver(command_executor_url)
        if not driver:
            raise Exception("No se pudo conectar al driver remoto.")

        scraper = GenericScraper(config, scraper_name, driver)

        for kw in keywords:
            local_job_ids = set(shared_job_ids)
            jobs_encontrados, titulos_procesados = scraper.scrape_keyword(kw, local_job_ids)
            
            with data_lock:
                shared_results.extend(jobs_encontrados)
                merge_processed_titles(shared_titles, titulos_procesados)
                for j in jobs_encontrados:
                    shared_job_ids.add(j.job_id)
            
            time.sleep(config['timing']['delay_between_keywords'])

    except Exception as e:
        # Solo imprimimos el error si NO fue porque apagamos el contenedor a la fuerza
        if "Max retries exceeded" not in str(e) and "Connection refused" not in str(e):
            logger.error(f"[{scraper_name.upper()}] Error crítico: {e}", exc_info=True)
    finally:
        if driver:
            try: driver.quit()
            except: pass
        if container_manager:
            container_manager.stop()

def main(config_path):
    config = load_config(config_path)
    logger = setup_logger()
    
    storage = CSVHandler(config['general']['output_filename'], config['general']['final_columns_to_save'])
    shared_job_ids = storage.get_existing_ids()

    shared_results = []
    shared_titles = {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}
    
    data_lock = threading.Lock()

    scrapers_activos = [k for k, v in config['platforms'].items() if v.get('enabled', False)]
    
    if not scrapers_activos:
        logger.info("No hay plataformas habilitadas en config.yaml.")
        return

    logger.info(f"=== INICIANDO SCRAPING ({len(scrapers_activos)} hilos/contenedores) ===")

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(scrapers_activos))
    try:
        futuros = []
        for name in scrapers_activos:
            futuros.append(executor.submit(
                scraper_worker, 
                name, config, config['search_filters']['search_keywords'], 
                shared_job_ids, shared_results, shared_titles, data_lock
            ))

        for futuro in concurrent.futures.as_completed(futuros):
            futuro.result() 

    except KeyboardInterrupt:
        logger.warning("🛑 Interrupción por teclado (Ctrl+C) detectada. Apagando sistema...")
        executor.shutdown(wait=False, cancel_futures=True)
        # Aquí el script terminará y 'atexit' de docker_utils matará los contenedores de forma limpia.
        return

    logger.info("=== TODOS LOS SCRAPERS TERMINARON ===")
    if shared_results:
        storage.save_jobs([job.__dict__ for job in shared_results])
    else:
        logger.info("No hay nuevas ofertas para guardar.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default="config.yaml")
    args = parser.parse_args()
    main(args.config)