import os
import re
import math
import time
import yaml
import argparse
import logging
from datetime import datetime

import requests
from bs4 import BeautifulSoup
import pandas as pd

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
from selenium.webdriver.chrome.options import Options as ChromeOptions

# --- Configuración de Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Funciones de Utilidad ---
def load_config(config_path):
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        logger.info(f"Configuración cargada desde '{config_path}'")
        return config
    except FileNotFoundError:
        logger.error(f"Archivo de configuración '{config_path}' no encontrado.")
        exit(1)
    except yaml.YAMLError as e:
        logger.error(f"Archivo YAML no válido: {e}")
        exit(1)
    except Exception as e:
        logger.error(f"Error inesperado al cargar la configuración: {e}")
        exit(1)

def filter_job_by_title(title, config_filters):
    title_lower = title.lower()
    exclude_keywords = config_filters.get('exclude_title_keywords', [])
    include_keywords = config_filters.get('include_title_keywords', [])
    
    for ex_word in exclude_keywords:
        if ex_word in title_lower:
            return False, "excluded_explicit", ex_word
            
    if not include_keywords:
        return True, "included", None
        
    for inc_word in include_keywords:
        if inc_word in title_lower:
            return True, "included", inc_word
            
    return False, "excluded_implicit", None

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

# --- Scraping: LinkedIn ---
def get_total_results_linkedin(driver, config_platform):
    try:
        # Busca el subtítulo que ahora usa clases diferentes o la clase de texto de resultados
        subtitle_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//*[contains(@class, 'jobs-search-results-list__text') or contains(@class, 'jobs-search-results-list__subtitle')]"))
        )
        # Limpiamos el texto de comas y el signo '+' (ej. "4,000+ results")
        clean_text = subtitle_element.text.replace(',', '').replace('+', '')
        match = re.search(r'(\d+)', clean_text)
        if match:
            total = int(match.group(1))
            limit = config_platform['max_pages'] * config_platform['page_increment']
            if total > limit: return limit
            return total
        return 0
    except TimeoutException:
        try:
            driver.find_element(By.CSS_SELECTOR, "main[class*='scaffold-layout__list'] div[data-job-id]")
            return config_platform['page_increment']
        except NoSuchElementException:
            return 0

def parse_job_card_linkedin_from_div(job_div):
    job_id = job_div.get('data-job-id')
    if not job_id: return None

    # --- Extraer Título ---
    title = "No especificado"
    title_link = job_div.find('a', class_=lambda x: x and 'job-card-list__title--link' in x)
    
    if title_link:
        # En la nueva UI, el título real suele estar dentro de un tag <strong>
        strong_tag = title_link.find('strong')
        if strong_tag:
            title = strong_tag.get_text(strip=True)
        else:
            title = title_link.get_text(strip=True)

    # --- Extraer Empresa ---
    company = "No especificado"
    # Evitamos usar la clase generada aleatoriamente (como "QFwixpMG...") y buscamos a su padre estable
    company_div = job_div.find('div', class_=lambda x: x and 'artdeco-entity-lockup__subtitle' in x)
    if company_div:
        company = company_div.get_text(strip=True)

    if title == "No especificado" or company == "No especificado": return None

    return {
        'job_id': str(job_id), 
        'title': title, 
        'company': company, 
        'salary': "No especificado", 
        'link': f"https://www.linkedin.com/jobs/view/{job_id}/"
    }

def scrape_linkedin_for_keyword(driver, keyword, time_param, found_job_ids, config):
    if not driver: return [], {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}
    
    cfg = config['platforms']['linkedin']
    logger.info(f"--- Iniciando LinkedIn para '{keyword}' ---")
    base_url = f"{cfg['base_url'].format(keyword=keyword)}&{cfg['time_param_name']}={time_param}"
    
    page = 1; max_pages = 1
    new_jobs = []; processed_titles = {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}
    wait_long = WebDriverWait(driver, cfg['request_timeout_selenium'])
    wait_short = WebDriverWait(driver, 5)
    
    while True:
        start_index = (page - 1) * cfg['page_increment']
        driver.get(f"{base_url}&start={start_index}" if page > 1 else base_url)
        time.sleep(5)
        close_cookie_popup(driver, wait_short)
        
        if driver.find_elements(By.XPATH, "//*[contains(@class, 'jobs-search-no-results')]"):
            logger.info("LinkedIn: 'Sin resultados' detectado.")
            break
            
        try:
            wait_long.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-job-id]")))
            
            if page == 1:
                total_results = get_total_results_linkedin(driver, cfg)
                max_pages = min(math.ceil(total_results / cfg['page_increment']), cfg['max_pages']) if total_results > 0 else 1
            
            # NUEVO: Hacer scroll en el panel izquierdo para que carguen todos los resultados de la página
            try:
                pane = driver.find_element(By.CSS_SELECTOR, "div.jobs-search-results-list")
                driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", pane)
                time.sleep(2) # Esperar a que rendericen
            except:
                pass # Si no encuentra el panel, ignora y continúa con lo que hay
                
            job_divs = BeautifulSoup(driver.page_source, 'lxml').find_all('div', attrs={'data-job-id': True})
            if not job_divs: break
                
            found_on_page = 0
            for div in job_divs:
                job_info = parse_job_card_linkedin_from_div(div)
                if not job_info: continue
                
                is_valid, r_type, r_kw = filter_job_by_title(job_info['title'], config['search_filters'])
                if not is_valid:
                    processed_titles[r_type].append(job_info['title'])
                    continue
                    
                if job_info['job_id'] not in found_job_ids:
                    job_info.update({'timestamp_found': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'platform': 'LinkedIn'})
                    new_jobs.append(job_info); found_job_ids.add(job_info['job_id'])
                    processed_titles['included'].append(job_info['title']); found_on_page += 1
                    
            logger.info(f"LinkedIn: Pág {page}/{max_pages}. Nuevas: +{found_on_page}")
            if page >= max_pages: break
            page += 1
            time.sleep(cfg.get('delay_between_pages_selenium', 3))
            
        except TimeoutException:
            logger.error(f"LinkedIn: Timeout en página {page}.")
            break
            
    return new_jobs, processed_titles

# --- Scraping: OCC ---
def get_total_results_occ(soup):
    for selector in [soup.find('div', id='sort-jobs'), soup.find('p', string=re.compile(r'resultados')), soup.find('p', class_='text-sm font-light')]:
        if selector:
            text_element = selector.find_previous_sibling('p') if selector.name == 'div' else selector
            if text_element and 'resultados' in text_element.get_text():
                match = re.search(r'(\d+)', text_element.get_text().replace(',', ''))
                if match: return int(match.group(1))
    return 0

def parse_job_card_occ(card_soup):
    card_id = card_soup.get('id', '')
    match_id = re.search(r'\d+$', card_id)
    if not match_id: return None
    
    title_tag = card_soup.find('h2', class_='text-lg')
    title = title_tag.get_text(strip=True) if title_tag else None
    if not title: return None
    
    salary_tag = card_soup.find('span', class_='font-base')
    salary = salary_tag.get_text(strip=True) if salary_tag else "No especificado"
    
    company = "No especificado"
    company_section = card_soup.find('div', class_='flex flex-row justify-between items-center')
    if company_section:
        company_text = company_section.get_text(strip=True)
        company = "Empresa confidencial" if "Empresa confidencial" in company_text else company_text.split(' ')[0] # Aproximación limpia

    return {'job_id': str(match_id.group(0)), 'title': title, 'company': company, 'salary': salary, 'link': f"https://www.occ.com.mx/empleo/oferta/{match_id.group(0)}/"}

def scrape_occ_for_keyword(keyword, time_param, found_job_ids, config):
    cfg = config['platforms']['occ']
    logger.info(f"--- Iniciando OCC para '{keyword}' ---")
    base_url = f"{cfg['base_url'].format(keyword=keyword)}&{cfg['time_param_name']}={time_param}"
    
    page = 1; max_pages = 1; new_jobs = []
    processed_titles = {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}
    
    while True:
        try:
            url = f"{base_url}&page={page}" if page > 1 else base_url
            response = requests.get(url, headers=config['general']['headers'], timeout=cfg['request_timeout'])
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')
            
            job_cards = soup.find_all('div', id=lambda x: x and x.startswith('jobcard-'))
            if not job_cards: break
            
            if page == 1:
                total_results = get_total_results_occ(soup)
                if total_results > 0 and len(job_cards) > 0:
                    max_pages = min(math.ceil(total_results / len(job_cards)), cfg.get('max_pages', 999))
            
            found_on_page = 0
            for card in job_cards:
                job_info = parse_job_card_occ(card)
                if not job_info: continue
                
                is_valid, r_type, r_kw = filter_job_by_title(job_info['title'], config['search_filters'])
                if not is_valid:
                    processed_titles[r_type].append(job_info['title'])
                    continue
                    
                if job_info['job_id'] not in found_job_ids:
                    job_info.update({'timestamp_found': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'platform': 'OCC'})
                    new_jobs.append(job_info); found_job_ids.add(job_info['job_id'])
                    processed_titles['included'].append(job_info['title']); found_on_page += 1
            
            logger.info(f"OCC: Pág {page}. Nuevas: +{found_on_page}")
            if page >= max_pages: break
            page += 1
            time.sleep(config['timing']['delay_between_keywords'])
            
        except Exception as e:
            logger.error(f"OCC: Error en página {page}: {e}")
            break
            
    return new_jobs, processed_titles

# --- Scraping: Indeed ---
def parse_job_card_indeed(card_soup):
    # Buscar el enlace principal que contiene el ID y el título
    a_tag = card_soup.find('a', class_=lambda x: x and 'jcs-JobTitle' in x)
    if not a_tag: 
        return None
    
    # Obtener el ID del trabajo (data-jk)
    job_id = a_tag.get('data-jk')
    if not job_id: 
        return None
    
    # Obtener el título (Buscamos el span con ID que empieza con jobTitle-)
    title_tag = card_soup.find('span', id=lambda x: x and str(x).startswith('jobTitle-'))
    title = title_tag.get_text(strip=True) if title_tag else a_tag.get_text(strip=True)
    if not title or title == "":
        return None
    
    # Obtener la empresa (usando data-testid que es más estable que las clases)
    company_tag = card_soup.find('span', {'data-testid': 'company-name'})
    company = company_tag.get_text(strip=True) if company_tag else "No especificado"
    
    # Obtener el salario (buscamos cualquier etiqueta que en su data-testid contenga 'salary-snippet-container')
    salary = "No especificado"
    salary_tag = card_soup.find(lambda tag: tag.has_attr('data-testid') and 'salary-snippet-container' in tag['data-testid'])
    if salary_tag:
        salary = salary_tag.get_text(strip=True)
    else:
        # Método alternativo: buscar en el grupo de metadatos el símbolo de moneda ($)
        metadata_group = card_soup.find('div', class_=lambda x: x and 'jobMetaDataGroup' in x)
        if metadata_group:
            for text in metadata_group.stripped_strings:
                if '$' in text:
                    salary = text
                    break

    # Asegúrate de poner el dominio correcto de tu Indeed (mx.indeed.com, es.indeed.com, etc.)
    return {
        'job_id': str(job_id), 
        'title': title, 
        'company': company, 
        'salary': salary, 
        'link': f"https://mx.indeed.com/viewjob?jk={job_id}" 
    }

def scrape_indeed_for_keyword(driver, keyword, time_param, found_job_ids, config):
    if not driver: return [], {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}
    
    cfg = config['platforms']['indeed']
    logger.info(f"--- Iniciando Indeed para '{keyword}' ---")
    base_url = f"{cfg['base_url']}&{cfg['time_param_name']}={time_param}"
    
    page = 1
    new_jobs = []
    processed_titles = {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}
    wait_long = WebDriverWait(driver, cfg['request_timeout_selenium'])
    wait_short = WebDriverWait(driver, 3)
    
    while page <= cfg.get('max_pages', 999):
        start_index = (page - 1) * cfg['page_increment']
        driver.get(base_url.format(keyword=keyword, start=start_index))
        close_cookie_popup(driver, wait_short)
        
        try:
            # Detección de validación anti-bots (Cloudflare)
            if "challenge-platform" in driver.page_source or "Cloudflare" in driver.page_source:
                logger.warning("⚠️ Indeed está mostrando un Captcha/Cloudflare. Resuélvelo manualmente en el navegador.")
                time.sleep(10) # Esperar a que el usuario lo resuelva
            
            # Verificación de "sin resultados"
            if driver.find_elements(By.XPATH, "//*[contains(text(), 'no produjo ningún resultado') or contains(text(), 'did not match any jobs')]"):
                logger.info("Indeed: 'Sin resultados' detectado.")
                break
                
            # Esperar a que cargue el contenedor principal de trabajos
            wait_long.until(EC.presence_of_element_located((By.ID, "mosaic-provider-jobcards")))
            time.sleep(3) # Pausa extra para asegurar que React renderice los items
            
            soup = BeautifulSoup(driver.page_source, 'lxml')
            jobcards_container = soup.find('div', id='mosaic-provider-jobcards')
            
            if not jobcards_container:
                break
            
            # Encontrar el UL genérico dentro del contenedor, sin depender de clases CSS dinámicas
            ul_list = jobcards_container.find('ul')
            
            # Extraer solo los <li> que realmente contienen una tarjeta de trabajo
            job_cards_li = []
            if ul_list:
                for li in ul_list.find_all('li', recursive=False):
                    if li.find('div', class_=lambda x: x and 'cardOutline' in x):
                        job_cards_li.append(li)
            
            if not job_cards_li: 
                break
                
            found_on_page = 0
            for card in job_cards_li:
                job_info = parse_job_card_indeed(card)
                if not job_info: continue
                
                is_valid, r_type, r_kw = filter_job_by_title(job_info['title'], config['search_filters'])
                if not is_valid:
                    processed_titles[r_type].append(job_info['title'])
                    continue
                    
                if job_info['job_id'] not in found_job_ids:
                    job_info.update({'timestamp_found': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'platform': 'Indeed'})
                    new_jobs.append(job_info)
                    found_job_ids.add(job_info['job_id'])
                    processed_titles['included'].append(job_info['title'])
                    found_on_page += 1
            
            logger.info(f"Indeed: Pág {page}. Nuevas: +{found_on_page}")
            
            # Lógica de paginación mejorada
            try:
                next_button = driver.find_element(By.CSS_SELECTOR, "a[data-testid='pagination-page-next']")
                # Si el botón está pero no es clickeable/desactivado (en algunas versiones de UI)
                if "disabled" in next_button.get_attribute("class"):
                    break
            except NoSuchElementException:
                break # No hay botón de siguiente, terminamos
                
            page += 1
            time.sleep(cfg.get('delay_between_pages_selenium', 3))
            
        except TimeoutException:
            logger.error(f"Indeed: Timeout en página {page}. Es posible que la página haya cambiado o te hayan bloqueado.")
            break
        except Exception as e:
            logger.error(f"Indeed: Error en página {page}: {e}")
            break
            
    return new_jobs, processed_titles

# --- Lógica Principal ---
def merge_processed_titles(global_dict, local_dict):
    for key in global_dict:
        global_dict[key].extend(local_dict.get(key, []))

def main(config_path):
    config = load_config(config_path)
    output_filename = config['general']['output_filename']
    final_columns = config['general']['final_columns_to_save']
    
    found_job_ids = set()
    if os.path.exists(output_filename):
        try:
            existing_df = pd.read_csv(output_filename)
            if 'job_id' in existing_df.columns:
                existing_df['job_id'] = existing_df['job_id'].astype(str)
                found_job_ids = set(existing_df['job_id'].dropna().tolist())
            logger.info(f"Se cargaron {len(found_job_ids)} IDs existentes.")
        except Exception as e:
            logger.error(f"Error al leer CSV: {e}. Se creará uno nuevo.")
            existing_df = pd.DataFrame(columns=final_columns)
    else:
        existing_df = pd.DataFrame(columns=final_columns)

    driver = None
    if config['platforms']['linkedin']['enabled'] or config['platforms']['indeed']['enabled']:
        driver = setup_driver(config['selenium'])

    logger.info("======= INICIANDO SCRAPING =======")
    all_new_jobs = []
    global_titles = {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}
    
    try:
        keywords = config['search_filters']['search_keywords']
        for i, raw_kw in enumerate(keywords):
            logger.info(f"--- Procesando Keyword {i+1}/{len(keywords)}: '{raw_kw}' ---")
            
            if config['platforms']['occ']['enabled']:
                nj, titles = scrape_occ_for_keyword(raw_kw.replace(' ', '-'), config['platforms']['occ']['default_time_param_value'], found_job_ids, config)
                all_new_jobs.extend(nj); merge_processed_titles(global_titles, titles)
                
            if config['platforms']['indeed']['enabled']:
                nj, titles = scrape_indeed_for_keyword(driver, raw_kw.replace(' ', '+'), config['platforms']['indeed']['default_time_param_value'], found_job_ids, config)
                all_new_jobs.extend(nj); merge_processed_titles(global_titles, titles)
                
            if config['platforms']['linkedin']['enabled']:
                nj, titles = scrape_linkedin_for_keyword(driver, raw_kw.replace(' ', '%20'), config['platforms']['linkedin']['default_time_param_value'], found_job_ids, config)
                all_new_jobs.extend(nj); merge_processed_titles(global_titles, titles)
                
            if i < len(keywords) - 1:
                time.sleep(config['timing']['delay_between_keywords'])
                
    except Exception as e:
        logger.exception(f"Error global inesperado: {e}")

    logger.info("======= PROCESANDO RESULTADOS FINALES =======")
    logger.info(f"Filtros - Incluidos: {len(global_titles['included'])}, Excluidos Explícitos: {len(global_titles['excluded_explicit'])}, Excluidos Implícitos: {len(global_titles['excluded_implicit'])}")
    
    if all_new_jobs:
        new_df = pd.DataFrame(all_new_jobs)
        new_df['job_id'] = new_df['job_id'].astype(str)
        
        combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        combined_df.dropna(subset=['job_id'], inplace=True)
        combined_df = combined_df[combined_df['job_id'] != 'None']
        combined_df.drop_duplicates(subset=['job_id'], keep='first', inplace=True)
        
        for col in final_columns:
            if col not in combined_df.columns: combined_df[col] = pd.NA
                
        combined_df[final_columns].to_csv(output_filename, index=False, encoding='utf-8-sig')
        logger.info(f"Datos combinados guardados en '{output_filename}' ({len(combined_df)} ofertas en total).")
    else:
        logger.info("No se encontraron ofertas nuevas. El archivo existente no se modificó.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraper de trabajos remotos.")
    parser.add_argument("--config", type=str, default="config.yaml")
    args = parser.parse_args()
    main(args.config)