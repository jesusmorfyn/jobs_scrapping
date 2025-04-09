import requests
from bs4 import BeautifulSoup
import time
import math
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
    "site-reliability-engineer",
    "mlops",
    # "infrastructure",
    # "automation",
    # "ci/cd",
    # "kubernetes",
    # "docker",
    # "terraform",
    # "ansible",
    # "platform-engineer"
]
BASE_URL_TEMPLATE = "https://www.occ.com.mx/empleos/de-{keyword}/tipo-home-office-remoto/?sort=2"
OUTPUT_FILENAME = "occ_multi_keyword_remoto_jobs.csv"
HEADERS = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36' }

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

DELAY_BETWEEN_PAGES = 10
RETRY_DELAY = 10
REQUEST_TIMEOUT = 60

# --- Funciones Auxiliares ---
# ELIMINADAS: read_last_run_time y write_last_run_time

# get_total_results y parse_job_card (sin cambios)
# ... (código de get_total_results y parse_job_card idéntico al anterior) ...
def get_total_results(soup):
    """Intenta extraer el número total de resultados de la página."""
    try:
        # Intento 1: Buscar el div con id 'sort-jobs' y luego el <p> anterior
        sort_div = soup.find('div', id='sort-jobs')
        if sort_div:
            # Buscar el hermano <p> anterior que tenga la clase específica
            results_p_specific = sort_div.find_previous_sibling('p', class_='text-sm font-light')
            if results_p_specific and 'resultados' in results_p_specific.get_text():
                match = re.search(r'(\d{1,3}(?:,\d{3})*|\d+)', results_p_specific.get_text().replace(',', '')) # Manejar comas
                if match:
                    return int(match.group(1))

        # Intento 2: Buscar directamente un <p> que contenga el patrón "X resultados"
        # Este es más general pero puede fallar si hay otros <p> similares
        results_p_general = soup.find('p', string=re.compile(r'\d{1,3}(?:,\d{3})*|\d+\s+resultados'))
        if results_p_general:
            match = re.search(r'(\d{1,3}(?:,\d{3})*|\d+)', results_p_general.get_text().replace(',', ''))
            if match:
                return int(match.group(1))

        # Intento 3: Buscar el primer <p> con la clase, por si acaso
        results_p_alt = soup.find('p', class_='text-sm font-light')
        if results_p_alt and 'resultados' in results_p_alt.get_text():
             match = re.search(r'(\d{1,3}(?:,\d{3})*|\d+)', results_p_alt.get_text().replace(',', ''))
             if match:
                 return int(match.group(1))

        print("Advertencia: No se pudo determinar el número total de resultados para esta búsqueda.")
        return 0
    except Exception as e:
        print(f"Error al intentar obtener el total de resultados: {e}")
        return 0

def parse_job_card(card_soup):
    """Extrae la información de interés de un 'job card'."""
    job_data = {}
    job_id_num = None
    try:
        card_id = card_soup.get('id')
        if card_id and card_id.startswith('jobcard-'):
             # Extraer solo la parte numérica
             match_id = re.search(r'\d+$', card_id)
             if match_id:
                 job_id_num = match_id.group(0)
                 job_data['job_id'] = str(job_id_num) # Asegurar que sea string
             else:
                 job_data['job_id'] = None # ID no numérico encontrado? Marcar como None
        else:
             job_data['job_id'] = None

        # Resto del parsing igual que antes...
        title_tag = card_soup.find('h2', class_='text-lg')
        job_data['title'] = title_tag.get_text(strip=True) if title_tag else None

        salary_tag = card_soup.find('span', class_='font-base')
        job_data['salary'] = salary_tag.get_text(strip=True) if salary_tag else "No especificado"

        company_section = card_soup.find('div', class_='flex flex-row justify-between items-center')
        if company_section:
            company_container_outer = company_section.find('div', class_='flex flex-col')
            if company_container_outer:
                 # Intenta encontrar el div interno h-[21px] o usa el outer como fallback
                 company_container_inner = company_container_outer.find('div', class_='h-[21px]')
                 target_container = company_container_inner if company_container_inner else company_container_outer

                 company_span_or_link = target_container.find('span', class_='line-clamp-1')
                 if company_span_or_link:
                     company_link = company_span_or_link.find('a')
                     if company_link:
                         job_data['company'] = company_link.get_text(strip=True)
                     else: # Si no hay link, buscar el span interno
                         inner_span = company_span_or_link.find('span')
                         if inner_span and "Empresa confidencial" in inner_span.get_text(strip=True):
                              job_data['company'] = "Empresa confidencial"
                         elif inner_span:
                              # Tomar el texto del span interno o default
                              job_data['company'] = inner_span.get_text(strip=True) or "No especificado"
                         else:
                             # Si no hay ni link ni span interno en line-clamp-1
                             job_data['company'] = company_span_or_link.get_text(strip=True) or "No especificado"
                 else:
                     # Fallback: si no hay 'line-clamp-1', buscar directamente 'a' o 'span'
                     company_link = target_container.find('a')
                     if company_link:
                        job_data['company'] = company_link.get_text(strip=True)
                     else:
                        inner_span = target_container.find('span')
                        if inner_span and "Empresa confidencial" in inner_span.get_text(strip=True):
                           job_data['company'] = "Empresa confidencial"
                        elif inner_span:
                           job_data['company'] = inner_span.get_text(strip=True) or "No especificado"
                        else:
                           job_data['company'] = "No especificado" # Último recurso

                 # Location: Buscar relativo al contenedor de compañía o al outer si falla
                 location_tag = target_container.find_next_sibling('div', class_='no-alter-loc-text')
                 if not location_tag: # Fallback: buscar dentro del outer container
                     location_tag = company_container_outer.find('div', class_='no-alter-loc-text')

                 if location_tag:
                     # Extraer texto de spans y links dentro, filtrar vacíos y unir
                     location_parts = [elem.get_text(strip=True) for elem in location_tag.find_all(['span', 'a']) if elem.get_text(strip=True)]
                     job_data['location'] = ', '.join(filter(None, location_parts)) if location_parts else "Remoto/No especificado"
                 else:
                      job_data['location'] = "Remoto/No especificado" # Si no se encuentra el div
            else:
                 job_data['company'] = "No especificado"
                 job_data['location'] = "No especificado" # Si no hay flex flex-col
        else:
             job_data['company'] = "No especificado"
             job_data['location'] = "No especificado" # Si no hay flex flex-row...

        date_tag = card_soup.find('label', class_='text-sm')
        job_data['posted_date'] = date_tag.get_text(strip=True) if date_tag else None

        if job_id_num:
             job_data['link'] = f"https://www.occ.com.mx/empleo/oferta/{job_id_num}/"
        else:
             job_data['link'] = "No encontrado (sin ID)"

        # Retornar solo si tiene título y un ID válido para poder operar
        return job_data if job_data.get('title') and job_data.get('job_id') else None

    except Exception as e:
        print(f"Error procesando una tarjeta de empleo: {e}")
        card_id_debug = card_soup.get('id', 'ID no encontrado')
        print(f"  Tarjeta con ID (aprox): {card_id_debug}")
        return None

# --- Script Principal ---

# 1. Cargar datos existentes y IDs
existing_df = pd.DataFrame()
found_job_ids = set()
expected_columns = ['job_id', 'title', 'company', 'salary', 'location', 'posted_date', 'timestamp_found', 'link']
last_run_time = None # MODIFICADO: Inicializar last_run_time

if os.path.exists(OUTPUT_FILENAME):
    print(f"Cargando datos existentes desde '{OUTPUT_FILENAME}'...")
    try:
        existing_df = pd.read_csv(OUTPUT_FILENAME)
        for col in expected_columns:
            if col not in existing_df.columns:
                existing_df[col] = pd.NA
        if 'job_id' in existing_df.columns:
            found_job_ids = set(existing_df['job_id'].dropna().astype(str).tolist())
            print(f"Se cargaron {len(found_job_ids)} IDs existentes.")
        else:
            print("Advertencia: El archivo CSV existente no tiene columna 'job_id'.")
            existing_df['job_id'] = pd.Series(dtype='str')

        # --- NUEVO: Intentar obtener el último timestamp del CSV ---
        if 'timestamp_found' in existing_df.columns and not existing_df['timestamp_found'].isnull().all():
            try:
                # Convertir a datetime, ignorando errores, y obtener el máximo
                valid_timestamps = pd.to_datetime(existing_df['timestamp_found'], errors='coerce').dropna()
                if not valid_timestamps.empty:
                    last_run_time = valid_timestamps.max()
                    print(f"Último registro encontrado en CSV: {last_run_time}")
            except Exception as e_ts:
                print(f"Advertencia: Error al procesar timestamps del CSV: {e_ts}")
                last_run_time = None # Fallback si hay error
        # --- Fin Nuevo ---

    except pd.errors.EmptyDataError:
        print("El archivo CSV existente está vacío.")
        existing_df = pd.DataFrame(columns=expected_columns)
    except Exception as e:
        print(f"Error al leer el archivo CSV existente: {e}. Se procederá como si no existiera.")
        existing_df = pd.DataFrame(columns=expected_columns)
        found_job_ids = set()
else:
    print(f"El archivo '{OUTPUT_FILENAME}' no existe. Se creará uno nuevo.")
    existing_df = pd.DataFrame(columns=expected_columns)

# --- Determinar parámetro de tiempo (tm) ---
tm_param = 14 # Default

if last_run_time:
    time_diff = datetime.now() - last_run_time
    days_diff = time_diff.days
    print(f"Última ejecución (según CSV) detectada hace {days_diff} días.")
    if days_diff <= 2: tm_param = 3
    elif days_diff <= 7: tm_param = 7
    # else: se mantiene 14
else:
    print("No se encontró fecha de última ejecución en CSV. Usando default tm=14.")

print(f"Parámetro de búsqueda por tiempo establecido: tm={tm_param}")

new_jobs_list = []
processed_titles_occ = {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}

print("======= INICIANDO SCRAPING DE OFERTAS OCC =======")

# 2. Iniciar Scraping
for i, keyword in enumerate(SEARCH_KEYWORDS): # MODIFICADO: Usar enumerate para saber si es el primero
    # MODIFICADO: Añadir parámetro tm a la URL base
    base_url_with_tm = f"{BASE_URL_TEMPLATE.format(keyword=keyword)}&tm={tm_param}"
    print(f"\n========== Procesando Búsqueda {i+1}/{len(SEARCH_KEYWORDS)} para: '{keyword}' (tm={tm_param}) ==========")
    page = 1
    max_pages = 1
    actual_jobs_per_page = 0
    skipped_excluded_title_total = 0
    skipped_inclusion_fail_total = 0

    while True:
        separator = '&'
        current_url = f"{base_url_with_tm}{separator}page={page}" if page > 1 else base_url_with_tm
        print(f"\n--- Scraping página {page} {'de '+str(max_pages) if max_pages > 1 else ''} para '{keyword}' ---")

        # ... (resto del bucle while y procesamiento SIN CAMBIOS) ...
        try:
            response = requests.get(current_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')
            job_cards = soup.find_all('div', id=lambda x: x and x.startswith('jobcard-'))
            current_page_job_count = len(job_cards)

            if page == 1:
                actual_jobs_per_page = current_page_job_count
                if actual_jobs_per_page > 0:
                    total_results = get_total_results(soup)
                    if total_results > 0:
                        max_pages = math.ceil(total_results / actual_jobs_per_page)
                        print(f"Total resultados: {total_results}. Trabajos por página: {actual_jobs_per_page}. Páginas estimadas: {max_pages}")
                    else:
                        max_pages = 1
                        print(f"Trabajos por página: {actual_jobs_per_page}. No se obtuvo total de resultados. Procesando solo página 1.")
                else:
                    max_pages = 0
                    print(f"No se encontraron ofertas en la primera página para '{keyword}'. Saltando esta búsqueda.")
                    break

            if not job_cards and page > 1:
                 print(f"No se encontraron más ofertas en la página {page} para '{keyword}'.")
                 break

            found_on_page = 0
            skipped_duplicates = 0
            skipped_excluded_title_page = 0
            skipped_inclusion_fail_page = 0

            for card in job_cards:
                job_info = parse_job_card(card)

                if job_info:
                    job_id = job_info.get('job_id')
                    job_title = job_info.get('title')
                    job_title_lower = job_title.lower() if job_title else ""

                    # Filtro de Exclusión
                    excluded = False
                    for exclude_word in EXCLUDE_TITLE_KEYWORDS:
                        if exclude_word in job_title_lower:
                            processed_titles_occ['excluded_explicit'].append(f"{job_title} (Excl: {exclude_word})")
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
                            processed_titles_occ['excluded_implicit'].append(f"{job_title}")
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
                        processed_titles_occ['included'].append(job_title)
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
                print(f"Se omitieron {skipped_duplicates} ofertas ya existentes o previamente encontradas.")

            if page >= max_pages:
                print(f"\nSe alcanzó la última página estimada ({max_pages}) para la búsqueda '{keyword}'.")
                break

            page += 1
            print(f"Esperando {DELAY_BETWEEN_PAGES} segundo(s)...")
            time.sleep(DELAY_BETWEEN_PAGES)

        except requests.exceptions.Timeout:
             print(f"Error: Timeout en la página {page} para '{keyword}'. Reintentando en {RETRY_DELAY} segundos...")
             time.sleep(RETRY_DELAY)
             continue # Reintentar la misma página
        except requests.exceptions.RequestException as e:
            print(f"Error de Red/HTTP en la página {page} para '{keyword}': {e}")
            print("Omitiendo el resto de páginas para esta búsqueda.")
            break
        except Exception as e:
            print(f"Error general procesando la página {page} para '{keyword}': {e}")
            print("Omitiendo el resto de páginas para esta búsqueda por error inesperado.")
            break

    print(f"\nResumen para '{keyword}':")
    if skipped_excluded_title_total > 0: print(f"  Total descartados por exclusión: {skipped_excluded_title_total}")
    if skipped_inclusion_fail_total > 0: print(f"  Total descartados por inclusión: {skipped_inclusion_fail_total}")

    # --- NUEVO: Pausa entre keywords ---
    if i < len(SEARCH_KEYWORDS) - 1: # No esperar después de la última keyword
        print(f"\nEsperando {DELAY_BETWEEN_PAGES} segundos antes de la siguiente keyword...")
        time.sleep(DELAY_BETWEEN_PAGES)
    # --- Fin Nuevo ---


# --- 3. Combinar y Guardar Resultados ---
# ... (sin cambios, ya no escribe timestamp aquí) ...
print("\n======= PROCESANDO RESULTADOS FINALES OCC =======")

print("\n--- Reporte de Títulos Procesados OCC ---")
print(f"Total Incluidos: {len(processed_titles_occ['included'])}")
print(f"Total Excluidos (por keyword explícita): {len(processed_titles_occ['excluded_explicit'])}")
print(f"Total Excluidos (por fallo de inclusión): {len(processed_titles_occ.get('excluded_implicit', []))}")

if new_jobs_list:
    print(f"\nSe encontraron {len(new_jobs_list)} ofertas nuevas de OCC en total durante esta ejecución.")
    new_df = pd.DataFrame(new_jobs_list)
    if 'job_id' in new_df.columns:
        new_df['job_id'] = new_df['job_id'].astype(str)
    else:
        print("Advertencia: El nuevo DataFrame OCC no contiene la columna 'job_id'.")
        new_df['job_id'] = pd.Series(dtype='str')

    if not existing_df.empty:
        print(f"Combinando {len(new_jobs_list)} nuevos con {len(existing_df)} existentes de OCC.")
        all_cols = list(set(new_df.columns) | set(existing_df.columns) | set(expected_columns))
        new_df = new_df.reindex(columns=all_cols)
        existing_df = existing_df.reindex(columns=all_cols)
        combined_df = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        print("No había datos existentes de OCC, guardando solo los nuevos.")
        combined_df = new_df

    initial_rows = len(combined_df)
    if 'job_id' in combined_df.columns:
         combined_df['job_id'] = combined_df['job_id'].astype(str)
         combined_df.drop_duplicates(subset=['job_id'], keep='first', inplace=True)
         final_rows = len(combined_df)
         if initial_rows > final_rows:
              print(f"Se eliminaron {initial_rows - final_rows} duplicados durante la combinación final de OCC.")
    else:
         print("Advertencia: No se pudo realizar la deduplicación final de OCC por falta de columna 'job_id'.")

    try:
        columns_order = ['job_id', 'title', 'company', 'salary', 'location', 'posted_date', 'timestamp_found', 'link']
        for col in columns_order:
            if col not in combined_df.columns:
                combined_df[col] = pd.NA
        combined_df = combined_df[columns_order]

        combined_df.to_csv(OUTPUT_FILENAME, index=False, encoding='utf-8-sig')
        print(f"\nDatos de OCC actualizados guardados exitosamente en '{OUTPUT_FILENAME}' ({len(combined_df)} ofertas en total).")

    except Exception as e:
        print(f"\nError al guardar el archivo CSV final de OCC: {e}")

elif not new_jobs_list and not existing_df.empty:
    print("\nNo se encontraron ofertas nuevas de OCC en esta ejecución. El archivo existente no se modificará.")
    count_existing = len(existing_df) if existing_df is not None else 0
    print(f"El archivo '{OUTPUT_FILENAME}' contiene {count_existing} ofertas.")
else:
    print("\nNo se encontraron ofertas nuevas de OCC y no existía archivo previo.")


print("\n======= FIN DEL SCRIPT =======")