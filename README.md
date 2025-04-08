# Documentación del Scraper de Empleos (OCC & Indeed)

Este proyecto contiene dos scripts de Python diseñados para extraer ("scrapear") ofertas de empleo de dos portales populares en México: OCC Mundial e Indeed. El objetivo principal es recopilar información sobre trabajos remotos en el área de tecnología (DevOps, Cloud, SRE, etc.).

## Requisitos Previos

*   **Python:** Asegúrate de tener instalado Python 3.x en tu sistema.
*   **Pip:** El instalador de paquetes de Python, generalmente viene con Python.
*   **Navegador Chrome:** Necesario para el script de Indeed, ya que utiliza Selenium para controlar una instancia de Chrome.

## Instalación de Dependencias

Antes de ejecutar los scripts, necesitas instalar las librerías de Python requeridas.

1.  Abre una terminal o línea de comandos.
2.  Navega hasta el directorio donde clonaste o descargaste este proyecto.
3.  Ejecuta el siguiente comando para instalar las dependencias listadas en el archivo `requirements.txt`:

    ```bash
    pip install -r requirements.txt
    ```

    Esto instalará las siguientes librerías:
    *   `beautifulsoup4`: Para parsear el HTML de las páginas web.
    *   `pandas`: Para manejar los datos y guardarlos en formato CSV.
    *   `selenium`: Para controlar el navegador (necesario para Indeed).
    *   `requests`: Para realizar las peticiones HTTP (usado en el script de OCC).
    *   `lxml`: ?.

## Descripción de los Scripts

### 1. Scraper de OCC Mundial (`test-occ.py`)

*   **Propósito:** Extrae ofertas de empleo remotas de OCC Mundial (occ.com.mx) basándose en una lista de palabras clave. Utiliza la librería `requests` para descargar el HTML y `BeautifulSoup` para parsearlo.
*   **Configuración:** Puedes modificar las siguientes variables dentro del script `test-occ.py`:
    *   `SEARCH_KEYWORDS`: Lista de palabras clave para buscar (ej. "devops", "cloud").
    *   `BASE_URL_TEMPLATE`: Plantilla de la URL de búsqueda.
    *   `OUTPUT_FILENAME`: Nombre del archivo CSV donde se guardarán los resultados (`occ_multi_keyword_remoto_jobs.csv`).
    *   `INCLUDE_TITLE_KEYWORDS`: Lista de palabras clave que *deben* estar presentes en el título del trabajo para ser considerado (si la lista no está vacía).
    *   `DELAY_BETWEEN_PAGES`: Tiempo de espera (en segundos) entre la carga de cada página de resultados.
*   **Ejecución:** Este script se puede ejecutar directamente desde la terminal:

    ```bash
    python test-occ.py
    ```
*   **Salida:** Genera (o actualiza) un archivo CSV llamado `occ_multi_keyword_remoto_jobs.csv` en el mismo directorio. El archivo contendrá columnas como `job_id`, `title`, `company`, `salary`, `location`, `posted_date`, y `link`. Si el archivo ya existe, el script cargará los IDs existentes y solo añadirá las ofertas nuevas, evitando duplicados basados en `job_id`.

### 2. Scraper de Indeed (`test-indeed.py`)

*   **Propósito:** Extrae ofertas de empleo remotas de Indeed (mx.indeed.com) basándose en una lista de palabras clave. Utiliza `Selenium` para controlar una instancia del navegador Chrome y poder interactuar con la página, que puede tener protecciones (como Cloudflare) o cargar contenido dinámicamente con JavaScript.
*   **Configuración:** Puedes modificar las siguientes variables dentro del script `test-indeed.py`:
    *   `SEARCH_KEYWORDS_INDEED`: Lista de palabras clave específicas para Indeed.
    *   `BASE_URL_TEMPLATE_INDEED`: Plantilla de la URL de búsqueda de Indeed.
    *   `OUTPUT_FILENAME_INDEED`: Nombre del archivo CSV de salida (`indeed_multi_keyword_remoto_jobs.csv`).
    *   `EXCLUDE_TITLE_KEYWORDS`: Lista de palabras clave que, si aparecen en el título, causarán que la oferta sea descartada.
    *   `INCLUDE_TITLE_KEYWORDS`: Lista de palabras clave que *deben* estar presentes en el título del trabajo para ser considerado (si la lista no está vacía).
    *   `DELAY_BETWEEN_PAGES`: Tiempo de espera (en segundos) entre páginas.
    *   `INDEED_PAGE_INCREMENT`: Valor fijo (generalmente 10) que Indeed usa para la paginación (`start=0, 10, 20...`).
    *   Dentro de la función `setup_driver_remote`: La dirección `localhost:9222` debe coincidir con el puerto usado al lanzar Chrome en modo depuración.
*   **¡Configuración Especial Requerida!**
    *   **¿Por qué?** Indeed utiliza medidas de protección (como Cloudflare) para detectar y bloquear bots. Ejecutar Chrome en modo de depuración remota permite que Selenium se conecte a una instancia *ya existente* del navegador que tú has iniciado manualmente, haciendo que la sesión parezca más legítima.
    *   **Paso 1: Lanzar Chrome en Modo Depuración:**
        *   Cierra **todas** las instancias de Chrome que tengas abiertas.
        *   Abre una terminal (CMD o PowerShell en Windows).
        *   Ejecuta el siguiente comando, **asegúrate de reemplazar la ruta del perfil (`--user-data-dir`) con la ruta correcta a tu perfil de Chrome o a un directorio de perfil nuevo/temporal**:

            ```bash
            .\chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\Users\jesus\AppData\Local\Google\Chrome\User Data\Default"
            ```
            *   **Nota:** La ruta `C:\Users\jesus\AppData\Local\Google\Chrome\User Data\Default` es un **ejemplo**. Debes adaptarla a tu nombre de usuario y sistema operativo. Puedes encontrar la ruta escribiendo `chrome://version` en la barra de direcciones de Chrome (busca "Ruta del perfil").
            *   El puerto `9222` es el estándar, pero si está en uso, puedes cambiarlo (y actualizarlo también en el script).
        *   Chrome se abrirá. **Mantén esta ventana abierta** mientras ejecutas el script.
    *   **Paso 2: Ejecutar el Script:**
        *   Con la ventana de Chrome en modo depuración abierta, ejecuta el script de Python desde otra terminal:

            ```bash
            python test-indeed.py
            ```
            El script intentará conectarse a `localhost:9222`.
    *   **Troubleshooting (Solución de problemas):**
        *   **Error de conexión:** Asegúrate de que Chrome se lanzó correctamente con el comando, que el puerto `9222` no está bloqueado y que coincide con el script. Asegúrate de haber cerrado *todas* las otras instancias de Chrome antes de lanzar la de depuración.
        *   **Detección de Bot / Cloudflare:**
            *   Si el script sigue siendo detectado, intenta crear un **nuevo perfil de Chrome** para usar con el modo depuración. Cambia la ruta en `--user-data-dir` a un directorio nuevo (ej. `C:\ChromeDebugProfile`). Al lanzar Chrome con este perfil nuevo, selecciona este perfil si te lo pregunta.
            *   Mientras el script se ejecuta en la ventana de Chrome controlada, **intenta interactuar manualmente con la página**: haz scroll hacia abajo, mueve el ratón ocasionalmente. Esto puede ayudar a simular actividad humana y evitar la detección.
*   **Salida:** Genera (o actualiza) un archivo CSV llamado `indeed_multi_keyword_remoto_jobs.csv`. Al igual que el script de OCC, cargará IDs existentes y solo añadirá las ofertas nuevas encontradas en esta ejecución.

## Notas Generales

*   Los sitios web como OCC e Indeed cambian su estructura HTML con frecuencia. Si los scripts dejan de funcionar, es probable que necesiten ajustes en los selectores CSS/XPath usados por `BeautifulSoup` o `Selenium` para encontrar los elementos correctos (títulos, salarios, enlaces de paginación, etc.).
*   Aumentar el `DELAY_BETWEEN_PAGES` puede ayudar a evitar bloqueos temporales si realizas muchas búsquedas seguidas.
*   Revisa y ajusta las listas `INCLUDE_TITLE_KEYWORDS` y `EXCLUDE_TITLE_KEYWORDS` según tus necesidades específicas para filtrar mejor los resultados.