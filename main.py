import time
import argparse
import logging
import threading
import concurrent.futures

from core.config_loader import load_config
from core.logger import setup_logger
from core.filter import merge_processed_titles

from utils.selenium_utils import setup_driver
from storage.csv_handler import CSVHandler

from scrapers.occ import OCCScraper
from scrapers.linkedin import LinkedinScraper
from scrapers.indeed import IndeedScraper

logger = logging.getLogger(__name__)

# --- Hilo para Scrapers sin Navegador (OCC, etc) ---
def api_worker(scraper_class, config, keywords, shared_job_ids, shared_results, shared_titles, lock):
    try:
        scraper = scraper_class(config)
        for kw in keywords:
            local_job_ids = set(shared_job_ids)
            jobs_encontrados, titulos_procesados = scraper.scrape_keyword(kw, local_job_ids)
            
            with lock:
                shared_results.extend(jobs_encontrados)
                merge_processed_titles(shared_titles, titulos_procesados)
                for j in jobs_encontrados:
                    shared_job_ids.add(j.job_id)
            
            time.sleep(config['timing']['delay_between_keywords'])
    except Exception as e:
        logger.error(f"Error en API Worker ({scraper_class.__name__}): {e}")

# --- Hilo para Scrapers con Navegador (LinkedIn, Indeed) ---
def selenium_worker(scraper_classes, config, keywords, shared_job_ids, shared_results, shared_titles, lock):
    driver = setup_driver(config['selenium'])
    if not driver:
        logger.error("No se pudo iniciar el navegador. Scrapers de Selenium abortados.")
        return

    try:
        # Ejecuta un scraper web después de otro usando la MISMA conexión
        for scraper_class in scraper_classes:
            scraper = scraper_class(config, driver)
            
            for kw in keywords:
                local_job_ids = set(shared_job_ids)
                jobs_encontrados, titulos_procesados = scraper.scrape_keyword(kw, local_job_ids)
                
                with lock:
                    shared_results.extend(jobs_encontrados)
                    merge_processed_titles(shared_titles, titulos_procesados)
                    for j in jobs_encontrados:
                        shared_job_ids.add(j.job_id)
                
                time.sleep(config['timing']['delay_between_keywords'])
    except Exception as e:
        logger.error(f"Error crítico en Selenium Worker: {e}")
    finally:
        logger.info("Scrapers de Selenium terminados. El navegador se dejará abierto en modo remoto.")
        # Quitamos el driver.close() para evitar desconectar tu Chrome de depuración
        # Puedes cerrar la pestaña manualmente cuando termine.

def main(config_path):
    config = load_config(config_path)
    logger = setup_logger()
    
    # 1. Inicializar Storage
    storage = CSVHandler(config['general']['output_filename'], config['general']['final_columns_to_save'])
    shared_job_ids = storage.get_existing_ids()

    # 2. Variables compartidas
    shared_results = []
    shared_titles = {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}
    data_lock = threading.Lock() 
    keywords = config['search_filters']['search_keywords']

    # 3. Clasificar Scrapers a ejecutar
    api_scrapers = []
    selenium_scrapers = []
    
    if config['platforms']['occ']['enabled']: 
        api_scrapers.append(OCCScraper)
        
    if config['platforms']['indeed']['enabled']: 
        selenium_scrapers.append(IndeedScraper)
        
    if config['platforms']['linkedin']['enabled']: 
        selenium_scrapers.append(LinkedinScraper)

    logger.info("======= INICIANDO SCRAPING HÍBRIDO =======")

    # 4. Lanzar Hilos Concurrentes
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(api_scrapers) + 1) as executor:
        futuros = []
        
        # Lanzar OCC de forma independiente
        for api_class in api_scrapers:
            futuro = executor.submit(
                api_worker, 
                api_class, config, keywords, shared_job_ids, shared_results, shared_titles, data_lock
            )
            futuros.append(futuro)

        # Lanzar LinkedIn e Indeed agrupados en UN SOLO hilo para no saturar Chrome
        if selenium_scrapers:
            futuro_selenium = executor.submit(
                selenium_worker, 
                selenium_scrapers, config, keywords, shared_job_ids, shared_results, shared_titles, data_lock
            )
            futuros.append(futuro_selenium)

        for futuro in concurrent.futures.as_completed(futuros):
            futuro.result()

    # 5. Guardar Resultados Finales
    logger.info("======= TODOS LOS SCRAPERS TERMINARON =======")
    logger.info(f"Filtros - Incluidos: {len(shared_titles['included'])}, Excluidos Explícitos: {len(shared_titles['excluded_explicit'])}, Excluidos Implícitos: {len(shared_titles['excluded_implicit'])}")
    
    if shared_results:
        jobs_dicts = [job.__dict__ for job in shared_results]
        storage.save_jobs(jobs_dicts)
    else:
        logger.info("No se encontraron ofertas nuevas. El archivo existente no se modificó.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraper de trabajos remotos.")
    parser.add_argument("--config", type=str, default="config.yaml")
    args = parser.parse_args()
    main(args.config)