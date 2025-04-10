from bs4 import BeautifulSoup
import time
import math
import re
import pandas as pd
import os
from datetime import datetime, timedelta

# --- Selenium Imports ---
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
from selenium.webdriver.chrome.options import Options as ChromeOptions

# --- Configuración General ---
OUTPUT_FILENAME = "linkedin_remote_jobs.csv"
# Lista final de columnas a guardar
FINAL_COLUMNS_TO_SAVE = ['job_id', 'platform', 'title', 'company', 'salary', 'timestamp_found', 'link']

# --- Configuración Específica LinkedIn ---
BASE_URL_LINKEDIN = "https://www.linkedin.com/jobs/search/?f_WT=2&keywords={keyword}&sortBy=DD"
LINKEDIN_PAGE_INCREMENT = 25
MAX_LINKEDIN_PAGES = 20

# --- Palabras a buscar ---
SEARCH_KEYWORDS = [
    "devops", "cloud", "aws", "gcp", "site reliability engineer", "mlops", "platform engineer"
]

# --- Filtros de Título (Comunes) ---
EXCLUDE_TITLE_KEYWORDS = [
    "software", "development", "data", ".net", "python", "quality", "security", "seguridad", "developer",
    "salesforce", "desarroll", "qa", "ruby", "test", "datos", "java", "fullstack", "sap", "hibrido",
    "qlik sense", "qliksense", "híbrido", "híbrida", "hibrida", "oracle", "architect"
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
DELAY_BETWEEN_KEYWORDS = 15
RETRY_DELAY = 10
REQUEST_TIMEOUT_SELENIUM = 60
DELAY_BETWEEN_PAGES_SELENIUM = 12

# --- Funciones Selenium ---
def setup_driver():
    """Configura y conecta con la instancia remota de Chrome."""
    print("Conectando a la instancia de Chrome en modo depuración remota...")
    chrome_options = ChromeOptions()
    chrome_options.add_experimental_option("debuggerAddress", "localhost:9222")
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
             print(f"Error Crítico: No se pudo conectar a Chrome en localhost:9222.")
             print("Asegúrate de haber lanzado Chrome con --remote-debugging-port=9222 y que esté abierto.")
        else:
             print(f"Error de WebDriver al conectar: {e}")
        return None
    except Exception as e:
        print(f"Error inesperado al conectar con Chrome: {e}")
        return None

def close_cookie_popup(driver, wait_short):
    """Intenta cerrar el popup de cookies de LinkedIn."""
    if not driver: return
    xpath_accept = "//button[contains(@aria-label, 'Accept cookies') or contains(@aria-label,'Aceptar cookies') or contains(text(), 'Accept') or contains(text(), 'Aceptar')]"
    try:
        cookie_button = wait_short.until(EC.element_to_be_clickable((By.XPATH, xpath_accept)))
        cookie_button.click()
        print("Pop-up de cookies cerrado (LinkedIn).")
        time.sleep(1)
    except TimeoutException:
        pass
    except Exception as e:
        print(f"Error al cerrar pop-up de cookies (LinkedIn): {e}")

# --- Funciones de Parseo y Obtención de Resultados ---

# --- MODIFICADA: Obtener Total de Resultados ---
def get_total_results_linkedin(driver):
    """Intenta extraer el número total de resultados de LinkedIn buscando el div__subtitle."""
    try:
        # Selector CSS para el div específico que contiene el texto de resultados
        subtitle_selector = "div.jobs-search-results-list__subtitle"
        print(f"    get_total_results: Esperando por '{subtitle_selector}'...")

        # Esperar a que el elemento esté presente
        subtitle_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, subtitle_selector))
        )
        print("    get_total_results: Elemento subtitle encontrado.")

        # Extraer el texto y buscar el número
        subtitle_text = subtitle_element.text
        print(f"    get_total_results: Texto encontrado en subtitle: '{subtitle_text}'")

        # 1. Quitar comas (si las hubiera, aunque a veces LinkedIn no las pone)
        text_without_commas = subtitle_text.replace(',', '')
        # 2. Usar regex simple para encontrar cualquier secuencia de dígitos
        match = re.search(r'(\d+)', text_without_commas)
        if match:
            total = int(match.group(1))
            print(f"    LinkedIn: Total extraído del subtitle: {total}")
            # Limitar el total a 1000, ya que LinkedIn no muestra más allá de la página 40
            if total > (MAX_LINKEDIN_PAGES * LINKEDIN_PAGE_INCREMENT):
                 limit = MAX_LINKEDIN_PAGES * LINKEDIN_PAGE_INCREMENT
                 print(f"    Advertencia: LinkedIn reporta {total} resultados, pero solo se pueden ver ~{limit}. Limitando a {limit}.")
                 return limit
            return total
        else:
            print(f"Advertencia (LinkedIn): Patrón numérico no encontrado en texto del subtitle: '{subtitle_text}'")
            return 0 # Devolver 0 si no se encuentra el número

    except TimeoutException:
        print("Advertencia (LinkedIn): Timeout esperando el div subtitle de resultados ('div.jobs-search-results-list__subtitle').")
        # Fallback: verificar si hay divs con data-job-id como antes
        try:
            driver.find_element(By.CSS_SELECTOR, "main[class*='scaffold-layout__list'] div[data-job-id]")
            print("    LinkedIn (Fallback): Subtitle no encontrado, pero SÍ hay divs con ID. Asumiendo 1 página.")
            return LINKEDIN_PAGE_INCREMENT # Devolver 25 para procesar al menos la página actual
        except NoSuchElementException:
             print("    LinkedIn (Fallback): Ni subtitle ni divs con ID encontrados tras timeout. Asumiendo 0 resultados.")
             return 0
    except Exception as e:
        print(f"Error general al obtener total de resultados (LinkedIn): {e}")
        return 0 # Devolver 0 en caso de otros errores

# --- MODIFICADA: Parseo desde Div ---
def parse_job_card_linkedin_from_div(job_div):
    """Extrae info de una tarjeta LinkedIn a partir del div con data-job-id."""
    job_data = {}
    job_id = None # Inicializar job_id
    try:
        job_id = job_div.get('data-job-id')
        if not job_id:
            return None
        job_data['job_id'] = str(job_id)

        card_container = job_div.find_parent('li')
        if not card_container:
             card_container = job_div.find_parent('div', class_=lambda x: x and 'job-card-container' in x)
             if not card_container:
                   card_container = job_div.find_parent('div', class_=lambda x: x and 'job-posting-card' in x)

        if not card_container:
             # print(f"Advertencia: No se encontró contenedor padre (li o div) para job_id {job_id}")
             return None

        # --- Extracción desde el contenedor padre (card_container) ---
        title_tag = card_container.find(['h3', 'h4'], class_=lambda x: x and 'base-search-card__title' in x)
        if not title_tag:
            title_link = card_container.find('a', class_=lambda x: x and 'job-card-list__title' in x)
            if title_link: job_data['title'] = title_link.get_text(strip=True)
            else:
                 title_strong = card_container.find('strong')
                 if title_strong: job_data['title'] = title_strong.get_text(strip=True)
                 else:
                      first_link_in_card = card_container.find('a')
                      job_data['title'] = first_link_in_card.get_text(strip=True) if first_link_in_card else "No especificado"
        else: job_data['title'] = title_tag.get_text(strip=True)

        company_tag = card_container.find(['a','span'], class_=lambda x: x and ('base-search-card__subtitle' in x or 'job-card-container__primary-description' in x))
        if not company_tag: company_tag = card_container.find('div', class_=lambda x: x and 'artdeco-entity-lockup__subtitle' in x)
        job_data['company'] = company_tag.get_text(strip=True) if company_tag else "No especificado"

        job_data['salary'] = "No especificado"
        job_data['link'] = f"https://www.linkedin.com/jobs/view/{job_id}/"

        if job_data.get('title') == "No especificado" or job_data.get('company') == "No especificado":
             # print(f"  Debug: Título o Compañía no encontrados para ID {job_id}.")
             return None

        return job_data

    except Exception as e:
        error_msg = f"Error procesando tarjeta LinkedIn desde div (ID: {job_id if job_id else 'Desconocido'}): {e}"
        # Limitar la impresión del HTML para no saturar el log
        html_snippet = job_div.prettify()[:500] + '...' if job_div else 'HTML no disponible'
        # print(f"{error_msg}\n  HTML Snippet:\n{html_snippet}\n")
        print(error_msg) # Imprimir solo el error por defecto
        return None

# --- MODIFICADA: Función Principal de Scraping ---
def scrape_linkedin_for_keyword(driver, keyword, f_tpr_param, found_job_ids):
    """Busca en LinkedIn usando Selenium para una keyword y rango de tiempo."""
    if not driver:
        print(f"\n--- Skipping LinkedIn para '{keyword}' (Driver no disponible) ---")
        return [], {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}

    print(f"\n--- Iniciando LinkedIn para '{keyword}' (f_TPR={f_tpr_param}) ---")
    base_url_with_time = f"{BASE_URL_LINKEDIN.format(keyword=keyword)}&f_TPR={f_tpr_param}"
    page = 1; max_pages = 1; total_results_linkedin = 0 # Inicializar max_pages a 1
    new_jobs_linkedin = []; processed_titles = {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}
    skipped_excluded_title_total = 0; skipped_inclusion_fail_total = 0; total_added = 0
    keep_paging = True
    wait_long = WebDriverWait(driver, REQUEST_TIMEOUT_SELENIUM); wait_short = WebDriverWait(driver, 5)

    while keep_paging:
        start_index = (page - 1) * LINKEDIN_PAGE_INCREMENT
        current_url = f"{base_url_with_time}&start={start_index}" if page > 1 else base_url_with_time
        print(f"  LinkedIn - Página {page} (start={start_index})... URL: {current_url}")

        try:
            driver.get(current_url)
            print("    LinkedIn: Esperando carga inicial (5s)...")
            time.sleep(5)

            close_cookie_popup(driver, wait_short)

            # Chequeo Rápido "Sin Resultados"
            no_results_found = False
            try:
                no_results_xpath = "//*[contains(@class, 'jobs-search-results-list__no-results') or contains(@class, 'jobs-search-no-results') or contains(text(), 'No se encontraron resultados') or contains(text(), 'No matching jobs found')]"
                WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                if driver.find_elements(By.XPATH, no_results_xpath):
                    print(f"    LinkedIn: Detectado 'Sin resultados'.")
                    no_results_found = True
                    break
            except TimeoutException: pass
            except Exception as e_nores: print(f"    LinkedIn: Advertencia menor buscando 'sin resultados': {e_nores}")
            if no_results_found: continue

            # --- REVISADO: Espera Principal ---
            list_container_selector = "main[class*='scaffold-layout__list']"
            job_id_div_selector = "div[data-job-id]"
            try:
                wait_long.until(EC.presence_of_element_located((By.CSS_SELECTOR, f"{list_container_selector} {job_id_div_selector}")))
                print("    LinkedIn: Contenedor principal y al menos un DIV con data-job-id encontrados.")
                time.sleep(4) # Pausa adicional para renderizado

                if page == 1:
                     total_results_linkedin = get_total_results_linkedin(driver)
                     if total_results_linkedin > 0:
                          max_pages_calc = math.ceil(total_results_linkedin / LINKEDIN_PAGE_INCREMENT)
                          max_pages = min(max_pages_calc, MAX_LINKEDIN_PAGES) # Aplicar límite máximo
                          print(f"    LinkedIn: {total_results_linkedin} resultados reportados, {LINKEDIN_PAGE_INCREMENT}/pág. Procesando hasta {max_pages} páginas.")
                     else:
                         try:
                             driver.find_element(By.CSS_SELECTOR, f"{list_container_selector} {job_id_div_selector}")
                             max_pages = 1 # Mantener max_pages en 1 si hay divs pero no total
                             print(f"    LinkedIn: No se obtuvo total > 0 desde get_total_results, pero hay divs con ID. Procesando solo página 1.")
                         except NoSuchElementException:
                              print(f"    LinkedIn: No se obtuvo total Y no hay divs con ID visibles. Abortando LinkedIn para '{keyword}'.")
                              keep_paging=False
                              continue
                # Si no es página 1, max_pages ya está establecido (o sigue siendo 1)

            except TimeoutException:
                print(f"    LinkedIn: Timeout esperando contenedor o divs con data-job-id en página {page}.")
                try: driver.save_screenshot(f"debug_linkedin_timeout_p{page}_{keyword}.png"); print(f"    LinkedIn: Screenshot guardado.")
                except Exception as img_e: print(f"    LinkedIn: No se pudo guardar screenshot: {img_e}")
                if page == 1: print(f"    LinkedIn: Error cargando resultados iniciales. Abortando LinkedIn para '{keyword}'.")
                else: print(f"    LinkedIn: Asumiendo fin de resultados por timeout.")
                keep_paging = False
                continue
            except Exception as e_wait:
                 print(f"    LinkedIn: Error esperando elementos en página {page}: {e_wait}.")
                 keep_paging = False
                 continue

            # # Scroll down
            # print("    LinkedIn: Realizando scroll...");
            # try: scrollable_element = driver.find_element(By.CSS_SELECTOR, list_container_selector)
            # except NoSuchElementException: print("    LinkedIn: No se encontró el elemento scrollable. Intentando con 'body'."); scrollable_element = driver.find_element(By.TAG_NAME, 'body')
            # last_height = driver.execute_script("return arguments[0].scrollHeight", scrollable_element); scroll_attempts = 0; max_scroll_attempts = 8; consecutive_no_change = 0
            # while scroll_attempts < max_scroll_attempts:
            #     driver.execute_script("arguments[0].scrollTo(0, arguments[0].scrollHeight);", scrollable_element); time.sleep(4)
            #     new_height = driver.execute_script("return arguments[0].scrollHeight", scrollable_element)
            #     if new_height == last_height:
            #         consecutive_no_change += 1; print(f"    LinkedIn: Scroll sin cambio de altura (intento {consecutive_no_change}/2)")
            #         if consecutive_no_change >= 2: print("    LinkedIn: Scroll completo o estancado."); break
            #     else: consecutive_no_change = 0
            #     last_height = new_height; scroll_attempts += 1; print(f"    LinkedIn: Scroll intento {scroll_attempts}/{max_scroll_attempts}...")
            # if scroll_attempts == max_scroll_attempts: print("    LinkedIn: Límite de intentos de scroll alcanzado.")

            # --- REVISADO: Parseo HTML ---
            page_html = driver.page_source
            soup = BeautifulSoup(page_html, 'lxml')
            job_divs = soup.find_all('div', attrs={'data-job-id': True})
            print(f"    LinkedIn: {len(job_divs)} divs con data-job-id encontrados en HTML.")

            if not job_divs and page == 1 and total_results_linkedin == 0:
                print("    LinkedIn: No se encontraron divs con data-job-id (confirmado).")
                break
            if not job_divs and page > 1:
                print(f"    LinkedIn: No se encontraron divs con data-job-id en HTML en página {page}.")
                break

            found_on_page, skipped_duplicates_page, skipped_excluded_page, skipped_inclusion_page = 0, 0, 0, 0
            for job_div in job_divs:
                 job_info = parse_job_card_linkedin_from_div(job_div) # Usar la nueva función
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
                        job_info['platform'] = 'LinkedIn'
                        new_jobs_linkedin.append(job_info)
                        found_job_ids.add(job_id)
                        found_on_page += 1
                        processed_titles['included'].append(job_title)
                    elif included and job_id: skipped_duplicates_page += 1
                 # else: print(f"  Advertencia: parse_job_card_linkedin_from_div devolvió None para un div.") # Opcional

            print(f"    LinkedIn: +{found_on_page} nuevas, {skipped_excluded_page} excluidas, {skipped_inclusion_page} no incluidas, {skipped_duplicates_page} duplicadas.")
            skipped_excluded_title_total += skipped_excluded_page
            skipped_inclusion_fail_total += skipped_inclusion_page
            total_added += found_on_page

            # Lógica de paginación
            if page >= max_pages: # Usar max_pages (que ya tiene el límite MAX_LINKEDIN_PAGES aplicado)
                 print(f"    LinkedIn: Se alcanzó la última página procesable ({max_pages}) para '{keyword}'.")
                 keep_paging = False
            elif found_on_page == 0 and skipped_duplicates_page == 0 and page > 1:
                 print(f"    LinkedIn: Página {page} sin nuevas ofertas ni duplicados conocidos. Asumiendo fin de resultados.")
                 keep_paging = False

            if keep_paging:
                page += 1
                print(f"\n--- Esperando {DELAY_BETWEEN_PAGES_SELENIUM} segundos antes de la siguiente página... ---")
                time.sleep(DELAY_BETWEEN_PAGES_SELENIUM)

        except TimeoutException:
            print(f"    LinkedIn: Timeout general en página {page}. Abortando keyword.")
            keep_paging = False
        except WebDriverException as e:
            print(f"    LinkedIn: Error de WebDriver en página {page}: {e}. Abortando script.")
            keep_paging = False
            raise e
        except Exception as e:
            print(f"    LinkedIn: Error general en página {page}: {e}. Abortando keyword.")
            keep_paging = False

    print(f"--- Fin LinkedIn para '{keyword}'. Total nuevas: {total_added} ---")
    return new_jobs_linkedin, processed_titles


# --- Script Principal ---

# 1. Cargar datos existentes y determinar fecha
existing_df = pd.DataFrame(); found_job_ids = set(); last_run_time = None
if os.path.exists(OUTPUT_FILENAME):
    print(f"Cargando datos existentes desde '{OUTPUT_FILENAME}'...")
    try:
        existing_df = pd.read_csv(OUTPUT_FILENAME)
        for col in FINAL_COLUMNS_TO_SAVE:
            if col not in existing_df.columns: existing_df[col] = pd.NA
        if 'job_id' in existing_df.columns:
            existing_df['job_id'] = existing_df['job_id'].astype(str); found_job_ids = set(existing_df['job_id'].dropna().tolist()); print(f"Se cargaron {len(found_job_ids)} IDs existentes.")
        else: print("Advertencia: El archivo CSV existente no tiene columna 'job_id'."); existing_df['job_id'] = pd.Series(dtype='str')
        if 'timestamp_found' in existing_df.columns and not existing_df['timestamp_found'].isnull().all():
            try:
                valid_timestamps = pd.to_datetime(existing_df['timestamp_found'], errors='coerce').dropna()
                if not valid_timestamps.empty:
                    last_run_time = valid_timestamps.max()
                    print(f"Último registro encontrado en CSV: {last_run_time}")
            except Exception as e_ts:
                print(f"Advertencia: Error al procesar timestamps del CSV: {e_ts}")
                last_run_time = None
    except pd.errors.EmptyDataError: print("El archivo CSV existente está vacío."); existing_df = pd.DataFrame(columns=FINAL_COLUMNS_TO_SAVE)
    except Exception as e: print(f"Error al leer archivo CSV: {e}."); existing_df = pd.DataFrame(columns=FINAL_COLUMNS_TO_SAVE); found_job_ids = set()
else: print(f"El archivo '{OUTPUT_FILENAME}' no existe."); existing_df = pd.DataFrame(columns=FINAL_COLUMNS_TO_SAVE)

# Calcular parámetros de fecha (Solo LinkedIn)
f_tpr_param_linkedin = "r604800" # Default 1 semana
if last_run_time:
    time_diff = datetime.now() - last_run_time; days_diff = time_diff.days
    print(f"Última ejecución (según CSV) detectada hace {days_diff} días.")
    if days_diff <= 1: f_tpr_param_linkedin = "r86400" # 1 día
else: print("No se encontró fecha de última ejecución en CSV. Usando default (1 semana).")
print(f"Parámetro de búsqueda LinkedIn: f_TPR={f_tpr_param_linkedin}")

all_new_jobs = []; all_processed_titles = {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}
driver = setup_driver()

print("\n======= INICIANDO SCRAPING LINKEDIN =======")

# Bucle Principal por Keyword (Solo LinkedIn)
try:
    if driver:
        for i, keyword_raw in enumerate(SEARCH_KEYWORDS):
            print(f"\n==================== Keyword {i+1}/{len(SEARCH_KEYWORDS)}: '{keyword_raw}' ====================")
            keyword_linkedin = keyword_raw.replace(' ', '%20')
            new_jobs_linkedin, titles_linkedin = scrape_linkedin_for_keyword(driver, keyword_linkedin, f_tpr_param_linkedin, found_job_ids)
            all_new_jobs.extend(new_jobs_linkedin)
            for key in all_processed_titles: all_processed_titles[key].extend(titles_linkedin[key])
            if i < len(SEARCH_KEYWORDS) - 1:
                print(f"\n--- Esperando {DELAY_BETWEEN_KEYWORDS} segundos antes de la siguiente keyword... ---")
                time.sleep(DELAY_BETWEEN_KEYWORDS)
    else:
        print("ERROR CRÍTICO: No se pudo iniciar el driver de Selenium. El script no puede continuar.")

except WebDriverException as e_wd_global: print(f"\nERROR CRÍTICO DE WEBDRIVER: {e_wd_global}"); print("El scraping de LinkedIn se detuvo.")
except Exception as e_global: print(f"\nERROR GLOBAL INESPERADO: {e_global}"); print("El scraping se detuvo.")
finally:
    if driver: print("\nCerrando conexión con WebDriver remoto..."); print("WebDriver remoto sigue conectado.")

# --- 3. Combinar y Guardar Resultados ---
print("\n======= PROCESANDO RESULTADOS FINALES (LinkedIn) =======")
print("\n--- Reporte de Títulos Procesados (Total) ---")
print(f"Total Incluidos: {len(all_processed_titles['included'])}")
print(f"Total Excluidos (explícito): {len(all_processed_titles['excluded_explicit'])}")
print(f"Total Excluidos (implícito): {len(all_processed_titles.get('excluded_implicit', []))}")

if all_new_jobs:
    print(f"\nSe encontraron {len(all_new_jobs)} ofertas nuevas de LinkedIn en total durante esta ejecución.")
    new_df = pd.DataFrame(all_new_jobs)
    if 'job_id' not in new_df.columns: new_df['job_id'] = pd.NA
    if not existing_df.empty:
        print(f"Combinando {len(new_df)} nuevos con {len(existing_df)} existentes.")
        all_cols_process = list(set(new_df.columns) | set(existing_df.columns) | set(FINAL_COLUMNS_TO_SAVE))
        new_df = new_df.reindex(columns=all_cols_process)
        existing_df = existing_df.reindex(columns=all_cols_process) # Corregido
        combined_df = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        print("No había datos existentes, guardando solo los nuevos.")
        all_cols_process = list(set(new_df.columns) | set(FINAL_COLUMNS_TO_SAVE))
        combined_df = new_df.reindex(columns=all_cols_process)
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
        for col in FINAL_COLUMNS_TO_SAVE:
            if col not in combined_df.columns:
                combined_df[col] = pd.NA
        combined_df_to_save = combined_df[FINAL_COLUMNS_TO_SAVE]
        combined_df_to_save.to_csv(OUTPUT_FILENAME, index=False, encoding='utf-8-sig')
        print(f"\nDatos de LinkedIn guardados exitosamente en '{OUTPUT_FILENAME}' ({len(combined_df_to_save)} ofertas en total).")
    except Exception as e:
        print(f"\nError al guardar el archivo CSV final: {e}")
elif not all_new_jobs and not existing_df.empty:
    print("\nNo se encontraron ofertas nuevas en esta ejecución. El archivo existente no se modificará.")
    count_existing = len(existing_df) if existing_df is not None else 0
    print(f"El archivo '{OUTPUT_FILENAME}' contiene {count_existing} ofertas.")
else:
    print("\nNo se encontraron ofertas nuevas y no existía archivo previo.")
print("\n======= FIN DEL SCRIPT =======")