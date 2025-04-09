# Documentación del Scraper Combinado de Empleos (OCC & Indeed)

Este proyecto contiene un script de Python (`main.py`) diseñado para extraer ("scrapear") ofertas de empleo de dos portales populares en México: OCC Mundial e Indeed. El objetivo principal es recopilar información sobre trabajos remotos en el área de tecnología (DevOps, Cloud, SRE, etc.) y almacenarla de forma centralizada.

## Requisitos Previos

*   **Python:** Asegúrate de tener instalado Python 3.x en tu sistema.
*   **Pip:** El instalador de paquetes de Python, generalmente viene con Python.
*   **Navegador Chrome:** Necesario para la parte del script que interactúa con Indeed, ya que utiliza Selenium para controlar una instancia de Chrome.

## Instalación de Dependencias

Antes de ejecutar el script, necesitas instalar las librerías de Python requeridas.

1.  Abre una terminal o línea de comandos.
2.  Navega hasta el directorio donde se encuentra el script `main.py` y el archivo `requirements.txt`.
3.  Ejecuta el siguiente comando para instalar las dependencias:

    ```bash
    pip install -r requirements.txt
    ```

    Esto instalará las siguientes librerías:
    *   `beautifulsoup4`: Para parsear (interpretar) el HTML de las páginas web.
    *   `pandas`: Para manejar los datos (crear tablas, leer/escribir CSV).
    *   `selenium`: Para controlar el navegador Chrome (necesario para Indeed).
    *   `requests`: Para realizar las peticiones HTTP (descargar el HTML de OCC).
    *   `lxml`: Un parser HTML alternativo, a menudo más rápido y robusto que el incorporado (usado por BeautifulSoup en este script).

## Configuración del Script (`main.py`)

Puedes modificar varias constantes al inicio del script `main.py` para ajustar su comportamiento:

*   `SEARCH_KEYWORDS`: Lista de palabras clave principales para buscar en ambos sitios. El script adaptará el formato para cada URL (ej. `site reliability engineer` se convertirá en `site-reliability-engineer` para OCC y `site+reliability+engineer` para Indeed).
*   `OUTPUT_FILENAME`: Nombre del archivo CSV unificado donde se guardarán todos los resultados (`all_remote_jobs.csv`).
*   `EXPECTED_COLUMNS`: Define las columnas y su orden en el archivo CSV final. Incluye la columna `'platform'` para identificar la fuente (OCC o Indeed).
*   `BASE_URL_OCC`: Plantilla de la URL de búsqueda para OCC.
*   `BASE_URL_INDEED`: Plantilla de la URL de búsqueda para Indeed.
*   `EXCLUDE_TITLE_KEYWORDS`: Lista de palabras clave (en minúsculas). Si *alguna* de estas palabras aparece en el título de la oferta, esta será **descartada**.
*   `INCLUDE_TITLE_KEYWORDS`: Lista de palabras clave (en minúsculas). Si esta lista **no** está vacía, el título de la oferta *debe contener al menos una* de estas palabras para ser incluida (después de pasar el filtro de exclusión). Si la lista está vacía (`[]`), este filtro se ignora.
*   `DELAY_BETWEEN_PAGES_OCC`/`INDEED`: Tiempo de espera (segundos) entre la carga de páginas de resultados para cada plataforma.
*   `DELAY_BETWEEN_KEYWORDS`: Tiempo de espera (segundos) *después* de completar la búsqueda de una palabra clave en *ambas* plataformas, antes de pasar a la siguiente palabra clave.
*   `INDEED_PAGE_INCREMENT`: Valor fijo (10) que Indeed usa para la paginación (`start=0, 10, 20...`).

## Ejecución del Script

La ejecución requiere un paso especial debido a las protecciones de Indeed.

1.  **Preparar Chrome para Indeed (¡Paso Crucial!):**
    *   **¿Por qué?** Indeed utiliza medidas (como Cloudflare) para detectar y bloquear scripts automatizados (bots). Ejecutar Chrome en modo de depuración remota permite que Selenium se conecte a una instancia del navegador que tú iniciaste manualmente, haciendo que la sesión parezca más humana y evitando bloqueos.
    *   **Cierra TODAS las ventanas de Chrome.** Es importante que no haya ninguna otra instancia ejecutándose.
    *   **Abre una terminal** (CMD, PowerShell, Git Bash, etc.).
    *   **Ejecuta el siguiente comando.** **¡IMPORTANTE!** Debes **reemplazar** la ruta en `--user-data-dir` con la ruta **correcta** a tu perfil de usuario de Chrome o a un directorio **nuevo** que quieras usar como perfil temporal para esto.

        ```bash
        # Ejemplo para Windows (ajusta la ruta a chrome.exe si es necesario)
        .\chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\Users\TuUsuario\AppData\Local\Google\Chrome\User Data\Default"
        
        # O usando un perfil temporal (recomendado si tienes problemas):
        # Crea una carpeta llamada C:\ChromeDebugProfile (o donde prefieras)
        .\chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\ChromeDebugProfile" 
        ```
        *   **¿Cómo encontrar la ruta del perfil?** Abre Chrome normalmente, ve a `chrome://version` en la barra de direcciones y busca "Ruta del perfil". Copia esa ruta.
        *   **Puerto:** `9222` es el estándar. Si está ocupado, elige otro (ej. `9223`) y **asegúrate de cambiarlo también** en la función `setup_driver` dentro del script `main.py` si es necesario (aunque actualmente usa el default `localhost:9222`).
    *   Se abrirá una ventana de Chrome. **¡Déjala abierta!** Esta es la ventana que el script controlará.
    *   **Opcional (Si sigue fallando):** Si usaste un perfil nuevo, la primera vez que se abra, inicia sesión en tu cuenta de Google si lo deseas (esto puede ayudar a que la sesión parezca más legítima).

2.  **Ejecutar el Script `main.py`:**
    *   Abre **otra** terminal.
    *   Navega hasta el directorio donde está `main.py`.
    *   Ejecuta el script:

        ```bash
        python main.py
        ```
    *   El script intentará conectarse a Chrome en `localhost:9222`.
    *   Iterará por cada `keyword` en `SEARCH_KEYWORDS`. Para cada una:
        *   Realizará el scraping de OCC (usando `requests`).
        *   Realizará el scraping de Indeed (usando Selenium conectado a tu Chrome).
        *   Esperará `DELAY_BETWEEN_KEYWORDS` segundos antes de pasar a la siguiente keyword.
    *   **Interacción Manual (Opcional pero útil para Indeed):** Mientras el script controla la ventana de Chrome para Indeed, puedes mover el ratón sobre la ventana o hacer scroll manualmente de vez en cuando. Esto *puede* ayudar a evitar la detección de bots.

## Salida

*   El script genera (o actualiza si ya existe) un **único archivo CSV**: `all_remote_jobs.csv`.
*   Este archivo contiene las ofertas de empleo encontradas en **ambas** plataformas que pasaron los filtros.
*   Las columnas son las definidas en `EXPECTED_COLUMNS`:
    *   `job_id`: Identificador único de la oferta.
    *   `platform`: Indica si la oferta vino de 'OCC' o 'Indeed'.
    *   `title`: Título del puesto.
    *   `company`: Nombre de la empresa (o "Empresa confidencial").
    *   `salary`: Salario publicado (o "No especificado").
    *   `location`: Ubicación (generalmente "Remoto/Home Office").
    *   `posted_date`: Fecha relativa de publicación (ej. "hace 1 día", "Recién publicado").
    *   `timestamp_found`: Fecha y hora exactas (`YYYY-MM-DD HH:MM:SS`) en que el script *encontró y añadió* esa oferta por primera vez.
    *   `link`: Enlace directo a la oferta de empleo.
*   **Deduplicación:** El script lee los `job_id` del archivo CSV existente al inicio. Solo añade ofertas con `job_id` que no se hayan visto antes. Al guardar, vuelve a eliminar duplicados por `job_id`, manteniendo la primera vez que se registró una oferta (la entrada más antigua).

## Funcionalidades Clave

*   **Scraping Combinado:** Ejecuta una sola vez para obtener datos de OCC e Indeed.
*   **Archivo Unificado:** Todos los resultados se guardan en `all_remote_jobs.csv`.
*   **Columna `platform`:** Identifica fácilmente de qué sitio proviene cada oferta.
*   **Filtrado Dinámico por Fecha:** Lee la fecha del último trabajo añadido (`timestamp_found` en el CSV) y ajusta automáticamente el rango de búsqueda (`tm` para OCC, `fromage` para Indeed) para buscar solo publicaciones desde esa fecha (o un rango cercano), optimizando la búsqueda. Si no hay historial, usa 14 días por defecto.
*   **Manejo "Sin Resultados" (Indeed):** Detecta rápidamente si una búsqueda en Indeed no arroja resultados para una keyword y salta a la siguiente, evitando esperas innecesarias.
*   **Pausa Estratégica:** Espera entre páginas de cada plataforma y también entre la búsqueda de diferentes palabras clave para reducir la carga en los servidores y evitar bloqueos.
*   **Filtrado Avanzado:** Permite excluir trabajos por palabras clave en el título (`EXCLUDE_TITLE_KEYWORDS`) e incluir solo aquellos que contengan ciertas palabras clave (`INCLUDE_TITLE_KEYWORDS`).

## Troubleshooting (Solución de Problemas)

*   **Error al conectar con Chrome (Indeed):**
    *   Verifica que Chrome se lanzó con el comando `--remote-debugging-port=9222` (o el puerto que uses).
    *   Asegúrate de que **TODAS** las demás ventanas de Chrome estaban cerradas *antes* de ejecutar ese comando.
    *   Confirma que el puerto no está bloqueado por un firewall.
    *   Verifica que la ruta en `--user-data-dir` es válida.
*   **Detección de Bot/Cloudflare (Indeed):**
    *   **Intenta con un perfil nuevo:** Usa `--user-data-dir="C:\Ruta\Nueva\Carpeta"` en el comando de Chrome.
    *   **Interactúa manualmente:** Mueve el ratón y haz scroll en la ventana de Chrome mientras el script corre para Indeed.
    *   **Aumenta los delays:** Incrementa `DELAY_BETWEEN_PAGES_INDEED` y `DELAY_BETWEEN_KEYWORDS`.
*   **El script deja de funcionar / No extrae datos:**
    *   Los sitios web cambian su estructura HTML. Probablemente necesites actualizar los **selectores CSS** (ej. `find('div', class_='...')`) o **XPath** en las funciones `parse_job_card_occ`, `parse_job_card_indeed`, `get_total_results_occ` y en la lógica de paginación/detección de "sin resultados" de Indeed. Inspecciona el HTML actual de las páginas en tu navegador para encontrar los selectores correctos.
*   **Errores de `requests` (OCC):** Pueden ser problemas de red, timeouts (aumenta `REQUEST_TIMEOUT_OCC`), o bloqueos temporales de IP (aumenta `DELAY_BETWEEN_PAGES_OCC` y `DELAY_BETWEEN_KEYWORDS`).
*   **Error `lxml` no encontrado:** Asegúrate de haber instalado las dependencias con `pip install -r requirements.txt`. Si persiste, intenta `pip install lxml` directamente.

## Notas Adicionales

*   El web scraping depende de la estructura HTML de los sitios web, la cual puede cambiar sin previo aviso, rompiendo el script. Se requiere mantenimiento periódico.
*   Realizar demasiadas peticiones en poco tiempo puede llevar a bloqueos temporales o permanentes de tu IP. Usa los delays de forma responsable.
*   Revisa y ajusta las listas `INCLUDE_TITLE_KEYWORDS` y `EXCLUDE_TITLE_KEYWORDS` según tus necesidades para obtener los resultados más relevantes.