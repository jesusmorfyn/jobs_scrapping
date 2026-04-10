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

def scraper_worker(scraper_name, config, keywords, shared_job_ids, shared_results, shared_titles, data_lock):
    logger = logging.getLogger(__name__)
    container_manager = None
    driver = None
    
    try:
        # 1. Levantar contenedor efímero exclusivo para este scraper
        container_manager = SeleniumContainerManager(image_name=config['selenium']['image'])
        command_executor_url = container_manager.start()
        
        # 2. Conectar Selenium al contenedor
        driver = setup_driver(command_executor_url)
        if not driver:
            raise Exception("No se pudo conectar al driver remoto.")

        scraper = GenericScraper(config, scraper_name, driver)

        # 3. Scrapear
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
        logger.error(f"[{scraper_name.upper()}] Error crítico: {e}", exc_info=True)
    finally:
        # 4. LIMPIEZA ABSOLUTA (Asegura que nada quede volando)
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

    # LANZAR HILOS (Cada uno levantará su propio contenedor)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(scrapers_activos)) as executor:
        futuros = []
        for name in scrapers_activos:
            futuros.append(executor.submit(
                scraper_worker, 
                name, config, config['search_filters']['search_keywords'], 
                shared_job_ids, shared_results, shared_titles, data_lock
            ))

        for futuro in concurrent.futures.as_completed(futuros):
            futuro.result() 

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