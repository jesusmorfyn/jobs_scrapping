import requests
from bs4 import BeautifulSoup
import time
import math
import re
import pandas as pd
import os
from datetime import datetime
import yaml  # <--- Importar YAML
import argparse

# --- Selenium Imports ---
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
from selenium.webdriver.chrome.options import Options as ChromeOptions

# --- Funciones de Utilidad ---
def load_config(config_path):
    """Carga la configuración desde un archivo YAML."""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            # Usa yaml.safe_load para mayor seguridad
            config = yaml.safe_load(f)
        print(f"Configuración cargada desde '{config_path}'")
        return config
    except FileNotFoundError:
        print(f"Error: Archivo de configuración '{config_path}' no encontrado.")
        exit(1)
    except yaml.YAMLError as e: # <--- Captura errores específicos de YAML
        print(f"Error: Archivo de configuración '{config_path}' no es un YAML válido: {e}")
        exit(1)
    except Exception as e:
        print(f"Error inesperado al cargar la configuración: {e}")
        exit(1)

# ... (El resto de tus funciones: filter_job_by_title, setup_driver, close_cookie_popup,
#      get_total_results_linkedin, parse_job_card_linkedin_from_div,
#      get_total_results_occ, parse_job_card_occ,
#      parse_job_card_indeed,
#      scrape_occ_for_keyword, scrape_linkedin_for_keyword, scrape_indeed_for_keyword,
#      main
#      permanecen IGUALES que en la versión JSON, ya que solo consumen el diccionario `config`)

# --- COPIA AQUÍ TODAS TUS FUNCIONES DE PARSEO Y SCRAPING ---
# (Igual que antes, no las repito por brevedad, pero deben estar aquí)
# get_total_results_linkedin, parse_job_card_linkedin_from_div,
# get_total_results_occ, parse_job_card_occ,
# parse_job_card_indeed
# Ejemplo:
def get_total_results_linkedin(driver, config_platform):
    """Intenta extraer el número total de resultados de LinkedIn buscando el div__subtitle."""
    try:
        subtitle_selector = "div.jobs-search-results-list__subtitle"
        print(f"    get_total_results: Esperando por '{subtitle_selector}'...")
        subtitle_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, subtitle_selector))
        )
        print("    get_total_results: Elemento subtitle encontrado.")
        subtitle_text = subtitle_element.text
        print(f"    get_total_results: Texto encontrado en subtitle: '{subtitle_text}'")
        text_without_commas = subtitle_text.replace(',', '')
        match = re.search(r'(\d+)', text_without_commas)
        if match:
            total = int(match.group(1))
            print(f"    LinkedIn: Total extraído del subtitle: {total}")
            limit = config_platform['max_pages'] * config_platform['page_increment']
            if total > limit:
                 print(f"    Advertencia: LinkedIn reporta {total} resultados, pero solo se pueden ver ~{limit}. Limitando a {limit}.")
                 return limit
            return total
        else:
            print(f"Advertencia (LinkedIn): Patrón numérico no encontrado en texto del subtitle: '{subtitle_text}'")
            return 0
    except TimeoutException:
        print("Advertencia (LinkedIn): Timeout esperando el div subtitle de resultados.")
        try:
            driver.find_element(By.CSS_SELECTOR, "main[class*='scaffold-layout__list'] div[data-job-id]")
            print("    LinkedIn (Fallback): Subtitle no encontrado, pero SÍ hay divs con ID. Asumiendo 1 página.")
            return config_platform['page_increment']
        except NoSuchElementException:
             print("    LinkedIn (Fallback): Ni subtitle ni divs con ID encontrados tras timeout. Asumiendo 0 resultados.")
             return 0
    except Exception as e:
        print(f"Error general al obtener total de resultados (LinkedIn): {e}")
        return 0

def parse_job_card_linkedin_from_div(job_div):
    job_data = {}
    job_id = None
    try:
        job_id = job_div.get('data-job-id')
        if not job_id: return None
        job_data['job_id'] = str(job_id)
        card_container = job_div.find_parent('li')
        if not card_container:
             card_container = job_div.find_parent('div', class_=lambda x: x and 'job-card-container' in x)
             if not card_container:
                   card_container = job_div.find_parent('div', class_=lambda x: x and 'job-posting-card' in x)
        if not card_container: return None

        title_tag_h = card_container.find(['h3', 'h4'], class_=lambda x: x and 'base-search-card__title' in x)
        if title_tag_h: job_data['title'] = title_tag_h.get_text(strip=True)
        else:
            title_link_element = card_container.find('a', class_=lambda x: x and 'job-card-list__title--link' in x)
            if title_link_element:
                strong_tag_in_link = title_link_element.find('strong')
                if strong_tag_in_link and strong_tag_in_link.get_text(strip=True): job_data['title'] = strong_tag_in_link.get_text(strip=True)
                elif title_link_element.get('aria-label'): job_data['title'] = title_link_element.get('aria-label').strip()
                else:
                    visually_hidden_span = title_link_element.find('span', class_='visually-hidden')
                    if visually_hidden_span and visually_hidden_span.get_text(strip=True): job_data['title'] = visually_hidden_span.get_text(strip=True)
                    else: job_data['title'] = "No especificado (estructura interna del link de título no esperada)"
            else:
                title_strong_global = card_container.find('strong')
                if title_strong_global: job_data['title'] = title_strong_global.get_text(strip=True)
                else:
                    first_link_in_card = card_container.find('a')
                    if first_link_in_card:
                        aria_label_generic = first_link_in_card.get('aria-label')
                        if aria_label_generic: job_data['title'] = aria_label_generic.strip()
                        else: job_data['title'] = first_link_in_card.get_text(strip=True)
                    else: job_data['title'] = "No especificado (título no encontrado)"

        company_tag = card_container.find(['a','span'], class_=lambda x: x and ('base-search-card__subtitle' in x or 'job-card-container__primary-description' in x))
        if not company_tag: company_tag = card_container.find('div', class_=lambda x: x and 'artdeco-entity-lockup__subtitle' in x)
        job_data['company'] = company_tag.get_text(strip=True) if company_tag else "No especificado"
        job_data['salary'] = "No especificado"
        job_data['link'] = f"https://www.linkedin.com/jobs/view/{job_id}/"
        if job_data.get('title') == "No especificado" or job_data.get('company') == "No especificado": return None
        return job_data
    except Exception as e:
        error_msg = f"Error procesando tarjeta LinkedIn desde div (ID: {job_id if job_id else 'Desconocido'}): {e}"
        print(error_msg)
        return None

def get_total_results_occ(soup):
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
    job_data = {}
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
        job_data['company'] = "No especificado"
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
        if job_data.get('job_id'): job_data['link'] = f"https://www.occ.com.mx/empleo/oferta/{job_data['job_id']}/"
        else: job_data['link'] = "No encontrado (sin ID)"
        return job_data if job_data.get('title') and job_data.get('job_id') else None
    except Exception as e:
        print(f"Error procesando tarjeta OCC: {e}")
        card_id_debug = card_soup.get('id', 'ID no encontrado')
        print(f"  Tarjeta OCC con ID (aprox): {card_id_debug}")
        return None

def parse_job_card_indeed(card_soup):
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
    print("Conectando a la instancia de Chrome en modo depuración remota...")
    chrome_options = ChromeOptions()
    chrome_options.add_experimental_option("debuggerAddress", config_selenium['debugger_address'])
    try:
        driver = webdriver.Chrome(options=chrome_options)
        try:
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        except Exception as e_script:
            print(f"Advertencia: No se pudo ocultar webdriver: {e_script}")
        print("Conectado a la instancia remota de Chrome.")
        return driver
    except WebDriverException as e:
        if "cannot connect to chrome" in str(e).lower() or "disconnected" in str(e).lower():
             print(f"Error Crítico: No se pudo conectar a Chrome en {config_selenium['debugger_address']}.")
             print("Asegúrate de haber lanzado Chrome con --remote-debugging-port=XXXX y que esté abierto.")
        else:
             print(f"Error de WebDriver al conectar: {e}")
        return None
    except Exception as e:
        print(f"Error inesperado al conectar con Chrome: {e}")
        return None

def close_cookie_popup(driver, wait_short):
    if not driver: return
    xpath_accept = "//button[contains(@aria-label, 'Accept cookies') or contains(@aria-label,'Aceptar cookies') or contains(text(), 'Accept') or contains(text(), 'Aceptar') or contains(@data-tracking-control-name, 'accept_cookies') or contains(@id, 'onetrust-accept')]"
    try:
        cookie_button = wait_short.until(EC.element_to_be_clickable((By.XPATH, xpath_accept)))
        cookie_button.click()
        print("Pop-up de cookies cerrado.")
        time.sleep(1)
    except TimeoutException:
        pass
    except Exception as e:
        print(f"Error al cerrar pop-up de cookies: {e}")

def scrape_occ_for_keyword(keyword, time_param_value, found_job_ids, config):
    platform_config = config['platforms']['occ']
    timing_config = config['timing']
    search_filters_config = config['search_filters']
    headers = config['general']['headers']
    # Obtener max_pages del config, con un default muy alto si no está definido
    max_pages_to_scrape_occ = platform_config.get('max_pages', 999) # <--- NUEVO

    print(f"\n--- Iniciando OCC para '{keyword}' ({platform_config['time_param_name']}={time_param_value}, max_pages={max_pages_to_scrape_occ}) ---") # <--- Modificado log
    base_url_with_tm = f"{platform_config['base_url'].format(keyword=keyword)}&{platform_config['time_param_name']}={time_param_value}"
    page = 1
    max_pages_calculated = 1 # Este será el max_pages calculado por la web
    actual_jobs_per_page = 0
    new_jobs_occ = []
    processed_titles = {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}
    total_added = 0

    while True:
        # Condición de salida basada en el MÍNIMO entre el max_pages del config y el calculado
        if page > min(max_pages_to_scrape_occ, max_pages_calculated): # <--- MODIFICADO
            if page > max_pages_to_scrape_occ:
                print(f"    OCC: Límite de max_pages ({max_pages_to_scrape_occ}) del config alcanzado.")
            else:
                print(f"    OCC: Límite de páginas calculadas ({max_pages_calculated}) alcanzado.")
            break

        current_url = f"{base_url_with_tm}&page={page}" if page > 1 else base_url_with_tm
        print(f"  OCC - Página {page}{' de '+str(min(max_pages_to_scrape_occ, max_pages_calculated)) if min(max_pages_to_scrape_occ, max_pages_calculated) > 1 else ''}...") # <--- MODIFICADO log

        try:
            response = requests.get(current_url, headers=headers, timeout=platform_config['request_timeout'])
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')
            job_cards = soup.find_all('div', id=lambda x: x and x.startswith('jobcard-'))
            current_page_job_count = len(job_cards)

            if page == 1:
                actual_jobs_per_page = current_page_job_count
                if actual_jobs_per_page > 0:
                    total_results = get_total_results_occ(soup)
                    if total_results > 0:
                        max_pages_calculated = math.ceil(total_results / actual_jobs_per_page) # <--- Actualiza max_pages_calculated
                        print(f"    OCC: {total_results} resultados, {actual_jobs_per_page}/pág, {max_pages_calculated} pág. estimadas (config limit: {max_pages_to_scrape_occ})")
                    else:
                        max_pages_calculated = 1 # <--- Actualiza max_pages_calculated
                else:
                    print(f"    OCC: No se encontraron ofertas en la primera página.")
                    break

            if not job_cards and page > 1:
                print(f"    OCC: No se encontraron más ofertas en la página {page}.")
                break

            found_on_page = 0
            # ... (resto del bucle for card in job_cards ... sin cambios)
            for card in job_cards:
                job_info = parse_job_card_occ(card)
                if job_info:
                    job_id = job_info.get('job_id'); job_title = job_info.get('title', '')
                    is_valid, reason_type, reason_keyword = filter_job_by_title(job_title, search_filters_config)
                    if not is_valid:
                        processed_titles[reason_type].append(f"{job_title} (Filtro: {reason_keyword or 'implícito'})"); continue
                    if job_id and job_id not in found_job_ids:
                        job_info['timestamp_found'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        job_info['platform'] = 'OCC'; new_jobs_occ.append(job_info); found_job_ids.add(job_id)
                        found_on_page += 1; processed_titles['included'].append(job_title)
            # ...

            print(f"    OCC: +{found_on_page} nuevas. Filtros: {len(processed_titles['included'])} incl, {len(processed_titles['excluded_explicit'])} excl_exp, {len(processed_titles['excluded_implicit'])} excl_imp.")
            total_added += found_on_page

            # La condición de salida ahora está al inicio del bucle while
            page += 1
            time.sleep(timing_config['delay_between_keywords'])

        except requests.exceptions.Timeout:
             print(f"    OCC: Timeout en página {page}. Reintentando...")
             time.sleep(timing_config['retry_delay'])
             continue
        except requests.exceptions.RequestException as e:
            print(f"    OCC: Error Red/HTTP en página {page}: {e}. Abortando OCC para '{keyword}'.")
            break
        except Exception as e:
            print(f"    OCC: Error general en página {page}: {e}. Abortando OCC para '{keyword}'.")
            break

    print(f"--- Fin OCC para '{keyword}'. Total nuevas: {total_added} ---")
    return new_jobs_occ, processed_titles

def scrape_linkedin_for_keyword(driver, keyword, time_param_value, found_job_ids, config):
    platform_config = config['platforms']['linkedin']; timing_config = config['timing']; search_filters_config = config['search_filters']
    if not driver: print(f"\n--- Skipping LinkedIn para '{keyword}' (Driver no disponible) ---"); return [], {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}
    print(f"\n--- Iniciando LinkedIn para '{keyword}' ({platform_config['time_param_name']}={time_param_value}) ---")
    base_url_with_time = f"{platform_config['base_url'].format(keyword=keyword)}&{platform_config['time_param_name']}={time_param_value}"
    page = 1; max_pages_to_scrape = 1; total_results_linkedin = 0
    new_jobs_linkedin = []; processed_titles = {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}; total_added = 0
    keep_paging = True; wait_long = WebDriverWait(driver, platform_config['request_timeout_selenium']); wait_short = WebDriverWait(driver, 5)
    while keep_paging:
        start_index = (page - 1) * platform_config['page_increment']
        current_url = f"{base_url_with_time}&start={start_index}" if page > 1 else base_url_with_time
        print(f"  LinkedIn - Página {page} (start={start_index})... URL: {current_url}")
        try:
            driver.get(current_url); print("    LinkedIn: Esperando carga inicial (5s)..."); time.sleep(5)
            close_cookie_popup(driver, wait_short)
            no_results_found = False
            try:
                no_results_xpath = "//*[contains(@class, 'jobs-search-results-list__no-results') or contains(@class, 'jobs-search-no-results') or contains(text(), 'No se encontraron resultados') or contains(text(), 'No matching jobs found')]"
                WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                if driver.find_elements(By.XPATH, no_results_xpath): print(f"    LinkedIn: Detectado 'Sin resultados'."); no_results_found = True; break
            except TimeoutException: pass
            except Exception as e_nores: print(f"    LinkedIn: Advertencia menor buscando 'sin resultados': {e_nores}")
            if no_results_found: continue
            list_container_selector = "main[class*='scaffold-layout__list']"; job_id_div_selector = "div[data-job-id]"
            try:
                wait_long.until(EC.presence_of_element_located((By.CSS_SELECTOR, f"{list_container_selector} {job_id_div_selector}")))
                print("    LinkedIn: Contenedor principal y al menos un DIV con data-job-id encontrados."); time.sleep(4)
                if page == 1:
                     total_results_linkedin = get_total_results_linkedin(driver, platform_config)
                     if total_results_linkedin > 0:
                          max_pages_calc = math.ceil(total_results_linkedin / platform_config['page_increment'])
                          max_pages_to_scrape = min(max_pages_calc, platform_config['max_pages'])
                          print(f"    LinkedIn: {total_results_linkedin} resultados reportados. Procesando hasta {max_pages_to_scrape} páginas.")
                     else:
                         try:
                             driver.find_element(By.CSS_SELECTOR, f"{list_container_selector} {job_id_div_selector}")
                             max_pages_to_scrape = 1; print(f"    LinkedIn: No se obtuvo total > 0, pero hay divs. Procesando solo página 1.")
                         except NoSuchElementException: print(f"    LinkedIn: No hay divs visibles. Abortando LinkedIn para '{keyword}'."); keep_paging=False; continue
            except TimeoutException: print(f"    LinkedIn: Timeout esperando contenedor o divs en página {page}."); keep_paging = False; continue
            except Exception as e_wait: print(f"    LinkedIn: Error esperando elementos en página {page}: {e_wait}."); keep_paging = False; continue
            page_html = driver.page_source; soup = BeautifulSoup(page_html, 'lxml'); job_divs = soup.find_all('div', attrs={'data-job-id': True})
            print(f"    LinkedIn: {len(job_divs)} divs con data-job-id encontrados en HTML.")
            if not job_divs and page == 1 and total_results_linkedin == 0: break
            if not job_divs and page > 1: break
            found_on_page = 0
            for job_div in job_divs:
                 job_info = parse_job_card_linkedin_from_div(job_div)
                 if job_info:
                    job_id = job_info.get('job_id'); job_title = job_info.get('title', '')
                    is_valid, reason_type, reason_keyword = filter_job_by_title(job_title, search_filters_config)
                    if not is_valid: processed_titles[reason_type].append(f"{job_title} (Filtro: {reason_keyword or 'implícito'})"); continue
                    if job_id and job_id not in found_job_ids:
                        job_info['timestamp_found'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        job_info['platform'] = 'LinkedIn'; new_jobs_linkedin.append(job_info); found_job_ids.add(job_id)
                        found_on_page += 1; processed_titles['included'].append(job_title)
            print(f"    LinkedIn: +{found_on_page} nuevas. Filtros: {len(processed_titles['included'])} incl, {len(processed_titles['excluded_explicit'])} excl_exp, {len(processed_titles['excluded_implicit'])} excl_imp.")
            total_added += found_on_page
            if page >= max_pages_to_scrape: print(f"    LinkedIn: Se alcanzó la última página procesable ({max_pages_to_scrape})."); keep_paging = False
            if keep_paging: page += 1; print(f"\n--- Esperando {platform_config['delay_between_pages_selenium']}s antes de la siguiente página ---"); time.sleep(platform_config['delay_between_pages_selenium'])
        except TimeoutException: print(f"    LinkedIn: Timeout general en página {page}. Abortando keyword."); keep_paging = False
        except WebDriverException as e: print(f"    LinkedIn: Error de WebDriver en página {page}: {e}. Abortando script."); keep_paging = False; raise e
        except Exception as e: print(f"    LinkedIn: Error general en página {page}: {e}. Abortando keyword."); keep_paging = False
    print(f"--- Fin LinkedIn para '{keyword}'. Total nuevas: {total_added} ---")
    return new_jobs_linkedin, processed_titles

def scrape_indeed_for_keyword(driver, keyword, time_param_value, found_job_ids, config):
    platform_config = config['platforms']['indeed']
    timing_config = config['timing']
    search_filters_config = config['search_filters']
    # Obtener max_pages del config, con un default muy alto si no está definido
    max_pages_to_scrape_indeed = platform_config.get('max_pages', 999) # <--- NUEVO

    if not driver:
        print(f"\n--- Skipping Indeed para '{keyword}' (Driver no disponible) ---")
        return [], {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}

    print(f"\n--- Iniciando Indeed para '{keyword}' ({platform_config['time_param_name']}={time_param_value}, max_pages={max_pages_to_scrape_indeed}) ---") # <--- Modificado log
    base_url_with_fromage = f"{platform_config['base_url']}&{platform_config['time_param_name']}={time_param_value}"
    page = 1
    new_jobs_indeed = []
    processed_titles = {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}
    total_added = 0
    keep_paging = True
    wait_long = WebDriverWait(driver, platform_config['request_timeout_selenium'])
    wait_short = WebDriverWait(driver, 3)

    while keep_paging:
        # Condición de salida basada en el max_pages del config
        if page > max_pages_to_scrape_indeed: # <--- MODIFICADO
            print(f"    Indeed: Límite de max_pages ({max_pages_to_scrape_indeed}) del config alcanzado.")
            break

        start_index = (page - 1) * platform_config['page_increment']
        current_url = base_url_with_fromage.format(keyword=keyword, start=start_index)
        print(f"  Indeed - Página {page} de (hasta) {max_pages_to_scrape_indeed} (start={start_index})...") # <--- MODIFICADO log

        try:
            driver.get(current_url)
            close_cookie_popup(driver, wait_short)

            try:
                no_results_xpath = "//*[contains(text(), 'no produjo ningún resultado') or contains(text(), 'did not match any jobs')]"
                WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.XPATH, "//*")))
                if driver.find_elements(By.XPATH, no_results_xpath):
                    print(f"    Indeed: Detectado 'Sin resultados'.")
                    break
            except TimeoutException: pass
            except Exception as e_nores: print(f"    Indeed: Advertencia menor buscando 'sin resultados': {e_nores}")

            try:
                wait_long.until(EC.presence_of_element_located((By.ID, "mosaic-provider-jobcards")))
                wait_long.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "div#mosaic-provider-jobcards li div.cardOutline")))
                time.sleep(2)
            except TimeoutException:
                print(f"    Indeed: Timeout esperando tarjetas en página {page}.")
                if page == 1: print(f"    Indeed: Error cargando resultados iniciales. Abortando.")
                else: print(f"    Indeed: Asumiendo fin de resultados.")
                keep_paging = False; continue
            except Exception as e_wait:
                 print(f"    Indeed: Error esperando elementos en página {page}: {e_wait}. Abortando.")
                 keep_paging = False; continue

            page_html = driver.page_source
            soup = BeautifulSoup(page_html, 'lxml')
            job_list_container_soup = soup.find('div', id='mosaic-provider-jobcards')
            job_cards_li = []
            if job_list_container_soup:
                ul_list = job_list_container_soup.find('ul', class_='css-1faftfv') or job_list_container_soup.find('ul')
                if ul_list: job_cards_li = [li for li in ul_list.find_all('li', recursive=False) if li.find('div', class_='cardOutline')]
            else: print("    Indeed: Advertencia - Contenedor de tarjetas no encontrado.")

            if not job_cards_li and page == 1: # Si no hay tarjetas en la primera página, no seguir.
                print(f"    Indeed: No se encontraron tarjetas en la primera página para '{keyword}'.")
                break
            if not job_cards_li and page > 1: # Si no hay tarjetas en páginas posteriores, fin.
                print(f"    Indeed: No se encontraron más tarjetas en página {page} para '{keyword}'.")
                break


            found_on_page = 0
            # ... (resto del bucle for card_li in job_cards_li ... sin cambios)
            for card_li in job_cards_li:
                 job_info = parse_job_card_indeed(card_li)
                 if job_info:
                    job_id = job_info.get('job_id'); job_title = job_info.get('title', '')
                    is_valid, reason_type, reason_keyword = filter_job_by_title(job_title, search_filters_config)
                    if not is_valid:
                        processed_titles[reason_type].append(f"{job_title} (Filtro: {reason_keyword or 'implícito'})"); continue
                    if job_id and job_id not in found_job_ids:
                        job_info['timestamp_found'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        job_info['platform'] = 'Indeed'; new_jobs_indeed.append(job_info); found_job_ids.add(job_id)
                        found_on_page += 1; processed_titles['included'].append(job_title)
            # ...

            print(f"    Indeed: +{found_on_page} nuevas. Filtros: {len(processed_titles['included'])} incl, {len(processed_titles['excluded_explicit'])} excl_exp, {len(processed_titles['excluded_implicit'])} excl_imp.")
            total_added += found_on_page

            try:
                if not driver.find_elements(By.CSS_SELECTOR, "a[data-testid='pagination-page-next']"):
                     print(f"    Indeed: No se encontró enlace 'Siguiente'. Fin para '{keyword}'.")
                     keep_paging = False
            except Exception as e_nav:
                 print(f"    Indeed: Error buscando paginación: {e_nav}. Abortando.")
                 keep_paging = False

            if keep_paging: # Solo incrementar y esperar si no hemos decidido parar
                 page += 1
                 # También verificamos aquí para no dormir innecesariamente si la siguiente página excede el límite
                 if page > max_pages_to_scrape_indeed:
                     print(f"    Indeed: Límite de max_pages ({max_pages_to_scrape_indeed}) del config se alcanzará en la siguiente iteración. Deteniendo.")
                     keep_paging = False # Para salir en la próxima comprobación del while
                 else:
                     time.sleep(platform_config.get('delay_between_pages_selenium', timing_config['delay_between_keywords']))

        except TimeoutException:
             print(f"    Indeed: Timeout general en página {page}. Abortando Indeed para '{keyword}'.")
             keep_paging = False
        except WebDriverException as e:
             print(f"    Indeed: Error de WebDriver en página {page}: {e}. Abortando script.")
             keep_paging = False; raise e
        except Exception as e:
            print(f"    Indeed: Error general en página {page}: {e}. Abortando Indeed para '{keyword}'.")
            keep_paging = False

    print(f"--- Fin Indeed para '{keyword}'. Total nuevas: {total_added} ---")
    return new_jobs_indeed, processed_titles

def main(config_path):
    config = load_config(config_path)
    output_filename = config['general']['output_filename']
    final_columns_to_save = config['general']['final_columns_to_save']
    existing_df = pd.DataFrame(columns=final_columns_to_save); found_job_ids = set()
    if os.path.exists(output_filename):
        print(f"Cargando datos existentes desde '{output_filename}'...")
        try:
            existing_df = pd.read_csv(output_filename)
            for col in final_columns_to_save:
                if col not in existing_df.columns: existing_df[col] = pd.NA
            if 'job_id' in existing_df.columns:
                existing_df['job_id'] = existing_df['job_id'].astype(str)
                found_job_ids = set(existing_df['job_id'].dropna().tolist())
                print(f"Se cargaron {len(found_job_ids)} IDs existentes.")
            else: print("Advertencia: El archivo CSV no tiene 'job_id'. Se creará."); existing_df['job_id'] = pd.Series(dtype='str')
        except pd.errors.EmptyDataError: print("El archivo CSV existente está vacío.")
        except Exception as e: print(f"Error al leer CSV: {e}. Se procederá como si no existiera."); existing_df = pd.DataFrame(columns=final_columns_to_save); found_job_ids = set()
    else: print(f"'{output_filename}' no existe. Se creará.")
    tm_param_occ = config['platforms']['occ']['default_time_param_value']
    fromage_param_indeed = config['platforms']['indeed']['default_time_param_value']
    f_tpr_param_linkedin = config['platforms']['linkedin']['default_time_param_value']
    print(f"Parámetros de búsqueda por tiempo: OCC tm={tm_param_occ}, Indeed fromage={fromage_param_indeed}, LinkedIn f_TPR={f_tpr_param_linkedin}")
    all_new_jobs = []; global_processed_titles = {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}
    driver = None
    needs_selenium = (config['platforms']['linkedin']['enabled'] or config['platforms']['indeed']['enabled'])
    if needs_selenium:
        driver = setup_driver(config['selenium'])
        if not driver and (config['platforms']['linkedin']['enabled'] or config['platforms']['indeed']['enabled']):
            print("Error crítico: No se pudo inicializar Selenium Driver. Saliendo."); return
    print("\n======= INICIANDO SCRAPING =======")
    try:
        search_keywords_list = config['search_filters']['search_keywords']
        for i, keyword_raw in enumerate(search_keywords_list):
            print(f"\n==================== Keyword {i+1}/{len(search_keywords_list)}: '{keyword_raw}' ====================")
            keyword_occ = keyword_raw.replace(' ', '-'); keyword_indeed = keyword_raw.replace(' ', '+'); keyword_linkedin = keyword_raw.replace(' ', '%20')
            if config['platforms']['occ']['enabled']:
                new_jobs, titles = scrape_occ_for_keyword(keyword_occ, tm_param_occ, found_job_ids, config)
                all_new_jobs.extend(new_jobs); [global_processed_titles[key].extend(titles[key]) for key in global_processed_titles]
            if config['platforms']['indeed']['enabled']:
                new_jobs, titles = scrape_indeed_for_keyword(driver, keyword_indeed, fromage_param_indeed, found_job_ids, config)
                all_new_jobs.extend(new_jobs); [global_processed_titles[key].extend(titles[key]) for key in global_processed_titles]
            if config['platforms']['linkedin']['enabled']:
                new_jobs, titles = scrape_linkedin_for_keyword(driver, keyword_linkedin, f_tpr_param_linkedin, found_job_ids, config)
                all_new_jobs.extend(new_jobs); [global_processed_titles[key].extend(titles[key]) for key in global_processed_titles]
            if i < len(search_keywords_list) - 1: print(f"\nEsperando {config['timing']['delay_between_keywords']}s antes de la siguiente keyword..."); time.sleep(config['timing']['delay_between_keywords'])
    except WebDriverException as e_wd_global: print(f"\nERROR CRÍTICO DE WEBDRIVER: {e_wd_global}")
    except Exception as e_global: print(f"\nERROR GLOBAL INESPERADO: {e_global}")
    finally:
        if driver: print("\nCierre de WebDriver no implementado explícitamente para modo debug remoto.")
    print("\n======= PROCESANDO RESULTADOS FINALES =======")
    print("\n--- Reporte de Títulos Procesados (Total Global) ---")
    print(f"Total Incluidos: {len(global_processed_titles['included'])}")
    print(f"Total Excluidos (explícito): {len(global_processed_titles['excluded_explicit'])}")
    print(f"Total Excluidos (implícito): {len(global_processed_titles['excluded_implicit'])}")
    if all_new_jobs:
        print(f"\nSe encontraron {len(all_new_jobs)} ofertas nuevas en total.")
        new_df = pd.DataFrame(all_new_jobs)
        if 'job_id' not in new_df.columns: new_df['job_id'] = pd.NA
        new_df['job_id'] = new_df['job_id'].astype(str)
        if not existing_df.empty:
            print(f"Combinando {len(new_df)} nuevos con {len(existing_df)} existentes.")
            for col in final_columns_to_save:
                if col not in new_df.columns: new_df[col] = pd.NA
                if col not in existing_df.columns: existing_df[col] = pd.NA
            new_df = new_df.reindex(columns=final_columns_to_save)
            existing_df = existing_df.reindex(columns=final_columns_to_save)
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        else: print("No había datos existentes, guardando solo los nuevos."); combined_df = new_df.reindex(columns=final_columns_to_save)
        initial_rows = len(combined_df)
        combined_df.dropna(subset=['job_id'], inplace=True)
        combined_df = combined_df[combined_df['job_id'] != 'None']
        combined_df.drop_duplicates(subset=['job_id'], keep='first', inplace=True)
        final_rows = len(combined_df)
        if initial_rows > final_rows: print(f"Se eliminaron {initial_rows - final_rows} duplicados/inválidos durante la combinación.")
        try:
            combined_df_to_save = combined_df[final_columns_to_save]
            combined_df_to_save.to_csv(output_filename, index=False, encoding='utf-8-sig')
            print(f"\nDatos combinados guardados en '{output_filename}' ({len(combined_df_to_save)} ofertas).")
        except Exception as e: print(f"\nError al guardar el archivo CSV final: {e}")
    elif not existing_df.empty: print("\nNo se encontraron ofertas nuevas. El archivo existente no se modificó."); print(f"'{output_filename}' contiene {len(existing_df)} ofertas.")
    else: print("\nNo se encontraron ofertas nuevas y no existía archivo previo.")
    print("\n======= FIN DEL SCRIPT =======")

# --- FIN DE LAS FUNCIONES, INICIO DEL BLOQUE PRINCIPAL DE EJECUCIÓN ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraper de trabajos remotos.")
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml", # Nombre por defecto del archivo de configuración
        help="Ruta al archivo de configuración YAML (default: config.yaml)"
    )
    args = parser.parse_args()
    main(args.config)