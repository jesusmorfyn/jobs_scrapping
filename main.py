import requests
from bs4 import BeautifulSoup
import time
import math
import re
import pandas as pd
import os
from datetime import datetime, timedelta

# --- Selenium Imports (Solo para Indeed) ---
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
from selenium.webdriver.chrome.options import Options as ChromeOptions

# --- Configuración General ---
OUTPUT_FILENAME = "all_remote_jobs.csv"
# MODIFICADO: Lista para asegurar consistencia al leer/combinar, pero NO es la lista final a guardar
EXPECTED_COLUMNS = ['job_id', 'platform', 'title', 'company', 'salary', 'location', 'posted_date', 'timestamp_found', 'link']

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# --- Configuración Específica ---
BASE_URL_OCC = "https://www.occ.com.mx/empleos/de-{keyword}/tipo-home-office-remoto/?sort=2"
BASE_URL_INDEED = "https://mx.indeed.com/jobs?q={keyword}&l=Remote&sc=0kf%3Aattr%28DSQF7%29%3B&sort=date&start={start}"
INDEED_PAGE_INCREMENT = 10

# --- Palabras a buscar ---
SEARCH_KEYWORDS = [
    "devops", "cloud", "aws", "gcp", "site reliability engineer", "mlops", "platform engineer"
]

# --- Filtros de Título (Comunes) ---
EXCLUDE_TITLE_KEYWORDS = [
    "software", "development", "data", ".net", "python", "quality", "security", "seguridad", "developer",
    "salesforce", "desarroll", "qa", "ruby", "test", "datos", "java", "fullstack", "sap", "hibrido",
    "qlik sense", "qliksense", "híbrido", "híbrida", "hibrida", "oracle"
]
INCLUDE_TITLE_KEYWORDS = [
    "devops", "sre", "cloud", "mlops", "platform engineer", "infrastructure", "systems engineer",
    "site reliability", "ingeniero de sistemas", "ingeniero de plataforma", "nube",
    "automation", "automatización", "ci/cd", "continuous integration", "continuous delivery", "pipeline",
    "aws", "azure", "gcp", "google cloud", "amazon web services", "cloud native",
    "kubernetes", "k8s", "docker", "containerization", "contenedores", "serverless", "serverless computing",
    "orquestación", "virtualización", "terraform", "ansible", "jenkins", "gitlab", "puppet", "chef",
    "openstack", "infrastructure as code", "iac", "configuración como código", "prometheus", "grafana",
    "observability", "observabilidad", "monitoring", "monitorización", "logging", "alerting", "alertas",
    "microservices", "microservicios", "deployment", "despliegue", "release", "escalability", "escalabilidad",
    "resilience", "resiliencia", "devsecops", "dataops", "integración continua", "entrega continua",
    "automated deployment", "pipeline de despliegue", "orquestación de contenedores", "gestión de infraestructura",
    "failover", "disaster recovery", "gitlab"
]

# --- Tiempos ---
DELAY_BETWEEN_KEYWORDS = 10
RETRY_DELAY = 10
REQUEST_TIMEOUT_OCC = 30
REQUEST_TIMEOUT_INDEED = 60

# --- Funciones Selenium (Indeed) ---
# setup_driver y close_cookie_popup (sin cambios)
def setup_driver():
    print("Conectando a la instancia de Chrome en modo depuración remota...")
    chrome_options = ChromeOptions()
    chrome_options.add_experimental_option("debuggerAddress", "localhost:9222")
    try:
        driver = webdriver.Chrome(options=chrome_options)
        print("Conectado a la instancia remota de Chrome.")
        return driver
    except Exception as e:
        print(f"Error al conectar con la instancia remota de Chrome: {e}")
        return None

def close_cookie_popup(driver, wait_short):
    if not driver: return
    try:
        xpath_accept = "//button[contains(translate(., 'ACEPTAR COOKIES', 'aceptar cookies'), 'aceptar cookies') or contains(translate(., 'ACCEPT', 'accept'), 'accept') or contains(translate(., 'ENTENDIDO', 'entendido'), 'entendido')]"
        cookie_button = wait_short.until(EC.element_to_be_clickable((By.XPATH, xpath_accept)))
        cookie_button.click()
        print("Pop-up de cookies cerrado (Indeed).")
        time.sleep(1)
    except TimeoutException:
        pass
    except Exception as e:
        print(f"Error al intentar cerrar pop-up de cookies (Indeed): {e}")

# --- Funciones de Parseo Específicas ---
# get_total_results_occ, parse_job_card_occ, parse_job_card_indeed
# (Sin cambios en estas funciones, siguen extrayendo location y posted_date internamente)
def get_total_results_occ(soup):
    """Intenta extraer el número total de resultados de la página de OCC."""
    try:
        sort_div = soup.find('div', id='sort-jobs')
        if sort_div:
            results_p_specific = sort_div.find_previous_sibling('p', class_='text-sm font-light')
            if results_p_specific and 'resultados' in results_p_specific.get_text():
                match = re.search(r'(\d{1,3}(?:,\d{3})*|\d+)', results_p_specific.get_text().replace(',', ''))
                if match: return int(match.group(1))
        results_p_general = soup.find('p', string=re.compile(r'\d{1,3}(?:,\d{3})*|\d+\s+resultados'))
        if results_p_general:
            match = re.search(r'(\d{1,3}(?:,\d{3})*|\d+)', results_p_general.get_text().replace(',', ''))
            if match: return int(match.group(1))
        results_p_alt = soup.find('p', class_='text-sm font-light')
        if results_p_alt and 'resultados' in results_p_alt.get_text():
             match = re.search(r'(\d{1,3}(?:,\d{3})*|\d+)', results_p_alt.get_text().replace(',', ''))
             if match: return int(match.group(1))
        print("Advertencia (OCC): No se pudo determinar el número total de resultados.")
        return 0
    except Exception as e:
        print(f"Error al obtener total de resultados (OCC): {e}")
        return 0

def parse_job_card_occ(card_soup):
    """Extrae info de una tarjeta OCC."""
    job_data = {}
    job_id_num = None
    try:
        card_id = card_soup.get('id')
        if card_id and card_id.startswith('jobcard-'):
             match_id = re.search(r'\d+$', card_id)
             if match_id: job_data['job_id'] = str(match_id.group(0))
             else: job_data['job_id'] = None
        else: job_data['job_id'] = None

        title_tag = card_soup.find('h2', class_='text-lg')
        job_data['title'] = title_tag.get_text(strip=True) if title_tag else None

        salary_tag = card_soup.find('span', class_='font-base')
        job_data['salary'] = salary_tag.get_text(strip=True) if salary_tag else "No especificado"

        company_section = card_soup.find('div', class_='flex flex-row justify-between items-center')
        job_data['company'] = "No especificado" # Default
        # job_data['location'] = "No especificado" # Default - Comentado, no se guarda
        if company_section:
            company_container_outer = company_section.find('div', class_='flex flex-col')
            if company_container_outer:
                 company_container_inner = company_container_outer.find('div', class_='h-[21px]')
                 target_container = company_container_inner if company_container_inner else company_container_outer
                 company_span_or_link = target_container.find('span', class_='line-clamp-1')
                 if company_span_or_link:
                     company_link = company_span_or_link.find('a')
                     if company_link: job_data['company'] = company_link.get_text(strip=True)
                     else:
                         inner_span = company_span_or_link.find('span')
                         if inner_span and "Empresa confidencial" in inner_span.get_text(strip=True): job_data['company'] = "Empresa confidencial"
                         elif inner_span: job_data['company'] = inner_span.get_text(strip=True) or "No especificado"
                         else: job_data['company'] = company_span_or_link.get_text(strip=True) or "No especificado"
                 else:
                     company_link = target_container.find('a')
                     if company_link: job_data['company'] = company_link.get_text(strip=True)
                     else:
                        inner_span = target_container.find('span')
                        if inner_span and "Empresa confidencial" in inner_span.get_text(strip=True): job_data['company'] = "Empresa confidencial"
                        elif inner_span: job_data['company'] = inner_span.get_text(strip=True) or "No especificado"

                 # location_tag = target_container.find_next_sibling('div', class_='no-alter-loc-text') # Comentado
                 # if not location_tag: location_tag = company_container_outer.find('div', class_='no-alter-loc-text')
                 # if location_tag:
                 #     location_parts = [elem.get_text(strip=True) for elem in location_tag.find_all(['span', 'a']) if elem.get_text(strip=True)]
                 #     job_data['location'] = ', '.join(filter(None, location_parts)) if location_parts else "Remoto/No especificado"
                 # else: job_data['location'] = "Remoto/No especificado"

        # date_tag = card_soup.find('label', class_='text-sm') # Comentado
        # job_data['posted_date'] = date_tag.get_text(strip=True) if date_tag else None

        if job_data.get('job_id'): job_data['link'] = f"https://www.occ.com.mx/empleo/oferta/{job_data['job_id']}/"
        else: job_data['link'] = "No encontrado (sin ID)"

        return job_data if job_data.get('title') and job_data.get('job_id') else None
    except Exception as e:
        print(f"Error procesando tarjeta OCC: {e}")
        card_id_debug = card_soup.get('id', 'ID no encontrado')
        print(f"  Tarjeta OCC con ID (aprox): {card_id_debug}")
        return None

def parse_job_card_indeed(card_soup):
    """Extrae info de una tarjeta Indeed."""
    job_data = {}
    job_id = None
    try:
        main_div = card_soup.find('div', class_='cardOutline')
        a_tag = card_soup.find('a', class_='jcs-JobTitle')
        if main_div and main_div.get('data-jk'): job_id = main_div.get('data-jk')
        elif a_tag and a_tag.get('data-jk'): job_id = a_tag.get('data-jk')
        if not job_id: return None
        job_data['job_id'] = str(job_id)

        title_tag = card_soup.find('span', id=lambda x: x and x.startswith('jobTitle-'))
        if title_tag: job_data['title'] = title_tag.get_text(strip=True)
        else:
             h2_title = card_soup.find('h2', class_='jobTitle')
             span_inside = h2_title.find('span') if h2_title else None
             job_data['title'] = span_inside.get_text(strip=True) if span_inside else "No especificado"

        company_tag = card_soup.find('span', {'data-testid': 'company-name'})
        job_data['company'] = company_tag.get_text(strip=True) if company_tag else "No especificado"

        # location_tag = card_soup.find('div', {'data-testid': 'text-location'}) # Comentado
        # job_data['location'] = location_tag.get_text(strip=True) if location_tag else "No especificado"

        salary_data = "No especificado"
        salary_tag_testid = card_soup.find('div', {'data-testid': 'attribute_snippet_testid'}, class_='salary-snippet-container')
        if salary_tag_testid: salary_data = salary_tag_testid.get_text(strip=True)
        else:
            metadata_container = card_soup.find('div', class_='jobMetaDataGroup')
            if metadata_container:
                 possible_salaries = metadata_container.find_all('div')
                 for div in possible_salaries:
                     text = div.get_text(strip=True).lower()
                     if '$' in text and ('mes' in text or 'año' in text or 'hora' in text or 'year' in text or 'month' in text or 'hour' in text):
                          salary_data = div.get_text(strip=True); break
        job_data['salary'] = salary_data

        # posted_date_data = "No encontrado" # Comentado
        # date_tag_relative = card_soup.find('span', class_='date')
        # if date_tag_relative: posted_date_data = date_tag_relative.get_text(strip=True)
        # else:
        #     metadata_container_date = card_soup.find('div', class_='jobMetaDataGroup')
        #     if metadata_container_date:
        #         possible_dates = metadata_container_date.find_all(['span', 'div'])
        #         for tag in possible_dates:
        #              text = tag.get_text(strip=True).lower()
        #              if re.search(r'\b(hace|posted|publicado)\b.*\b(d[íi]a|hora|semana|day|hour|week)s?\b', text, re.IGNORECASE) or \
        #                 re.match(r'\d+\+?\s+(d[íi]as?|days?)\s+ago', text, re.IGNORECASE) or \
        #                 re.search(r'\b(today|ayer)\b', text, re.IGNORECASE):
        #                   posted_date_data = tag.get_text(strip=True); break
        # job_data['posted_date'] = posted_date_data

        job_data['link'] = f"https://mx.indeed.com/viewjob?jk={job_id}"

        return job_data if job_data.get('job_id') and job_data.get('title') != "No especificado" else None
    except Exception as e:
        print(f"Error procesando tarjeta Indeed: {e}")
        error_id = 'N/A'
        try:
            if not job_id:
                a_tag_err = card_soup.find('a', class_='jcs-JobTitle')
                if a_tag_err: error_id = a_tag_err.get('data-jk', 'N/A')
        except: pass
        print(f"  Tarjeta Indeed con ID (aprox): {job_id or error_id}")
        return None

# --- Funciones Principales de Scraping ---
# (scrape_occ_for_keyword y scrape_indeed_for_keyword sin cambios,
#  ya que los cambios se hacen en el parseo y al guardar)
def scrape_occ_for_keyword(keyword, tm_param, found_job_ids):
    """Busca en OCC para una keyword y rango de tiempo dados."""
    print(f"\n--- Iniciando OCC para '{keyword}' (tm={tm_param}) ---")
    base_url_with_tm = f"{BASE_URL_OCC.format(keyword=keyword)}&tm={tm_param}"
    page = 1
    max_pages = 1
    actual_jobs_per_page = 0
    new_jobs_occ = []
    processed_titles = {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}
    skipped_excluded_title_total = 0
    skipped_inclusion_fail_total = 0
    total_added = 0

    while True:
        current_url = f"{base_url_with_tm}&page={page}" if page > 1 else base_url_with_tm
        print(f"  OCC - Página {page}{' de '+str(max_pages) if max_pages > 1 else ''}...")

        try:
            response = requests.get(current_url, headers=HEADERS, timeout=REQUEST_TIMEOUT_OCC)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')
            job_cards = soup.find_all('div', id=lambda x: x and x.startswith('jobcard-'))
            current_page_job_count = len(job_cards)

            if page == 1:
                actual_jobs_per_page = current_page_job_count
                if actual_jobs_per_page > 0:
                    total_results = get_total_results_occ(soup)
                    if total_results > 0:
                        max_pages = math.ceil(total_results / actual_jobs_per_page)
                        print(f"    OCC: {total_results} resultados, {actual_jobs_per_page}/pág, {max_pages} pág. estimadas")
                    else: max_pages = 1
                else:
                    print(f"    OCC: No se encontraron ofertas en la primera página.")
                    break # No hay nada que hacer para esta keyword en OCC

            if not job_cards and page > 1:
                print(f"    OCC: No se encontraron más ofertas en la página {page}.")
                break

            found_on_page, skipped_duplicates_page, skipped_excluded_page, skipped_inclusion_page = 0, 0, 0, 0

            for card in job_cards:
                job_info = parse_job_card_occ(card) # <<< USA LA FUNCIÓN DE PARSEO ACTUALIZADA
                if job_info:
                    job_id = job_info.get('job_id')
                    job_title = job_info.get('title', '')
                    job_title_lower = job_title.lower()

                    excluded = any(ex_word in job_title_lower for ex_word in EXCLUDE_TITLE_KEYWORDS)
                    if excluded:
                        reason = next((ex_word for ex_word in EXCLUDE_TITLE_KEYWORDS if ex_word in job_title_lower), "?")
                        processed_titles['excluded_explicit'].append(f"{job_title} (Excl: {reason})")
                        skipped_excluded_page += 1
                        continue

                    included = not INCLUDE_TITLE_KEYWORDS or any(inc_word in job_title_lower for inc_word in INCLUDE_TITLE_KEYWORDS)
                    if not included:
                        processed_titles['excluded_implicit'].append(job_title)
                        skipped_inclusion_page += 1
                        continue

                    if included and job_id and job_id not in found_job_ids:
                        timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        job_info['timestamp_found'] = timestamp_str
                        job_info['platform'] = 'OCC'
                        new_jobs_occ.append(job_info)
                        found_job_ids.add(job_id)
                        found_on_page += 1
                        processed_titles['included'].append(job_title)
                    elif included and job_id:
                        skipped_duplicates_page += 1

            print(f"    OCC: +{found_on_page} nuevas, {skipped_excluded_page} excluidas, {skipped_inclusion_page} no incluidas, {skipped_duplicates_page} duplicadas.")
            skipped_excluded_title_total += skipped_excluded_page
            skipped_inclusion_fail_total += skipped_inclusion_page
            total_added += found_on_page

            if page >= max_pages: break
            page += 1
            time.sleep(DELAY_BETWEEN_KEYWORDS) # Usamos el delay entre keywords como delay entre páginas aquí

        except requests.exceptions.Timeout:
             print(f"    OCC: Timeout en página {page}. Reintentando...")
             time.sleep(RETRY_DELAY)
             continue
        except requests.exceptions.RequestException as e:
            print(f"    OCC: Error Red/HTTP en página {page}: {e}. Abortando OCC para '{keyword}'.")
            break
        except Exception as e:
            print(f"    OCC: Error general en página {page}: {e}. Abortando OCC para '{keyword}'.")
            break

    print(f"--- Fin OCC para '{keyword}'. Total nuevas: {total_added} ---")
    return new_jobs_occ, processed_titles

def scrape_indeed_for_keyword(driver, keyword, fromage_param, found_job_ids):
    """Busca en Indeed usando Selenium para una keyword y rango de tiempo."""
    if not driver:
        print(f"\n--- Skipping Indeed para '{keyword}' (Driver no disponible) ---")
        return [], {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}

    print(f"\n--- Iniciando Indeed para '{keyword}' (fromage={fromage_param}) ---")
    base_url_with_fromage = f"{BASE_URL_INDEED}&fromage={fromage_param}"
    page = 1
    new_jobs_indeed = []
    processed_titles = {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}
    skipped_excluded_title_total = 0
    skipped_inclusion_fail_total = 0
    total_added = 0
    keep_paging = True
    wait_long = WebDriverWait(driver, REQUEST_TIMEOUT_INDEED)
    wait_short = WebDriverWait(driver, 3)

    while keep_paging:
        start_index = (page - 1) * INDEED_PAGE_INCREMENT
        current_url = base_url_with_fromage.format(keyword=keyword, start=start_index)
        print(f"  Indeed - Página {page} (start={start_index})...")

        try:
            driver.get(current_url)
            close_cookie_popup(driver, wait_short)

            try: # Chequeo rápido sin resultados
                no_results_xpath = "//*[contains(text(), 'no produjo ningún resultado') or contains(text(), 'did not match any jobs')]"
                WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.XPATH, "//*")))
                if driver.find_elements(By.XPATH, no_results_xpath):
                    print(f"    Indeed: Detectado 'Sin resultados'.")
                    break
            except TimeoutException: pass
            except Exception as e_nores: print(f"    Indeed: Advertencia menor buscando 'sin resultados': {e_nores}")

            try: # Espera principal
                wait_long.until(EC.presence_of_element_located((By.ID, "mosaic-provider-jobcards")))
                wait_long.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "div#mosaic-provider-jobcards li div.cardOutline")))
                time.sleep(2)
            except TimeoutException:
                print(f"    Indeed: Timeout esperando tarjetas en página {page}.")
                try: driver.save_screenshot(f"debug_indeed_timeout_p{page}_{keyword}.png")
                except: pass
                if page == 1: print(f"    Indeed: Error cargando resultados iniciales. Abortando Indeed para '{keyword}'.")
                else: print(f"    Indeed: Asumiendo fin de resultados.")
                keep_paging = False; continue
            except Exception as e_wait:
                 print(f"    Indeed: Error esperando elementos en página {page}: {e_wait}. Abortando Indeed para '{keyword}'.")
                 keep_paging = False; continue

            page_html = driver.page_source
            soup = BeautifulSoup(page_html, 'lxml')
            job_list_container_soup = soup.find('div', id='mosaic-provider-jobcards')
            job_cards_li = []
            if job_list_container_soup:
                ul_list = job_list_container_soup.find('ul', class_='css-1faftfv') or job_list_container_soup.find('ul')
                if ul_list: job_cards_li = [li for li in ul_list.find_all('li', recursive=False) if li.find('div', class_='cardOutline')]
            else: print("    Indeed: Advertencia - Contenedor de tarjetas no encontrado en HTML.")

            found_on_page, skipped_duplicates_page, skipped_excluded_page, skipped_inclusion_page = 0, 0, 0, 0

            for card_li in job_cards_li:
                 job_info = parse_job_card_indeed(card_li) # <<< USA LA FUNCIÓN DE PARSEO ACTUALIZADA
                 if job_info:
                    job_id = job_info.get('job_id')
                    job_title = job_info.get('title', '')
                    job_title_lower = job_title.lower()

                    excluded = any(ex_word in job_title_lower for ex_word in EXCLUDE_TITLE_KEYWORDS)
                    if excluded:
                        reason = next((ex_word for ex_word in EXCLUDE_TITLE_KEYWORDS if ex_word in job_title_lower), "?")
                        processed_titles['excluded_explicit'].append(f"{job_title} (Excl: {reason})")
                        skipped_excluded_page += 1
                        continue

                    included = not INCLUDE_TITLE_KEYWORDS or any(inc_word in job_title_lower for inc_word in INCLUDE_TITLE_KEYWORDS)
                    if not included:
                        processed_titles['excluded_implicit'].append(job_title)
                        skipped_inclusion_page += 1
                        continue

                    if included and job_id and job_id not in found_job_ids:
                        timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        job_info['timestamp_found'] = timestamp_str
                        job_info['platform'] = 'Indeed'
                        new_jobs_indeed.append(job_info)
                        found_job_ids.add(job_id)
                        found_on_page += 1
                        processed_titles['included'].append(job_title)
                    elif included and job_id:
                        skipped_duplicates_page += 1

            print(f"    Indeed: +{found_on_page} nuevas, {skipped_excluded_page} excluidas, {skipped_inclusion_page} no incluidas, {skipped_duplicates_page} duplicadas.")
            skipped_excluded_title_total += skipped_excluded_page
            skipped_inclusion_fail_total += skipped_inclusion_page
            total_added += found_on_page

            try: # Comprobar paginación
                if not driver.find_elements(By.CSS_SELECTOR, "a[data-testid='pagination-page-next']"):
                     print(f"    Indeed: No se encontró enlace 'Siguiente'. Fin para '{keyword}'.")
                     keep_paging = False
            except Exception as e_nav:
                 print(f"    Indeed: Error buscando paginación: {e_nav}. Abortando Indeed para '{keyword}'.")
                 keep_paging = False

            if keep_paging:
                 page += 1
                 time.sleep(DELAY_BETWEEN_KEYWORDS) # Usamos el delay entre keywords como delay entre páginas

        except TimeoutException:
             print(f"    Indeed: Timeout general en página {page}. Abortando Indeed para '{keyword}'.")
             keep_paging = False
        except WebDriverException as e:
             print(f"    Indeed: Error de WebDriver en página {page}: {e}. Abortando Indeed para '{keyword}'.")
             keep_paging = False; raise e
        except Exception as e:
            print(f"    Indeed: Error general en página {page}: {e}. Abortando Indeed para '{keyword}'.")
            keep_paging = False

    print(f"--- Fin Indeed para '{keyword}'. Total nuevas: {total_added} ---")
    return new_jobs_indeed, processed_titles


# --- Script Principal ---

# 1. Cargar datos existentes y determinar fecha
# ... (Sin cambios en esta sección) ...
existing_df = pd.DataFrame()
found_job_ids = set()
last_run_time = None

if os.path.exists(OUTPUT_FILENAME):
    print(f"Cargando datos existentes desde '{OUTPUT_FILENAME}'...")
    try:
        existing_df = pd.read_csv(OUTPUT_FILENAME)
        # Usar EXPECTED_COLUMNS para asegurar compatibilidad con archivos viejos
        for col in EXPECTED_COLUMNS:
            if col not in existing_df.columns:
                existing_df[col] = pd.NA
        if 'job_id' in existing_df.columns:
            existing_df['job_id'] = existing_df['job_id'].astype(str)
            found_job_ids = set(existing_df['job_id'].dropna().tolist())
            print(f"Se cargaron {len(found_job_ids)} IDs existentes.")
        else:
            print("Advertencia: El archivo CSV existente no tiene columna 'job_id'.")
            existing_df['job_id'] = pd.Series(dtype='str')

        if 'timestamp_found' in existing_df.columns and not existing_df['timestamp_found'].isnull().all():
            try:
                valid_timestamps = pd.to_datetime(existing_df['timestamp_found'], errors='coerce').dropna()
                if not valid_timestamps.empty:
                    last_run_time = valid_timestamps.max()
                    print(f"Último registro encontrado en CSV: {last_run_time}")
            except Exception as e_ts:
                print(f"Advertencia: Error al procesar timestamps del CSV: {e_ts}")
                last_run_time = None
    except pd.errors.EmptyDataError:
        print("El archivo CSV existente está vacío.")
        existing_df = pd.DataFrame(columns=EXPECTED_COLUMNS) # Usar la lista completa aquí
    except Exception as e:
        print(f"Error al leer el archivo CSV existente: {e}. Se procederá como si no existiera.")
        existing_df = pd.DataFrame(columns=EXPECTED_COLUMNS) # Usar la lista completa aquí
        found_job_ids = set()
else:
    print(f"El archivo '{OUTPUT_FILENAME}' no existe. Se creará uno nuevo.")
    existing_df = pd.DataFrame(columns=EXPECTED_COLUMNS) # Usar la lista completa aquí

# Calcular parámetros de fecha
tm_param_occ = 14
fromage_param_indeed = 14
if last_run_time:
    time_diff = datetime.now() - last_run_time
    days_diff = time_diff.days
    print(f"Última ejecución (según CSV) detectada hace {days_diff} días.")
    if days_diff <= 2: tm_param_occ = 3
    elif days_diff <= 7: tm_param_occ = 7
    if days_diff <= 1: fromage_param_indeed = 1
    elif days_diff <= 3: fromage_param_indeed = 3
    elif days_diff <= 7: fromage_param_indeed = 7
else: print("No se encontró fecha de última ejecución en CSV. Usando defaults (14 días).")
print(f"Parámetros de búsqueda: tm={tm_param_occ} (OCC), fromage={fromage_param_indeed} (Indeed)")

# Inicializar listas y contadores globales
all_new_jobs = []
all_processed_titles = {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}

# Inicializar Driver para Indeed
driver = setup_driver()

print("\n======= INICIANDO SCRAPING COMBINADO =======")

# Bucle Principal por Keyword
try:
    for i, keyword_raw in enumerate(SEARCH_KEYWORDS):
        print(f"\n==================== Keyword {i+1}/{len(SEARCH_KEYWORDS)}: '{keyword_raw}' ====================")
        keyword_occ = keyword_raw.replace(' ', '-')
        keyword_indeed = keyword_raw.replace(' ', '+')

        new_jobs_occ, titles_occ = scrape_occ_for_keyword(keyword_occ, tm_param_occ, found_job_ids)
        all_new_jobs.extend(new_jobs_occ)
        for key in all_processed_titles: all_processed_titles[key].extend(titles_occ[key])

        new_jobs_indeed, titles_indeed = scrape_indeed_for_keyword(driver, keyword_indeed, fromage_param_indeed, found_job_ids)
        all_new_jobs.extend(new_jobs_indeed)
        for key in all_processed_titles: all_processed_titles[key].extend(titles_indeed[key])

        if i < len(SEARCH_KEYWORDS) - 1:
            print(f"\nEsperando {DELAY_BETWEEN_KEYWORDS} segundos antes de la siguiente keyword...")
            time.sleep(DELAY_BETWEEN_KEYWORDS)

except WebDriverException as e_wd_global:
    print(f"\nERROR CRÍTICO DE WEBDRIVER: {e_wd_global}")
    print("El scraping de Indeed se detuvo. Los resultados de OCC (si hubo) se guardarán.")
except Exception as e_global:
    print(f"\nERROR GLOBAL INESPERADO: {e_global}")
    print("El scraping se detuvo. Se intentará guardar los resultados obtenidos hasta ahora.")
finally:
    if driver:
        print("\nCerrando conexión con WebDriver remoto...")
        print("WebDriver remoto sigue conectado. Ciérralo manualmente si es necesario.")

# --- 3. Combinar y Guardar Resultados ---
print("\n======= PROCESANDO RESULTADOS FINALES (Combinado) =======")
print("\n--- Reporte de Títulos Procesados (Total) ---")
print(f"Total Incluidos: {len(all_processed_titles['included'])}")
print(f"Total Excluidos (explícito): {len(all_processed_titles['excluded_explicit'])}")
print(f"Total Excluidos (implícito): {len(all_processed_titles.get('excluded_implicit', []))}")

if all_new_jobs:
    print(f"\nSe encontraron {len(all_new_jobs)} ofertas nuevas en total durante esta ejecución.")
    new_df = pd.DataFrame(all_new_jobs)
    if 'job_id' not in new_df.columns: new_df['job_id'] = pd.NA

    if not existing_df.empty:
        print(f"Combinando {len(new_df)} nuevos con {len(existing_df)} existentes.")
        # Usar la lista completa para asegurar compatibilidad al combinar
        all_cols = list(set(new_df.columns) | set(existing_df.columns) | set(EXPECTED_COLUMNS))
        new_df = new_df.reindex(columns=all_cols)
        existing_df = existing_df.reindex(columns=all_cols)
        combined_df = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        print("No había datos existentes, guardando solo los nuevos.")
        all_cols = list(set(new_df.columns) | set(EXPECTED_COLUMNS))
        combined_df = new_df.reindex(columns=all_cols)

    initial_rows = len(combined_df)
    if 'job_id' in combined_df.columns:
         combined_df['job_id'] = combined_df['job_id'].astype(str)
         combined_df.dropna(subset=['job_id'], inplace=True)
         combined_df = combined_df[combined_df['job_id'] != 'None']
         combined_df.drop_duplicates(subset=['job_id'], keep='first', inplace=True)
         final_rows = len(combined_df)
         if initial_rows > final_rows:
              print(f"Se eliminaron {initial_rows - final_rows} duplicados durante la combinación final.")
    else:
         print("Advertencia: No se pudo realizar la deduplicación final por falta de columna 'job_id'.")

    try:
        # --- MODIFICADO: Definir aquí las columnas finales a guardar ---
        final_columns_order = ['job_id', 'platform', 'title', 'company', 'salary', 'timestamp_found', 'link']

        # Asegurar que estas columnas finales existan
        for col in final_columns_order:
            if col not in combined_df.columns:
                combined_df[col] = pd.NA # Añadir si falta

        # Seleccionar y reordenar SOLO las columnas finales para guardar
        combined_df_to_save = combined_df[final_columns_order]

        combined_df_to_save.to_csv(OUTPUT_FILENAME, index=False, encoding='utf-8-sig')
        print(f"\nDatos combinados (columnas seleccionadas) guardados exitosamente en '{OUTPUT_FILENAME}' ({len(combined_df_to_save)} ofertas en total).")
        # --- FIN MODIFICADO ---

    except Exception as e:
        print(f"\nError al guardar el archivo CSV final: {e}")

elif not all_new_jobs and not existing_df.empty:
    print("\nNo se encontraron ofertas nuevas en esta ejecución. El archivo existente no se modificará.")
    count_existing = len(existing_df) if existing_df is not None else 0
    print(f"El archivo '{OUTPUT_FILENAME}' contiene {count_existing} ofertas.")
else:
    print("\nNo se encontraron ofertas nuevas y no existía archivo previo.")

print("\n======= FIN DEL SCRIPT =======")