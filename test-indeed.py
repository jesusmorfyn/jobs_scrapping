from bs4 import BeautifulSoup
import time
import re
import pandas as pd
import os
from datetime import datetime

DELAY_BETWEEN_PAGES = 10
RETRY_DELAY = 10
REQUEST_TIMEOUT = 60

SEARCH_KEYWORDS = [
    "devops",
    "cloud",
    "aws",
    "gcp",
    # "sre",
    "site+reliability+engineer",
    "mlops",
    # "infrastructure",
    # "automation",
    # "ci/cd",
    # "kubernetes",
    # "docker",
    # "terraform",
    # "ansible",
    # "platform engineer"
]
BASE_URL_TEMPLATE_INDEED = "https://mx.indeed.com/jobs?q={keyword}&l=Remote&sc=0kf%3Aattr%28DSQF7%29%3B&sort=date&start={start}"
OUTPUT_FILENAME = "indeed_multi_keyword_remoto_jobs.csv"
INDEED_PAGE_INCREMENT = 10

EXCLUDE_TITLE_KEYWORDS = [
    "software", "development", "data", ".net", "python", "quality", "security", "salesforce", "desarroll", "qa", "ruby", "test", "datos", "java", "fullstack", "sap"
]

INCLUDE_TITLE_KEYWORDS = [
    "devops", "sre", "cloud", "mlops", "platform engineer", "infrastructure", "systems engineer",
    "site reliability", "ingeniero de sistemas", "ingeniero de plataforma", "ingeniero de la nube", "nube",
    "automation", "automatización", "ci/cd", "continuous integration", "continuous delivery", "pipeline",
    "aws", "azure", "gcp", "google cloud", "amazon web services", "cloud native", "computación en la nube",
    "kubernetes", "k8s", "docker", "containerization", "contenedores", "serverless", "serverless computing",
    "orquestación", "virtualización",
    "terraform", "ansible", "jenkins", "gitlab", "puppet", "chef", "openstack", "infrastructure as code", "iac",
    "configuración como código",
    "prometheus", "grafana", "observability", "observabilidad", "monitoring", "monitorización", "logging", "alerting", "alertas",
    "microservices", "microservicios", "deployment", "despliegue", "release", "escalability", "escalabilidad", "resilience", "resiliencia",
    "devsecops", "seguridad en la nube", "dataops", "integración continua", "entrega continua",
    "automated deployment", "pipeline de despliegue", "orquestación de contenedores", "gestión de infraestructura",
    "failover", "disaster recovery"
]

# --- Selenium Imports ---
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
from selenium.webdriver.chrome.options import Options as ChromeOptions

# --- Funciones Selenium ---
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
        exit(1)

def close_cookie_popup(driver, wait_short):
    """Intenta encontrar y cerrar el pop-up de cookies."""
    try:
        xpath_accept = "//button[contains(translate(., 'ACEPTAR COOKIES', 'aceptar cookies'), 'aceptar cookies') or contains(translate(., 'ACCEPT', 'accept'), 'accept') or contains(translate(., 'ENTENDIDO', 'entendido'), 'entendido')]"
        cookie_button = wait_short.until(EC.element_to_be_clickable((By.XPATH, xpath_accept)))
        cookie_button.click()
        print("Pop-up de cookies cerrado.")
        time.sleep(1) # Pequeña pausa después de cerrar
    except TimeoutException:
        pass # Es normal si no aparece
    except Exception as e:
        print(f"Error al intentar cerrar pop-up de cookies: {e}")

# --- Funciones Auxiliares ---
# ELIMINADAS: read_last_run_time y write_last_run_time
# parse_job_card (sin cambios)
# ... (código de parse_job_card idéntico al anterior) ...
def parse_job_card(card_soup):
    """Extrae la información de interés de una tarjeta de trabajo de Indeed."""
    job_data = {}
    job_id = None
    try:
        # Intenta obtener el ID desde el div principal o el enlace del título
        main_div = card_soup.find('div', class_='cardOutline')
        a_tag = card_soup.find('a', class_='jcs-JobTitle')

        if main_div and main_div.get('data-jk'):
            job_id = main_div.get('data-jk')
        elif a_tag and a_tag.get('data-jk'):
             job_id = a_tag.get('data-jk')

        # Si no hay ID, no podemos procesar la tarjeta
        if not job_id:
            # print("Advertencia: No se pudo encontrar job_id para una tarjeta.")
            return None
        job_data['job_id'] = str(job_id)

        # --- Título ---
        title_tag = card_soup.find('span', id=lambda x: x and x.startswith('jobTitle-'))
        if title_tag:
             job_data['title'] = title_tag.get_text(strip=True)
        else: # Fallback por si cambia el ID
             h2_title = card_soup.find('h2', class_='jobTitle')
             span_inside = h2_title.find('span') if h2_title else None
             job_data['title'] = span_inside.get_text(strip=True) if span_inside else "No especificado"

        # --- Compañía ---
        company_tag = card_soup.find('span', {'data-testid': 'company-name'})
        job_data['company'] = company_tag.get_text(strip=True) if company_tag else "No especificado"

        # --- Ubicación ---
        location_tag = card_soup.find('div', {'data-testid': 'text-location'})
        job_data['location'] = location_tag.get_text(strip=True) if location_tag else "No especificado"

        # --- Salario (Intentos múltiples) ---
        salary_data = "No especificado"
        # Intento 1: Test ID específico
        salary_tag_testid = card_soup.find('div', {'data-testid': 'attribute_snippet_testid'}, class_='salary-snippet-container')
        if salary_tag_testid:
            salary_data = salary_tag_testid.get_text(strip=True)
        else:
            # Intento 2: Contenedor de metadatos general y buscar texto con $ y periodo
            metadata_container = card_soup.find('div', class_='jobMetaDataGroup')
            if metadata_container:
                 possible_salaries = metadata_container.find_all('div') # Buscar divs dentro
                 for div in possible_salaries:
                     text = div.get_text(strip=True).lower()
                     if '$' in text and ('mes' in text or 'año' in text or 'hora' in text or 'year' in text or 'month' in text or 'hour' in text):
                          salary_data = div.get_text(strip=True)
                          break # Tomar el primero que coincida
        job_data['salary'] = salary_data

        # --- Fecha de Publicación (Intentos múltiples) ---
        posted_date_data = "No encontrado"
        # Intento 1: Span con clase 'date' (común para fechas relativas "hace X días")
        date_tag_relative = card_soup.find('span', class_='date')
        if date_tag_relative:
            posted_date_data = date_tag_relative.get_text(strip=True)
        else:
            # Intento 2: Buscar dentro del contenedor de metadatos por patrones de texto
            metadata_container_date = card_soup.find('div', class_='jobMetaDataGroup')
            if metadata_container_date:
                possible_dates = metadata_container_date.find_all(['span', 'div']) # Buscar spans y divs
                for tag in possible_dates:
                     text = tag.get_text(strip=True).lower()
                     # Patrones comunes: "hace X días/horas", "Publicado hoy/ayer", "X days ago"
                     if re.search(r'\b(hace|posted|publicado)\b.*\b(d[íi]a|hora|semana|day|hour|week)s?\b', text, re.IGNORECASE) or \
                        re.match(r'\d+\+?\s+(d[íi]as?|days?)\s+ago', text, re.IGNORECASE) or \
                        re.search(r'\b(today|ayer)\b', text, re.IGNORECASE):
                          posted_date_data = tag.get_text(strip=True)
                          break # Tomar la primera coincidencia razonable
        job_data['posted_date'] = posted_date_data


        # --- Enlace ---
        job_data['link'] = f"https://mx.indeed.com/viewjob?jk={job_id}"

        # Verificar que tenemos al menos ID y Título antes de devolver
        return job_data if job_data.get('job_id') and job_data.get('title') != "No especificado" else None

    except Exception as e:
        print(f"Error procesando tarjeta de Indeed: {e}")
        # Intentar obtener ID para depuración si falló antes
        error_id = 'N/A'
        try:
            if not job_id: # Si el ID no se obtuvo al principio
                a_tag_err = card_soup.find('a', class_='jcs-JobTitle')
                if a_tag_err: error_id = a_tag_err.get('data-jk', 'N/A')
        except: pass
        print(f"  Tarjeta con ID (aprox): {job_id or error_id}")
        # Considera loggear la tarjeta completa: print(card_soup.prettify())
        return None

# --- Script Principal ---

# 1. Cargar datos existentes
existing_df = pd.DataFrame()
found_job_ids = set()
expected_columns = ['job_id', 'title', 'company', 'salary', 'location', 'posted_date', 'timestamp_found', 'link']
last_run_time = None # MODIFICADO: Inicializar

if os.path.exists(OUTPUT_FILENAME):
    print(f"Cargando datos existentes desde '{OUTPUT_FILENAME}'...")
    try:
        existing_df = pd.read_csv(OUTPUT_FILENAME)
        for col in expected_columns:
            if col not in existing_df.columns:
                existing_df[col] = pd.NA
        if 'job_id' in existing_df.columns:
            existing_df['job_id'] = existing_df['job_id'].astype(str)
            found_job_ids = set(existing_df['job_id'].dropna().tolist())
            print(f"Se cargaron {len(found_job_ids)} IDs existentes de Indeed.")
        else:
            print(f"Advertencia: '{OUTPUT_FILENAME}' no tiene columna 'job_id'.")
            existing_df['job_id'] = pd.Series(dtype='str')

        # --- NUEVO: Intentar obtener el último timestamp del CSV ---
        if 'timestamp_found' in existing_df.columns and not existing_df['timestamp_found'].isnull().all():
            try:
                valid_timestamps = pd.to_datetime(existing_df['timestamp_found'], errors='coerce').dropna()
                if not valid_timestamps.empty:
                    last_run_time = valid_timestamps.max()
                    print(f"Último registro encontrado en CSV (Indeed): {last_run_time}")
            except Exception as e_ts:
                print(f"Advertencia: Error al procesar timestamps del CSV (Indeed): {e_ts}")
                last_run_time = None
        # --- Fin Nuevo ---

    except pd.errors.EmptyDataError:
        print(f"El archivo '{OUTPUT_FILENAME}' está vacío.")
        existing_df = pd.DataFrame(columns=expected_columns)
    except Exception as e:
        print(f"Error al leer '{OUTPUT_FILENAME}': {e}.")
        existing_df = pd.DataFrame(columns=expected_columns)
        found_job_ids = set()
else:
    print(f"El archivo '{OUTPUT_FILENAME}' no existe. Se creará uno nuevo.")
    existing_df = pd.DataFrame(columns=expected_columns)

# --- Determinar parámetro fromage ---
fromage_param = 14 # Default

if last_run_time:
    time_diff_indeed = datetime.now() - last_run_time
    days_diff_indeed = time_diff_indeed.days
    print(f"Última ejecución de Indeed (según CSV) detectada hace {days_diff_indeed} días.")
    if days_diff_indeed <= 1: fromage_param = 1
    elif days_diff_indeed <= 3: fromage_param = 3
    elif days_diff_indeed <= 7: fromage_param = 7
    # else: se mantiene 14
else:
    print("No se encontró fecha de última ejecución en CSV (Indeed). Usando default fromage=14.")

print(f"Parámetro de búsqueda por tiempo establecido: fromage={fromage_param}")

new_jobs_list = []
processed_titles_indeed = {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}

# --- Inicializar Driver ---
driver = setup_driver()
wait_long = WebDriverWait(driver, REQUEST_TIMEOUT)
wait_short = WebDriverWait(driver, 3) # Reducir espera corta para chequeo rápido

print("======= INICIANDO SCRAPING DE OFERTAS INDEED (CON SELENIUM) =======")

# 2. Iniciar Scraping
try:
    for i, keyword in enumerate(SEARCH_KEYWORDS):
        # MODIFICADO: Añadir fromage a la URL base
        base_url_with_fromage = f"{BASE_URL_TEMPLATE_INDEED}&fromage={fromage_param}"
        print(f"\n========== Procesando Búsqueda {i+1}/{len(SEARCH_KEYWORDS)} para: '{keyword}' (fromage={fromage_param}) ==========")
        page = 1
        keep_paging = True
        skipped_excluded_title_total = 0
        skipped_inclusion_fail_total = 0

        while keep_paging:
            start_index = (page - 1) * INDEED_PAGE_INCREMENT
            # MODIFICADO: Construir URL
            current_url = base_url_with_fromage.format(keyword=keyword, start=start_index)
            print(f"\n--- Scraping página {page} para '{keyword}' (start={start_index}) ---")
            print(f"URL: {current_url}")

            try:
                driver.get(current_url)
                close_cookie_popup(driver, wait_short)

                # --- NUEVO: Chequeo Rápido de "Sin Resultados" ---
                no_results_found = False
                try:
                    # Intentar localizar un elemento que indique cero resultados
                    # Ajusta el selector XPath según lo que veas en la página real de "sin resultados" de Indeed MX
                    # Ejemplo: buscar un div que contenga el texto específico
                    no_results_xpath = "//*[contains(text(), 'no produjo ningún resultado de empleos nuevos') or contains(text(), 'did not match any jobs')]"
                    # Usar find_elements con espera corta para no bloquear si hay resultados
                    WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.XPATH, "//*"))) # Esperar que algo cargue
                    no_results_elements = driver.find_elements(By.XPATH, no_results_xpath)

                    if no_results_elements:
                        print(f"Detectado mensaje de 'Sin resultados' para '{keyword}'. Saltando keyword.")
                        no_results_found = True
                        break # Salir del bucle 'while keep_paging' para esta keyword

                except TimeoutException:
                    # Es normal si no se encuentra el mensaje de "sin resultados", significa que SÍ hay resultados (o la página aún no carga)
                    pass
                except Exception as e_nores:
                    print(f"Advertencia: Error menor al buscar mensaje 'sin resultados': {e_nores}")
                    # Continuar de todas formas intentando buscar las tarjetas

                if no_results_found:
                    continue # Salta el resto del código de la página y va al siguiente keyword

                # --- Fin Chequeo Rápido ---


                print("Esperando que la lista de trabajos cargue...")
                job_list_container = None
                try:
                    job_list_container = wait_long.until(
                        EC.presence_of_element_located((By.ID, "mosaic-provider-jobcards"))
                    )
                    wait_long.until(
                        EC.visibility_of_element_located((By.CSS_SELECTOR, "div#mosaic-provider-jobcards li div.cardOutline"))
                    )
                    print("Contenedor y al menos una tarjeta de trabajo encontrados.")
                    time.sleep(2)
                except TimeoutException:
                    print(f"Timeout esperando la lista/tarjetas de trabajos en la página {page}.")
                    # Aquí SÍ queremos guardar screenshot, porque no fue la página de "sin resultados"
                    try:
                         screenshot_filename = f"debug_timeout_page_{page}_{keyword.replace(' ', '_')}.png"
                         driver.save_screenshot(screenshot_filename)
                         print(f"Screenshot guardado en: {screenshot_filename}")
                    except Exception as img_e:
                         print(f"No se pudo guardar el screenshot: {img_e}")

                    if page == 1: # Si falló en la primera página (y no era "sin resultados")
                         print(f"Error cargando resultados iniciales para '{keyword}' (no era página 'sin resultados'). Saltando keyword.")
                    else: # Si falló en páginas posteriores
                         print(f"Timeout en página {page}. Asumiendo fin de resultados para esta keyword.")
                    keep_paging = False
                    continue # Saltar al siguiente ciclo del while (que terminará)
                except NoSuchElementException:
                     print(f"Error crítico: No se encontró el contenedor 'mosaic-provider-jobcards' (después del chequeo 'sin resultados'). Saltando keyword.")
                     keep_paging = False
                     continue
                except Exception as e_wait:
                    print(f"Error inesperado durante la espera de elementos en página {page}: {e_wait}. Deteniendo para '{keyword}'.")
                    keep_paging = False
                    continue

                # ... (resto del procesamiento de tarjetas, filtros, adición con timestamp - SIN CAMBIOS) ...
                page_html = driver.page_source
                soup = BeautifulSoup(page_html, 'lxml') # Usar lxml si está instalado
                job_list_container_soup = soup.find('div', id='mosaic-provider-jobcards')

                job_cards_li = []
                if job_list_container_soup:
                    ul_list = job_list_container_soup.find('ul', class_='css-1faftfv')
                    if not ul_list: ul_list = job_list_container_soup.find('ul')
                    if ul_list:
                        job_cards_li = [li for li in ul_list.find_all('li', recursive=False) if li.find('div', class_='cardOutline')]
                else:
                     print("Advertencia: No se encontró el contenedor 'mosaic-provider-jobcards' en el HTML parseado.")

                current_page_job_count = len(job_cards_li)
                print(f"Se encontraron {current_page_job_count} tarjetas de trabajo válidas en el HTML de la página {page}.")

                found_on_page = 0
                skipped_duplicates = 0
                skipped_excluded_title_page = 0
                skipped_inclusion_fail_page = 0

                for card_li in job_cards_li:
                    job_info = parse_job_card(card_li)
                    if job_info:
                        job_id = job_info.get('job_id')
                        job_title = job_info.get('title', '')
                        job_title_lower = job_title.lower()

                        # Filtro de Exclusión
                        excluded = False
                        for exclude_word in EXCLUDE_TITLE_KEYWORDS:
                            if exclude_word in job_title_lower:
                                processed_titles_indeed['excluded_explicit'].append(f"{job_title} (Excl: {exclude_word})")
                                excluded = True
                                skipped_excluded_title_page += 1
                                break
                        if excluded: continue

                        # Filtro de Inclusión
                        included = False
                        if INCLUDE_TITLE_KEYWORDS:
                            for include_word in INCLUDE_TITLE_KEYWORDS:
                                if include_word in job_title_lower:
                                    included = True
                                    break
                            if not included:
                                processed_titles_indeed['excluded_implicit'].append(f"{job_title}")
                                skipped_inclusion_fail_page += 1
                                continue
                        else:
                            included = True

                        # Deduplicación y Adición con Timestamp
                        if included and job_id and job_id not in found_job_ids:
                            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            job_info['timestamp_found'] = timestamp_str
                            new_jobs_list.append(job_info)
                            found_job_ids.add(job_id)
                            found_on_page += 1
                            processed_titles_indeed['included'].append(job_title)
                        elif included and job_id:
                            skipped_duplicates += 1

                print(f"Se añadieron {found_on_page} ofertas nuevas.")
                if skipped_excluded_title_page > 0:
                    print(f"Se descartaron {skipped_excluded_title_page} por exclusión de título.")
                    skipped_excluded_title_total += skipped_excluded_title_page
                if skipped_inclusion_fail_page > 0:
                    print(f"Se descartaron {skipped_inclusion_fail_page} por fallo de inclusión de título.")
                    skipped_inclusion_fail_total += skipped_inclusion_fail_page
                if skipped_duplicates > 0:
                    print(f"Se omitieron {skipped_duplicates} ofertas duplicadas.")


                # Comprobar enlace "Siguiente" (sin cambios)
                try:
                    next_page_links = driver.find_elements(By.CSS_SELECTOR, "a[data-testid='pagination-page-next']")
                    if not next_page_links:
                         print(f"\nNo se encontró el enlace 'Página siguiente'. Asumiendo fin de resultados para '{keyword}'.")
                         keep_paging = False
                except NoSuchElementException:
                     print(f"Error buscando el enlace 'Página siguiente'. Asumiendo fin para '{keyword}'.")
                     keep_paging = False
                except Exception as e_nav:
                     print(f"Error inesperado al buscar paginación: {e_nav}. Deteniendo para '{keyword}'.")
                     keep_paging = False

                if keep_paging:
                     page += 1
                     print(f"Esperando {DELAY_BETWEEN_PAGES} segundo(s) antes de la página {page}...")
                     time.sleep(DELAY_BETWEEN_PAGES)

            # ... (Manejo de excepciones del bucle interno SIN CAMBIOS) ...
            except TimeoutException:
                 print(f"Error: Timeout general en la página {page} para '{keyword}'. Deteniendo para esta keyword.")
                 keep_paging = False
            except NoSuchElementException as e:
                 print(f"Error: No se encontró un elemento esencial POST-carga en {page} para '{keyword}': {e}. Deteniendo para esta keyword.")
                 keep_paging = False
            except WebDriverException as e:
                 print(f"Error de WebDriver en {page} para '{keyword}': {e}")
                 print("Deteniendo el scraping para esta keyword debido a error del driver.")
                 keep_paging = False
            except Exception as e:
                print(f"Error general procesando {page} para '{keyword}': {e}")
                print("Deteniendo para esta keyword debido a error inesperado.")
                keep_paging = False

        print(f"\nResumen para '{keyword}':")
        if skipped_excluded_title_total > 0: print(f"  Total descartados por exclusión: {skipped_excluded_title_total}")
        if skipped_inclusion_fail_total > 0: print(f"  Total descartados por inclusión: {skipped_inclusion_fail_total}")

        # --- NUEVO: Pausa entre keywords también para Indeed ---
        if i < len(SEARCH_KEYWORDS) - 1:
            print(f"\nEsperando {DELAY_BETWEEN_PAGES} segundos antes de la siguiente keyword...")
            time.sleep(DELAY_BETWEEN_PAGES) # Reutilizamos la constante definida en OCC o define una nueva

except Exception as global_e:
    print(f"\nError GOBAL durante la ejecución de Indeed: {global_e}")
finally:
    if 'driver' in locals() and driver is not None:
        print("\nCerrando conexión con WebDriver remoto...")
        # driver.quit() # Comentado para no cerrar navegador manual
        print("WebDriver remoto sigue conectado. Ciérralo manualmente si es necesario.")


# --- 3. Combinar y Guardar Resultados ---
# ... (sin cambios, ya no escribe timestamp aquí) ...
print("\n======= PROCESANDO RESULTADOS FINALES INDEED =======")

print("\n--- Reporte de Títulos Procesados Indeed ---")
print(f"Total Incluidos: {len(processed_titles_indeed['included'])}")
print(f"Total Excluidos (por keyword explícita): {len(processed_titles_indeed['excluded_explicit'])}")
print(f"Total Excluidos (por fallo de inclusión): {len(processed_titles_indeed.get('excluded_implicit', []))}")


if new_jobs_list:
    print(f"\nSe encontraron {len(new_jobs_list)} ofertas nuevas de Indeed en total durante esta ejecución.")
    new_df = pd.DataFrame(new_jobs_list)
    if 'job_id' in new_df.columns:
        new_df['job_id'] = new_df['job_id'].astype(str)
    else:
        print("Advertencia: El nuevo DataFrame Indeed no contiene la columna 'job_id'.")
        new_df['job_id'] = pd.Series(dtype='str')

    if not existing_df.empty:
        print(f"Combinando {len(new_jobs_list)} nuevos con {len(existing_df)} existentes de Indeed.")
        all_cols = list(set(new_df.columns) | set(existing_df.columns) | set(expected_columns))
        new_df = new_df.reindex(columns=all_cols)
        existing_df = existing_df.reindex(columns=all_cols)
        combined_df = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        print("No había datos existentes de Indeed, guardando solo los nuevos.")
        combined_df = new_df

    initial_rows = len(combined_df)
    if 'job_id' in combined_df.columns:
        combined_df['job_id'] = combined_df['job_id'].astype(str)
        combined_df.drop_duplicates(subset=['job_id'], keep='first', inplace=True)
        final_rows = len(combined_df)
        if initial_rows > final_rows:
             print(f"Se eliminaron {initial_rows - final_rows} duplicados durante la combinación final de Indeed.")
    else:
         print("Advertencia: No se pudo realizar la deduplicación final de Indeed por falta de columna 'job_id'.")

    try:
        columns_order = ['job_id', 'title', 'company', 'salary', 'location', 'posted_date', 'timestamp_found', 'link']
        for col in columns_order:
            if col not in combined_df.columns:
                combined_df[col] = pd.NA
        combined_df = combined_df[columns_order]

        combined_df.to_csv(OUTPUT_FILENAME, index=False, encoding='utf-8-sig')
        print(f"\nDatos de Indeed actualizados guardados exitosamente en '{OUTPUT_FILENAME}' ({len(combined_df)} ofertas en total).")

    except Exception as e:
        print(f"\nError al guardar el archivo CSV final de Indeed: {e}")

elif not new_jobs_list and not existing_df.empty:
    print("\nNo se encontraron ofertas nuevas de Indeed en esta ejecución. El archivo existente no se modificará.")
    count_existing = len(existing_df) if existing_df is not None else 0
    print(f"El archivo '{OUTPUT_FILENAME}' contiene {count_existing} ofertas.")
else:
    print("\nNo se encontraron ofertas nuevas de Indeed y no existía archivo previo.")


print("\n======= FIN DEL SCRIPT =======")