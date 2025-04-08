import requests
from bs4 import BeautifulSoup
import time
import math
import re # Para extraer números
import pandas as pd # Necesario para leer/escribir CSV
import os # Para verificar si el archivo existe

# --- Configuración ---
SEARCH_KEYWORDS = [
    "devops", 
    "cloud", 
    "aws", 
    "gcp", 
    "sre", 
    "site-reliability-engineer", 
    "mlops", 
    "infrastructure", 
    "automation", 
    "ci/cd", 
    "kubernetes", 
    "docker", 
    "terraform", 
    "ansible", 
    "platform-engineer"
]
BASE_URL_TEMPLATE = "https://www.occ.com.mx/empleos/de-{keyword}/tipo-home-office-remoto/?sort=2&tm=14"
OUTPUT_FILENAME = "occ_multi_keyword_remoto_jobs.csv" # Nombre del archivo de salida/DB

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# --- Filtros de Título ---
# Lista de palabras clave de inclusión (el título DEBE contener al menos una si la lista NO está vacía)
# Poner en minúsculas. Dejar vacía [] para desactivar este filtro.
INCLUDE_TITLE_KEYWORDS = [
    # Términos generales y roles
    "devops", "sre", "cloud", "mlops", "platform engineer", "infrastructure", "systems engineer",
    "site reliability", "ingeniero de sistemas", "ingeniero de plataforma", "ingeniero de la nube", "nube",
    "automation", "automatización", "ci/cd", "continuous integration", "continuous delivery", "pipeline",
    
    # Nubes públicas y conceptos de nube
    "aws", "azure", "gcp", "google cloud", "amazon web services", "cloud native", "computación en la nube",
    
    # Contenedores, orquestación y virtualización
    "kubernetes", "k8s", "docker", "containerization", "contenedores", "serverless", "serverless computing",
    "orquestación", "virtualización",
    
    # Herramientas de automatización y configuración (IaC)
    "terraform", "ansible", "jenkins", "gitlab", "puppet", "chef", "openstack", "infrastructure as code", "iac", 
    "configuración como código",
    
    # Monitorización, logging y observabilidad
    "prometheus", "grafana", "observability", "observabilidad", "monitoring", "monitorización", "logging", "alerting", "alertas",
    
    # Otros conceptos, herramientas y términos relacionados
    "microservices", "microservicios", "deployment", "despliegue", "release", "escalability", "escalabilidad", "resilience", "resiliencia",
    "devsecops", "seguridad en la nube", "dataops", "integración continua", "entrega continua",
    "automated deployment", "pipeline de despliegue", "orquestación de contenedores", "gestión de infraestructura",
    "failover", "disaster recovery"
]


# Eliminamos JOBS_PER_PAGE, se determinará dinámicamente
DELAY_BETWEEN_PAGES = 10
RETRY_DELAY = 5
REQUEST_TIMEOUT = 30

# --- Funciones Auxiliares (parse_job_card y get_total_results sin cambios) ---
def get_total_results(soup):
    """Intenta extraer el número total de resultados de la página."""
    try:
        sort_div = soup.find('div', id='sort-jobs')
        if sort_div:
            results_p_specific = sort_div.find_previous_sibling('p', class_='text-sm font-light')
            if results_p_specific and 'resultados' in results_p_specific.get_text():
                match = re.search(r'(\d+)', results_p_specific.get_text())
                if match:
                    # print(f"Texto de resultados (específico) encontrado: '{results_p_specific.get_text(strip=True)}'")
                    return int(match.group(1))

        results_p_general = soup.find('p', string=re.compile(r'\d+\s+resultados'))
        if results_p_general:
            match = re.search(r'(\d+)', results_p_general.get_text())
            if match:
                # print(f"Texto de resultados (general) encontrado: '{results_p_general.get_text(strip=True)}'")
                return int(match.group(1))

        results_p_alt = soup.find('p', class_='text-sm font-light')
        if results_p_alt and 'resultados' in results_p_alt.get_text():
             match = re.search(r'(\d+)', results_p_alt.get_text())
             if match:
                 # print(f"Texto de resultados (alternativo) encontrado: '{results_p_alt.get_text(strip=True)}'")
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
                 company_container_inner = company_container_outer.find('div', class_='h-[21px]')
                 target_container = company_container_inner if company_container_inner else company_container_outer

                 company_span_or_link = target_container.find('span', class_='line-clamp-1')
                 if company_span_or_link:
                     company_link = company_span_or_link.find('a')
                     if company_link:
                         job_data['company'] = company_link.get_text(strip=True)
                     else:
                         inner_span = company_span_or_link.find('span')
                         if inner_span and "Empresa confidencial" in inner_span.get_text(strip=True):
                              job_data['company'] = "Empresa confidencial"
                         elif inner_span:
                              job_data['company'] = inner_span.get_text(strip=True) or "No especificado"
                         else:
                             job_data['company'] = "No especificado"
                 else:
                     # Fallback si no hay 'line-clamp-1'
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
                           job_data['company'] = "No especificado"


                 location_tag = target_container.find_next_sibling('div', class_='no-alter-loc-text')
                 if not location_tag and company_container_outer:
                     location_tag = company_container_outer.find('div', class_='no-alter-loc-text')

                 if location_tag:
                     location_parts = [elem.get_text(strip=True) for elem in location_tag.find_all(['span', 'a']) if elem.get_text(strip=True)]
                     job_data['location'] = ', '.join(filter(None, location_parts)) if location_parts else "Remoto/No especificado"
                 else:
                      job_data['location'] = "Remoto/No especificado"
            else:
                 job_data['company'] = "No especificado"
                 job_data['location'] = "No especificado"
        else:
             job_data['company'] = "No especificado"
             job_data['location'] = "No especificado"

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

if os.path.exists(OUTPUT_FILENAME):
    print(f"Cargando datos existentes desde '{OUTPUT_FILENAME}'...")
    try:
        existing_df = pd.read_csv(OUTPUT_FILENAME)
        # Asegurar que la columna job_id exista y convertir a string, manejando NaN
        if 'job_id' in existing_df.columns:
            found_job_ids = set(existing_df['job_id'].dropna().astype(str).tolist())
            print(f"Se cargaron {len(found_job_ids)} IDs existentes.")
        else:
            print("Advertencia: El archivo CSV existente no tiene columna 'job_id'. No se cargarán IDs.")
            existing_df['job_id'] = None # Añadir columna para consistencia si falta

    except pd.errors.EmptyDataError:
        print("El archivo CSV existente está vacío.")
    except Exception as e:
        print(f"Error al leer el archivo CSV existente: {e}. Se procederá como si no existiera.")
        existing_df = pd.DataFrame() # Resetear por si hubo error parcial
        found_job_ids = set()
else:
    print(f"El archivo '{OUTPUT_FILENAME}' no existe. Se creará uno nuevo.")

new_jobs_list = [] # Lista para almacenar solo las NUEVAS ofertas encontradas en esta ejecución

print("======= INICIANDO SCRAPING DE OFERTAS OCC =======")

# 2. Iniciar Scraping
for keyword in SEARCH_KEYWORDS:
    base_url = BASE_URL_TEMPLATE.format(keyword=keyword)
    print(f"\n========== Procesando Búsqueda para: '{keyword}' ==========")
    # print(f"URL Base: {base_url}") # Opcional: mostrar URL base
    page = 1
    max_pages = 1
    actual_jobs_per_page = 0 # Se determinará en la primera página

    while True:
        separator = '&' if '?' in base_url else '?'
        current_url = f"{base_url}{separator}page={page}" if page > 1 else base_url

        print(f"\n--- Scraping página {page} {'de '+str(max_pages) if max_pages > 1 else ''} para '{keyword}' ---")
        # print(f"URL: {current_url}") # Opcional: mostrar URL completa

        try:
            response = requests.get(current_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'lxml')
            job_cards = soup.find_all('div', id=lambda x: x and x.startswith('jobcard-'))
            current_page_job_count = len(job_cards)

            if page == 1:
                actual_jobs_per_page = current_page_job_count # Determinar dinámicamente
                if actual_jobs_per_page > 0:
                    total_results = get_total_results(soup)
                    if total_results > 0:
                        max_pages = math.ceil(total_results / actual_jobs_per_page)
                        print(f"Total resultados: {total_results}. Trabajos por página: {actual_jobs_per_page}. Páginas estimadas: {max_pages}")
                    else:
                        max_pages = 1 # No se pudo obtener total, solo procesar esta página
                        print(f"Trabajos por página: {actual_jobs_per_page}. No se obtuvo total de resultados. Procesando solo página 1.")
                else:
                    max_pages = 0 # No hay trabajos en la primera página, no hay nada que hacer
                    print(f"No se encontraron ofertas en la primera página para '{keyword}'. Saltando esta búsqueda.")
                    break # Salir del while para esta keyword

            if not job_cards:
                if page == 1 and actual_jobs_per_page == 0: # Ya se manejó arriba
                    pass
                elif page > 1:
                     print(f"No se encontraron más ofertas en la página {page} para '{keyword}'.")
                break # Salir del while (sea pág 1 sin jobs o pág > 1 vacía)

            # print(f"Se encontraron {current_page_job_count} posibles ofertas en esta página.") # Opcional
            found_on_page = 0
            skipped_duplicates = 0

            for card in job_cards:
                job_info = parse_job_card(card)

                if job_info: # Asegura que el parseo fue exitoso y devolvió datos y un ID
                    job_id = job_info.get('job_id') # ID ya está como string o None
                    job_title = job_info.get('title')
                    job_title_lower = job_title.lower() if job_title else ""

                # 2. Filtro de Inclusión (solo si la lista no está vacía)
                included = False
                if INCLUDE_TITLE_KEYWORDS:
                    for word in INCLUDE_TITLE_KEYWORDS:
                        # if re.search(r'\b' + re.escape(word) + r'\b', job_title_lower):
                        if word in job_title_lower:
                            included = True
                            break
                    if not included:
                        continue # Pasar a la siguiente tarjeta si no cumple inclusión
                # Si INCLUDE_TITLE_KEYWORDS está vacía, este filtro se pasa automáticamente

                    # Comprobar si el ID es NUEVO (no está en los existentes NI en los añadidos en ESTA ejecución)
                    if job_id not in found_job_ids:
                        new_jobs_list.append(job_info)
                        found_job_ids.add(job_id) # Añadir al set general para evitar duplicados intra-ejecución
                        found_on_page += 1
                    else:
                        skipped_duplicates += 1
                # Si parse_job_card devolvió None (error o sin título/ID), se ignora

            print(f"Se añadieron {found_on_page} ofertas nuevas.")
            if skipped_duplicates > 0:
                print(f"Se omitieron {skipped_duplicates} ofertas ya existentes o previamente encontradas.")

            # Condición de salida del while (paginación)
            if page >= max_pages:
                print(f"\nSe alcanzó la última página estimada ({max_pages}) para la búsqueda '{keyword}'.")
                break

            page += 1
            print(f"Esperando {DELAY_BETWEEN_PAGES} segundo(s)...")
            time.sleep(DELAY_BETWEEN_PAGES)

        # Resto del manejo de excepciones igual que antes...
        except requests.exceptions.Timeout:
             print(f"Error: Timeout en la página {page} para '{keyword}'. Reintentando en {RETRY_DELAY} segundos...")
             time.sleep(RETRY_DELAY)
        except requests.exceptions.RequestException as e:
            print(f"Error de Red/HTTP en la página {page} para '{keyword}': {e}")
            print("Omitiendo el resto de páginas para esta búsqueda.")
            break
        except Exception as e:
            print(f"Error general procesando la página {page} para '{keyword}': {e}")
            print("Intentando continuar con la siguiente página...")
            page += 1
            if page > max_pages and max_pages >= 1 : # Corregido para manejar max_pages=0
                 print("Superado el número de páginas estimado tras error. Pasando a la siguiente keyword.")
                 break
            time.sleep(2)

# --- 3. Combinar y Guardar Resultados ---
print("\n======= PROCESANDO RESULTADOS FINALES =======")

if new_jobs_list:
    print(f"Se encontraron {len(new_jobs_list)} ofertas nuevas en total durante esta ejecución.")
    new_df = pd.DataFrame(new_jobs_list)

    # Combinar nuevos resultados con los existentes (nuevos primero)
    if not existing_df.empty:
        print(f"Combinando {len(new_jobs_list)} nuevos con {len(existing_df)} existentes.")
        # Asegurar que ambos DFs tengan las mismas columnas antes de concatenar para evitar errores
        # Obtener todas las columnas únicas de ambos dataframes
        all_cols = list(set(new_df.columns) | set(existing_df.columns))
        # Reindexar ambos dataframes con todas las columnas, llenando NaN donde no existan
        new_df = new_df.reindex(columns=all_cols)
        existing_df = existing_df.reindex(columns=all_cols)
        combined_df = pd.concat([new_df, existing_df], ignore_index=True)
    else:
        print("No había datos existentes, guardando solo los nuevos.")
        combined_df = new_df

    # Eliminar duplicados finales basados en 'job_id', manteniendo la primera (la más nueva)
    initial_rows = len(combined_df)
    # Asegurar que job_id sea string para la comparación correcta en drop_duplicates
    if 'job_id' in combined_df.columns:
         combined_df['job_id'] = combined_df['job_id'].astype(str)
         combined_df.drop_duplicates(subset=['job_id'], keep='first', inplace=True)
         final_rows = len(combined_df)
         if initial_rows > final_rows:
              print(f"Se eliminaron {initial_rows - final_rows} duplicados durante la combinación final.")
    else:
         print("Advertencia: No se pudo realizar la deduplicación final por falta de columna 'job_id'.")


    # Guardar el DataFrame combinado
    try:
        # Definir el orden deseado de columnas para el archivo final
        columns_order = ['job_id', 'title', 'company', 'salary', 'location', 'posted_date', 'link']
        # Asegurar que todas las columnas existan en el DF combinado
        for col in columns_order:
            if col not in combined_df.columns:
                combined_df[col] = None # Añadirla si falta
        combined_df = combined_df[columns_order] # Reordenar

        combined_df.to_csv(OUTPUT_FILENAME, index=False, encoding='utf-8-sig')
        print(f"Datos actualizados guardados exitosamente en '{OUTPUT_FILENAME}' ({len(combined_df)} ofertas en total).")
    except Exception as e:
        print(f"\nError al guardar el archivo CSV final: {e}")

elif not new_jobs_list and not existing_df.empty:
    print("No se encontraron ofertas nuevas en esta ejecución. El archivo existente no se modificará.")
    print(f"El archivo '{OUTPUT_FILENAME}' contiene {len(existing_df)} ofertas.")
else: # No hay nuevos y no había existentes
    print("No se encontraron ofertas nuevas y no existía archivo previo. No se guardará ningún archivo.")


print("\n======= FIN DEL SCRIPT =======")