from bs4 import BeautifulSoup
import time
import re
import pandas as pd
import os

# --- Selenium Imports ---
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
from selenium.webdriver.chrome.options import Options as ChromeOptions

def setup_driver_remote():
    print("Conectando a la instancia de Chrome en modo depuración remota...")
    chrome_options = ChromeOptions()
    # Establece la dirección del debugger (la misma que usaste al lanzar Chrome)
    chrome_options.add_experimental_option("debuggerAddress", "localhost:9222")

    try:
        # No se crea una nueva instancia, se conecta a la ya abierta
        driver = webdriver.Chrome(options=chrome_options)
        print("Conectado a la instancia remota de Chrome.")
        return driver
    except Exception as e:
        print(f"Error al conectar con la instancia remota de Chrome: {e}")
        exit(1)

# --- Configuración General ---
DELAY_BETWEEN_PAGES = 10
RETRY_DELAY = 10
# Aumentado un poco el timeout global para la espera de elementos
REQUEST_TIMEOUT = 60 # segundos

# --- Configuración Específica para INDEED ---
SEARCH_KEYWORDS_INDEED = [
    "devops", "cloud", "aws", "gcp", "sre", "site reliability engineer",
    "mlops", "ci/cd", "kubernetes",
    # "docker", "terraform", "ansible", "platform engineer", "infrastructure", "automation",
]
# URL Template ajustada para incluir 'Remote' como ubicación directamente
# Asegúrate que esta URL base es la correcta para empezar en start=0
BASE_URL_TEMPLATE_INDEED = "https://mx.indeed.com/jobs?q={keyword}&l=Remote&fromage=14&sc=0kf%3Aattr%28DSQF7%29%3B&sort=date&start={start}"
OUTPUT_FILENAME_INDEED = "indeed_multi_keyword_remoto_jobs.csv"
# --- CONSTANTE NUEVA ---
INDEED_PAGE_INCREMENT = 10 # Indeed usa start=0, 10, 20...

# --- Filtros de Título para INDEED (minúsculas) ---
EXCLUDE_TITLE_KEYWORDS = [
    "software", "development", "data", ".net", "python", "quality", "security", "salesforce", "desarroll", "qa", "ruby", "test", "datos" # "azure"
]
INCLUDE_TITLE_KEYWORDS = [
    "devops", "sre", "cloud", "mlops", "platform", "infrastructure",
    "site reliability", "plataforma","nube",
    "automation", "automatización", "ci/cd", "pipeline", "aws", "azure",
    "gcp", "google cloud", "amazon web services", "cloud native", "kubernetes",
    "k8s", "docker", "container", "contenedor", "serverless", "terraform",
    "ansible", "jenkins", "gitlab", "iac", "monitoring", "monitorización",
    "observability", "observabilidad", "prometheus", "grafana", "architect", "arquitecto"
]

# parse_indeed_job_card (sin cambios respecto a la versión anterior)
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


# --- Funciones de Selenium ---
def close_cookie_popup(driver, wait_short):
    """Intenta encontrar y cerrar el pop-up de cookies."""
    try:
        # Intentar encontrar por XPATH buscando texto (más flexible pero puede fallar si cambia texto)
        # Ajusta los textos según lo que veas en Indeed MX
        xpath_accept = "//button[contains(translate(., 'ACEPTAR COOKIES', 'aceptar cookies'), 'aceptar cookies') or contains(translate(., 'ACCEPT', 'accept'), 'accept') or contains(translate(., 'ENTENDIDO', 'entendido'), 'entendido')]"
        cookie_button = wait_short.until(EC.element_to_be_clickable((By.XPATH, xpath_accept)))
        cookie_button.click()
        print("Pop-up de cookies cerrado.")
        time.sleep(1) # Pequeña pausa después de cerrar
    except TimeoutException:
        # print("No se encontró pop-up de cookies (o no fue clickeable a tiempo).")
        pass # Es normal si no aparece
    except Exception as e:
        print(f"Error al intentar cerrar pop-up de cookies: {e}")


# --- Script Principal ---

# 1. Cargar datos existentes (sin cambios)
existing_df_indeed = pd.DataFrame()
found_job_ids_indeed = set()
if os.path.exists(OUTPUT_FILENAME_INDEED):
    print(f"Cargando datos existentes desde '{OUTPUT_FILENAME_INDEED}'...")
    try:
        existing_df_indeed = pd.read_csv(OUTPUT_FILENAME_INDEED)
        if 'job_id' in existing_df_indeed.columns:
            # Asegurar que job_id sea string para comparación correcta
            existing_df_indeed['job_id'] = existing_df_indeed['job_id'].astype(str)
            found_job_ids_indeed = set(existing_df_indeed['job_id'].dropna().tolist())
            print(f"Se cargaron {len(found_job_ids_indeed)} IDs existentes de Indeed.")
        else:
            print(f"Advertencia: '{OUTPUT_FILENAME_INDEED}' no tiene columna 'job_id'.")
            # Crear columna si no existe para evitar errores posteriores
            existing_df_indeed['job_id'] = pd.Series(dtype='str')
    except pd.errors.EmptyDataError:
        print(f"El archivo '{OUTPUT_FILENAME_INDEED}' está vacío.")
        # Asegurar que el DataFrame tiene la columna job_id aunque esté vacío
        existing_df_indeed = pd.DataFrame(columns=['job_id']) # Define las columnas esperadas si está vacío
    except Exception as e:
        print(f"Error al leer '{OUTPUT_FILENAME_INDEED}': {e}.")
        existing_df_indeed = pd.DataFrame(columns=['job_id']) # Define columnas en caso de error
        found_job_ids_indeed = set()
else:
    print(f"El archivo '{OUTPUT_FILENAME_INDEED}' no existe. Se creará uno nuevo.")
    existing_df_indeed = pd.DataFrame(columns=['job_id']) # Define columnas para archivo nuevo

new_jobs_list_indeed = []
processed_titles_indeed = {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}

# --- Inicializar Driver ---
driver = setup_driver_remote() # O la función que prefieras para obtener el driver
wait_long = WebDriverWait(driver, REQUEST_TIMEOUT) # Espera larga para elementos principales
wait_short = WebDriverWait(driver, 5) # Espera corta para elementos opcionales (popups)

print("======= INICIANDO SCRAPING DE OFERTAS INDEED (CON SELENIUM) =======")

# 2. Iniciar Scraping
try:
    for keyword in SEARCH_KEYWORDS_INDEED:
        print(f"\n========== Procesando Búsqueda Indeed para: '{keyword}' ==========")
        page = 1
        keep_paging = True

        while keep_paging:
            # --- CÁLCULO CORRECTO de start_index ---
            start_index = (page - 1) * INDEED_PAGE_INCREMENT
            current_url = BASE_URL_TEMPLATE_INDEED.format(keyword=keyword, start=start_index)

            print(f"\n--- Scraping página {page} para '{keyword}' (start={start_index}) ---")
            print(f"URL: {current_url}")

            try:
                driver.get(current_url)

                # --- Intentar cerrar pop-up de cookies ---
                close_cookie_popup(driver, wait_short)

                # --- Espera Explícita (Selector Mejorado) ---
                print("Esperando que la lista de trabajos cargue...")
                job_list_container = None # Inicializar
                try:
                    # Esperar por el contenedor DIV que contiene la lista UL
                    job_list_container = wait_long.until(
                        EC.presence_of_element_located((By.ID, "mosaic-provider-jobcards"))
                    )
                    # Opcional pero recomendado: Esperar a que al menos una tarjeta sea visible
                    wait_long.until(
                        EC.visibility_of_element_located((By.CSS_SELECTOR, "div#mosaic-provider-jobcards li div.cardOutline"))
                    )
                    print("Contenedor y al menos una tarjeta de trabajo encontrados.")
                    time.sleep(2) # Pausa adicional para renderizado JS
                except TimeoutException:
                    print(f"Timeout esperando la lista/tarjetas de trabajos en la página {page}.")
                     # Intentar tomar screenshot para depuración
                    try:
                         screenshot_filename = f"debug_timeout_page_{page}_{keyword.replace(' ', '_')}.png"
                         driver.save_screenshot(screenshot_filename)
                         print(f"Screenshot guardado en: {screenshot_filename}")
                    except Exception as img_e:
                         print(f"No se pudo guardar el screenshot: {img_e}")

                    # Decisión: Si falla en la página 1, saltar keyword. Si falla después, detener paginación para esa keyword.
                    if page == 1:
                        print(f"No se encontraron resultados iniciales visibles para '{keyword}'. Saltando keyword.")
                    else:
                        print(f"Timeout en página {page}. Asumiendo fin de resultados para esta keyword.")
                    keep_paging = False # Detiene el bucle while para esta keyword
                    continue # Salta al siguiente ciclo (o sale si keep_paging es False)
                except NoSuchElementException:
                     print(f"Error crítico: No se encontró el contenedor principal 'mosaic-provider-jobcards' en la página {page}. Saltando keyword.")
                     keep_paging = False
                     continue
                except Exception as e_wait:
                    print(f"Error inesperado durante la espera de elementos en página {page}: {e_wait}. Deteniendo para '{keyword}'.")
                    keep_paging = False
                    continue


                # --- Obtener HTML y Parsear ---
                page_html = driver.page_source
                soup = BeautifulSoup(page_html, 'html.parser')

                # Buscar el contenedor específico y luego los LIs dentro
                job_list_container_soup = soup.find('div', id='mosaic-provider-jobcards')

                if job_list_container_soup:
                    # Buscar ULs que parezcan contener las tarjetas (la clase puede cambiar)
                    # Intentamos con la clase vista, pero podríamos necesitar algo más genérico
                    ul_list = job_list_container_soup.find('ul', class_='css-1faftfv') # Clase específica vista en el HTML
                    if not ul_list: # Fallback si la clase cambia
                         ul_list = job_list_container_soup.find('ul') # El primer UL dentro del div

                    # Obtener LIs que sean hijos directos del UL y que contengan una tarjeta válida
                    job_cards_li = ul_list.find_all('li', recursive=False) if ul_list else []
                    job_cards_li = [li for li in job_cards_li if li.find('div', class_='cardOutline')] # Filtrar LIs válidos
                else:
                    print("Advertencia: No se encontró el contenedor 'mosaic-provider-jobcards' en el HTML parseado.")
                    job_cards_li = [] # No se encontró el contenedor principal

                current_page_job_count = len(job_cards_li)
                print(f"Se encontraron {current_page_job_count} tarjetas de trabajo válidas en el HTML de la página {page}.")

                # --- Manejo si no hay trabajos en la página 1 ---
                # (Movido arriba, después de la espera, para mejor lógica)

                # --- Procesamiento de tarjetas, filtros, deduplicación ---
                found_on_page = 0
                skipped_duplicates = 0
                skipped_excluded_title = 0
                skipped_inclusion_fail = 0

                for card_li in job_cards_li:
                    job_info = parse_indeed_job_card(card_li) # Usa tu función de parseo

                    if job_info:
                        job_id = job_info.get('job_id')
                        job_title = job_info.get('title', '')
                        job_title_lower = job_title.lower()

                        # --- Aplicar Filtros ---
                        # Exclusión explícita
                        excluded = False
                        for exclude_word in EXCLUDE_TITLE_KEYWORDS:
                            if exclude_word in job_title_lower:
                                processed_titles_indeed['excluded_explicit'].append(f"{job_title} (Excl: {exclude_word})")
                                excluded = True
                                skipped_excluded_title += 1
                                break
                        if excluded: continue

                        # Inclusión (si se define la lista)
                        if INCLUDE_TITLE_KEYWORDS: # Solo si la lista no está vacía
                            included = False
                            for include_word in INCLUDE_TITLE_KEYWORDS:
                                if include_word in job_title_lower:
                                    included = True
                                    break
                            if not included:
                                processed_titles_indeed['excluded_implicit'].append(f"{job_title}")
                                skipped_inclusion_fail += 1
                                continue # Saltar si no cumple inclusión

                        # --- Deduplicación y Adición ---
                        if job_id and job_id not in found_job_ids_indeed:
                            new_jobs_list_indeed.append(job_info)
                            found_job_ids_indeed.add(job_id) # Añadir como string
                            found_on_page += 1
                            processed_titles_indeed['included'].append(job_title)
                        elif job_id:
                            skipped_duplicates += 1
                        # else: No debería pasar si parse_indeed_job_card devuelve None sin ID

                print(f"Se añadieron {found_on_page} ofertas nuevas.")
                if skipped_excluded_title > 0: print(f"Se descartaron {skipped_excluded_title} por exclusión de título.")
                if skipped_inclusion_fail > 0: print(f"Se descartaron {skipped_inclusion_fail} por fallo de inclusión de título.")
                if skipped_duplicates > 0: print(f"Se omitieron {skipped_duplicates} ofertas duplicadas.")


                # --- NUEVA CONDICIÓN DE SALIDA: Comprobar enlace "Siguiente" ---
                try:
                    # Usamos find_elements para evitar excepción si no existe
                    next_page_links = driver.find_elements(By.CSS_SELECTOR, "a[data-testid='pagination-page-next']")
                    if not next_page_links:
                         print(f"\nNo se encontró el enlace 'Página siguiente'. Asumiendo fin de resultados para '{keyword}'.")
                         keep_paging = False
                    # Opcional: podrías verificar si el enlace es clickeable: EC.element_to_be_clickable
                    # else:
                    #    print("Enlace 'Página siguiente' encontrado.") # Para depuración

                except NoSuchElementException: # No debería ocurrir con find_elements
                     print(f"Error buscando el enlace 'Página siguiente'. Asumiendo fin para '{keyword}'.")
                     keep_paging = False
                except Exception as e_nav:
                     print(f"Error inesperado al buscar paginación: {e_nav}. Deteniendo para '{keyword}'.")
                     keep_paging = False


                # --- Preparar Siguiente Iteración ---
                if keep_paging:
                     page += 1
                     print(f"Esperando {DELAY_BETWEEN_PAGES} segundo(s) antes de la página {page}...")
                     time.sleep(DELAY_BETWEEN_PAGES)
                # else: El bucle while terminará naturalmente

            # --- Manejo de Excepciones del Bucle Interno (ajustado) ---
            except TimeoutException:
                 print(f"Error: Timeout general en la página {page} para '{keyword}'. Deteniendo para esta keyword.")
                 keep_paging = False # Detener para esta keyword si hay timeouts generales
            except NoSuchElementException as e:
                 # Esto podría ocurrir si un elemento esperado (ej: job list) no se carga DESPUÉS de la espera inicial
                 print(f"Error: No se encontró un elemento esencial POST-carga en {page} para '{keyword}': {e}. Deteniendo para esta keyword.")
                 keep_paging = False
            except WebDriverException as e:
                 print(f"Error de WebDriver en {page} para '{keyword}': {e}")
                 print("Deteniendo el scraping para esta keyword debido a error del driver.")
                 keep_paging = False
            except Exception as e:
                print(f"Error general procesando {page} para '{keyword}': {e}")
                print("Deteniendo para esta keyword debido a error inesperado.")
                keep_paging = False # Es más seguro detenerse en errores inesperados

finally: # Asegurar cierre del driver
    if 'driver' in locals() and driver is not None:
        print("\nCerrando WebDriver...")
        try:
            driver.quit()
            print("WebDriver cerrado.")
        except Exception as e:
            print(f"Error al cerrar WebDriver: {e}")


# --- 3. Combinar y Guardar Resultados ---
print("\n======= PROCESANDO RESULTADOS FINALES INDEED =======")

print("\n--- Reporte de Títulos Procesados ---")
print(f"Total Incluidos: {len(processed_titles_indeed['included'])}")
print(f"Total Excluidos (por keyword explícita): {len(processed_titles_indeed['excluded_explicit'])}")
# Asegúrate que la key 'excluded_implicit' existe antes de accederla
print(f"Total Excluidos (por fallo de inclusión): {len(processed_titles_indeed.get('excluded_implicit', []))}")


if new_jobs_list_indeed:
    print(f"\nSe encontraron {len(new_jobs_list_indeed)} ofertas nuevas de Indeed en total durante esta ejecución.")
    new_df_indeed = pd.DataFrame(new_jobs_list_indeed)
    # Asegurar que la columna job_id existe y es string en el nuevo DF
    if 'job_id' in new_df_indeed.columns:
        new_df_indeed['job_id'] = new_df_indeed['job_id'].astype(str)
    else:
        print("Advertencia: El nuevo DataFrame no contiene la columna 'job_id'.")
        new_df_indeed['job_id'] = pd.Series(dtype='str')


    if not existing_df_indeed.empty:
        print(f"Combinando {len(new_jobs_list_indeed)} nuevos con {len(existing_df_indeed)} existentes de Indeed.")
        # Asegurar que ambos DFs tienen las mismas columnas antes de concatenar
        all_cols = list(set(new_df_indeed.columns) | set(existing_df_indeed.columns))
        # Reindexar ambos DFs para que tengan todas las columnas, rellenando con NaN si falta alguna
        new_df_indeed = new_df_indeed.reindex(columns=all_cols)
        existing_df_indeed = existing_df_indeed.reindex(columns=all_cols)

        combined_df_indeed = pd.concat([existing_df_indeed, new_df_indeed], ignore_index=True)
    else:
        print("No había datos existentes de Indeed, guardando solo los nuevos.")
        combined_df_indeed = new_df_indeed

    # Deduplicación final basada en job_id (asegurándose que la columna existe)
    initial_rows = len(combined_df_indeed)
    if 'job_id' in combined_df_indeed.columns:
        # Convertir a string ANTES de eliminar duplicados por si hay mezclas de tipos
        combined_df_indeed['job_id'] = combined_df_indeed['job_id'].astype(str)
        # Eliminar duplicados manteniendo la primera aparición (los existentes)
        combined_df_indeed.drop_duplicates(subset=['job_id'], keep='first', inplace=True)
        final_rows = len(combined_df_indeed)
        if initial_rows > final_rows:
             print(f"Se eliminaron {initial_rows - final_rows} duplicados durante la combinación final de Indeed.")
    else:
         print("Advertencia: No se pudo realizar la deduplicación final de Indeed por falta de columna 'job_id'.")

    # Guardar el CSV final
    try:
        # Definir el orden deseado y asegurar que todas las columnas existen
        columns_order = ['job_id', 'title', 'company', 'salary', 'location', 'posted_date', 'link']
        # Añadir columnas faltantes con None o NaN
        for col in columns_order:
            if col not in combined_df_indeed.columns:
                combined_df_indeed[col] = pd.NA # Usar pd.NA para datos faltantes

        # Reordenar y guardar
        combined_df_indeed = combined_df_indeed[columns_order]
        combined_df_indeed.to_csv(OUTPUT_FILENAME_INDEED, index=False, encoding='utf-8-sig')
        print(f"\nDatos de Indeed actualizados guardados exitosamente en '{OUTPUT_FILENAME_INDEED}' ({len(combined_df_indeed)} ofertas en total).")
    except Exception as e:
        print(f"\nError al guardar el archivo CSV final de Indeed: {e}")

elif not new_jobs_list_indeed and not existing_df_indeed.empty:
    print("\nNo se encontraron ofertas nuevas de Indeed en esta ejecución. El archivo existente no se modificará.")
    # Asegurarse de que len() no falle si existing_df_indeed es None o similar (aunque no debería serlo)
    count_existing = len(existing_df_indeed) if existing_df_indeed is not None else 0
    print(f"El archivo '{OUTPUT_FILENAME_INDEED}' contiene {count_existing} ofertas.")
else:
    print("\nNo se encontraron ofertas nuevas de Indeed y no existía archivo previo.")
    # Opcional: Crear un archivo vacío con cabeceras si se desea
    # pd.DataFrame(columns=['job_id', 'title', 'company', 'salary', 'location', 'posted_date', 'link']).to_csv(OUTPUT_FILENAME_INDEED, index=False, encoding='utf-8-sig')
    # print(f"Se creó un archivo vacío '{OUTPUT_FILENAME_INDEED}' con cabeceras.")


print("\n======= FIN DEL SCRIPT =======")