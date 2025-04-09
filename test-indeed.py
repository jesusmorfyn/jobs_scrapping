# import requests
from bs4 import BeautifulSoup
import time
# import math
import re
import pandas as pd
import sys
import os
from datetime import datetime # NUEVO: Importar datetime

# --- Selenium Imports ---
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
from selenium.webdriver.chrome.options import Options as ChromeOptions

# --- Funciones Selenium ---
# setup_driver_remote (sin cambios)
def setup_driver_remote():
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

# close_cookie_popup (sin cambios)
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


# --- Configuración General ---
DELAY_BETWEEN_PAGES = 10 # Aumentado ligeramente
RETRY_DELAY = 10
REQUEST_TIMEOUT = 60 # segundos

# --- Configuración Específica para INDEED ---
SEARCH_KEYWORDS_INDEED = [ # <-- Tu lista original
    "devops", "cloud", "aws", "gcp", "sre", "site reliability engineer",
    "mlops", "ci/cd", "kubernetes",
    # "docker", "terraform", "ansible", "platform engineer", "infrastructure", "automation",
]
BASE_URL_TEMPLATE_INDEED = "https://mx.indeed.com/jobs?q={keyword}&l=Remote&fromage=14&sc=0kf%3Aattr%28DSQF7%29%3B&sort=date&start={start}"
OUTPUT_FILENAME_INDEED = "indeed_multi_keyword_remoto_jobs.csv" # Nombre actualizado
INDEED_PAGE_INCREMENT = 10

# --- Filtros de Título para INDEED (minúsculas) ---
EXCLUDE_TITLE_KEYWORDS = [ # <-- Tu lista original
    "software", "development", "data", ".net", "python", "quality", "security", 
    "salesforce", "desarroll", "qa", "ruby", "test", "datos", "fullstack" # "azure"
]
INCLUDE_TITLE_KEYWORDS = [ # <-- Tu lista original
    "devops", "sre", "cloud", "mlops", "platform", "infrastructure",
    "site reliability", "plataforma","nube",
    "automation", "automatización", "ci/cd", "pipeline", "aws", "azure",
    "gcp", "google cloud", "amazon web services", "cloud native", "kubernetes",
    "k8s", "docker", "container", "contenedor", "serverless", "terraform",
    "ansible", "jenkins", "gitlab", "iac", "monitoring", "monitorización",
    "observability", "observabilidad", "prometheus", "grafana", "architect", "arquitecto"
]

# --- Función parse_indeed_job_card (sin cambios) ---
def parse_indeed_job_card(card_soup):
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
existing_df_indeed = pd.DataFrame()
found_job_ids_indeed = set()
# NUEVO: Definir columnas esperadas
expected_columns_indeed = ['job_id', 'title', 'company', 'salary', 'location', 'posted_date', 'timestamp_found', 'link']

if os.path.exists(OUTPUT_FILENAME_INDEED):
    print(f"Cargando datos existentes desde '{OUTPUT_FILENAME_INDEED}'...")
    try:
        existing_df_indeed = pd.read_csv(OUTPUT_FILENAME_INDEED)
        # Asegurar columnas
        for col in expected_columns_indeed:
            if col not in existing_df_indeed.columns:
                existing_df_indeed[col] = pd.NA
        # Cargar IDs
        if 'job_id' in existing_df_indeed.columns:
            existing_df_indeed['job_id'] = existing_df_indeed['job_id'].astype(str)
            found_job_ids_indeed = set(existing_df_indeed['job_id'].dropna().tolist())
            print(f"Se cargaron {len(found_job_ids_indeed)} IDs existentes de Indeed.")
        else:
            print(f"Advertencia: '{OUTPUT_FILENAME_INDEED}' no tiene columna 'job_id'.")

    except pd.errors.EmptyDataError:
        print(f"El archivo '{OUTPUT_FILENAME_INDEED}' está vacío.")
        existing_df_indeed = pd.DataFrame(columns=expected_columns_indeed)
    except Exception as e:
        print(f"Error al leer '{OUTPUT_FILENAME_INDEED}': {e}.")
        existing_df_indeed = pd.DataFrame(columns=expected_columns_indeed)
        found_job_ids_indeed = set()
else:
    print(f"El archivo '{OUTPUT_FILENAME_INDEED}' no existe. Se creará uno nuevo.")
    existing_df_indeed = pd.DataFrame(columns=expected_columns_indeed)


new_jobs_list_indeed = []
processed_titles_indeed = {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}

# --- Inicializar Driver ---
driver = setup_driver_remote()
wait_long = WebDriverWait(driver, REQUEST_TIMEOUT)
wait_short = WebDriverWait(driver, 5)

print("======= INICIANDO SCRAPING DE OFERTAS INDEED (CON SELENIUM) =======")

# 2. Iniciar Scraping
try:
    for keyword in SEARCH_KEYWORDS_INDEED:
        print(f"\n========== Procesando Búsqueda Indeed para: '{keyword}' ==========")
        page = 1
        keep_paging = True
        # NUEVO: Contadores por keyword
        skipped_excluded_title_total = 0
        skipped_inclusion_fail_total = 0

        while keep_paging:
            start_index = (page - 1) * INDEED_PAGE_INCREMENT
            current_url = BASE_URL_TEMPLATE_INDEED.format(keyword=keyword, start=start_index)
            print(f"\n--- Scraping página {page} para '{keyword}' (start={start_index}) ---")
            print(f"URL: {current_url}")

            try:
                driver.get(current_url)
                close_cookie_popup(driver, wait_short)

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
                    try:
                         screenshot_filename = f"debug_timeout_page_{page}_{keyword.replace(' ', '_')}.png"
                         driver.save_screenshot(screenshot_filename)
                         print(f"Screenshot guardado en: {screenshot_filename}")
                    except Exception as img_e:
                         print(f"No se pudo guardar el screenshot: {img_e}")
                    if page == 1:
                        print(f"No se encontraron resultados iniciales visibles para '{keyword}'. Saltando keyword.")
                    else:
                        print(f"Timeout en página {page}. Asumiendo fin de resultados para esta keyword.")
                    keep_paging = False
                    continue
                except NoSuchElementException:
                     print(f"Error crítico: No se encontró el contenedor principal 'mosaic-provider-jobcards' en la página {page}. Saltando keyword.")
                     keep_paging = False
                     continue
                except Exception as e_wait:
                    print(f"Error inesperado durante la espera de elementos en página {page}: {e_wait}. Deteniendo para '{keyword}'.")
                    keep_paging = False
                    continue

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
                    job_info = parse_indeed_job_card(card_li)
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
                        if included and job_id and job_id not in found_job_ids_indeed:
                            # NUEVO: Obtener y añadir timestamp
                            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            job_info['timestamp_found'] = timestamp_str
                            # --- Fin Nuevo ---
                            new_jobs_list_indeed.append(job_info)
                            found_job_ids_indeed.add(job_id)
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

                # Comprobar enlace "Siguiente"
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

        # --- NUEVO: Imprimir resumen total de la keyword (opcional) ---
        print(f"\nResumen para '{keyword}':")
        if skipped_excluded_title_total > 0: print(f"  Total descartados por exclusión: {skipped_excluded_title_total}")
        if skipped_inclusion_fail_total > 0: print(f"  Total descartados por inclusión: {skipped_inclusion_fail_total}")


finally:
    if 'driver' in locals() and driver is not None:
        print("\nCerrando WebDriver...")
        try:
            # No usar quit() si nos conectamos remotamente a un navegador que queremos mantener abierto
            # driver.quit()
            print("WebDriver remoto sigue conectado. Ciérralo manualmente si es necesario.")
        except Exception as e:
            print(f"Error al intentar cerrar WebDriver (puede ignorarse si es conexión remota): {e}")


# --- 3. Combinar y Guardar Resultados ---
print("\n======= PROCESANDO RESULTADOS FINALES INDEED =======")

print("\n--- Reporte de Títulos Procesados Indeed ---") # Mensaje actualizado
print(f"Total Incluidos: {len(processed_titles_indeed['included'])}")
print(f"Total Excluidos (por keyword explícita): {len(processed_titles_indeed['excluded_explicit'])}")
print(f"Total Excluidos (por fallo de inclusión): {len(processed_titles_indeed.get('excluded_implicit', []))}")


if new_jobs_list_indeed:
    print(f"\nSe encontraron {len(new_jobs_list_indeed)} ofertas nuevas de Indeed en total durante esta ejecución.")
    new_df_indeed = pd.DataFrame(new_jobs_list_indeed)
    if 'job_id' in new_df_indeed.columns:
        new_df_indeed['job_id'] = new_df_indeed['job_id'].astype(str)
    else:
        print("Advertencia: El nuevo DataFrame Indeed no contiene la columna 'job_id'.")
        new_df_indeed['job_id'] = pd.Series(dtype='str')


    if not existing_df_indeed.empty:
        print(f"Combinando {len(new_jobs_list_indeed)} nuevos con {len(existing_df_indeed)} existentes de Indeed.")
        # Asegurar columnas consistentes
        all_cols = list(set(new_df_indeed.columns) | set(existing_df_indeed.columns) | set(expected_columns_indeed))
        new_df_indeed = new_df_indeed.reindex(columns=all_cols)
        existing_df_indeed = existing_df_indeed.reindex(columns=all_cols)
        combined_df_indeed = pd.concat([existing_df_indeed, new_df_indeed], ignore_index=True) # Existentes primero
    else:
        print("No había datos existentes de Indeed, guardando solo los nuevos.")
        combined_df_indeed = new_df_indeed

    initial_rows = len(combined_df_indeed)
    if 'job_id' in combined_df_indeed.columns:
        combined_df_indeed['job_id'] = combined_df_indeed['job_id'].astype(str)
        combined_df_indeed.drop_duplicates(subset=['job_id'], keep='first', inplace=True) # Mantener primera (existente)
        final_rows = len(combined_df_indeed)
        if initial_rows > final_rows:
             print(f"Se eliminaron {initial_rows - final_rows} duplicados durante la combinación final de Indeed.")
    else:
         print("Advertencia: No se pudo realizar la deduplicación final de Indeed por falta de columna 'job_id'.")

    try:
        # Orden de columnas actualizado
        columns_order = ['job_id', 'title', 'company', 'salary', 'location', 'posted_date', 'timestamp_found', 'link']
        for col in columns_order:
            if col not in combined_df_indeed.columns:
                combined_df_indeed[col] = pd.NA
        combined_df_indeed = combined_df_indeed[columns_order]

        combined_df_indeed.to_csv(OUTPUT_FILENAME_INDEED, index=False, encoding='utf-8-sig')
        print(f"\nDatos de Indeed actualizados guardados exitosamente en '{OUTPUT_FILENAME_INDEED}' ({len(combined_df_indeed)} ofertas en total).")
    except Exception as e:
        print(f"\nError al guardar el archivo CSV final de Indeed: {e}")

elif not new_jobs_list_indeed and not existing_df_indeed.empty:
    print("\nNo se encontraron ofertas nuevas de Indeed en esta ejecución. El archivo existente no se modificará.")
    count_existing = len(existing_df_indeed) if existing_df_indeed is not None else 0
    print(f"El archivo '{OUTPUT_FILENAME_INDEED}' contiene {count_existing} ofertas.")
else:
    print("\nNo se encontraron ofertas nuevas de Indeed y no existía archivo previo.")


print("\n======= FIN DEL SCRIPT =======")