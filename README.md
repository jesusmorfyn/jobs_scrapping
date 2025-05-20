# Documentación del Scraper Combinado de Empleos

Este proyecto contiene un script de Python (`job_scraper.py`) diseñado para extraer ("scrapear") ofertas de empleo de varios portales, incluyendo OCC Mundial, Indeed y LinkedIn. El objetivo principal es recopilar información sobre trabajos (inicialmente remotos, pero configurable) en el área de tecnología (DevOps, Cloud, SRE, etc.) y almacenarla de forma centralizada.

## Requisitos Previos

*   **Python:** Asegúrate de tener instalado Python 3.7+ en tu sistema.
*   **Pip:** El instalador de paquetes de Python, generalmente viene con Python.
*   **Navegador Chrome:** Necesario para las plataformas que utilizan Selenium (como Indeed y LinkedIn) para controlar una instancia de Chrome.

## Instalación de Dependencias

Antes de ejecutar el script, necesitas instalar las librerías de Python requeridas.

1.  Abre una terminal o línea de comandos.
2.  Navega hasta el directorio donde se encuentra el script `job_scraper.py` y el archivo `requirements.txt`.
3.  Crea un archivo `requirements.txt` con el siguiente contenido (si aún no lo tienes):
    ```
    beautifulsoup4
    pandas
    selenium
    requests
    lxml
    PyYAML
    argparse 
    ```
4.  Ejecuta el siguiente comando para instalar las dependencias:

    ```bash
    pip install -r requirements.txt
    ```

    Esto instalará las siguientes librerías:
    *   `beautifulsoup4`: Para parsear (interpretar) el HTML de las páginas web.
    *   `pandas`: Para manejar los datos (crear tablas, leer/escribir CSV).
    *   `selenium`: Para controlar el navegador Chrome (necesario para Indeed y LinkedIn).
    *   `requests`: Para realizar las peticiones HTTP (descargar el HTML de OCC).
    *   `lxml`: Un parser HTML alternativo, a menudo más rápido y robusto (usado por BeautifulSoup).
    *   `PyYAML`: Para leer y escribir archivos de configuración en formato YAML.
    *   `argparse`: Para manejar argumentos de línea de comandos (como especificar un archivo de configuración).

## Configuración del Script (`config.yaml`)

El comportamiento del script se controla a través de un archivo de configuración llamado `config.yaml` (o el nombre que especifiques al ejecutar el script). Este archivo permite modificar:

*   **`general`**:
    *   `output_filename`: Nombre del archivo CSV donde se guardarán los resultados.
    *   `final_columns_to_save`: Lista de columnas y su orden en el CSV final.
    *   `headers`: Cabeceras HTTP a usar (ej. `User-Agent`).
*   **`platforms`**: Configuraciones específicas para cada portal (OCC, LinkedIn, Indeed).
    *   `base_url`: Plantilla de la URL de búsqueda.
    *   `time_param_name` y `default_time_param_value`: Para filtrar por fecha de publicación.
    *   `request_timeout`, `request_timeout_selenium`: Tiempos de espera.
    *   `page_increment`: Cómo avanza la paginación.
    *   `max_pages`: Número máximo de páginas a scrapear por keyword para esa plataforma (útil para pruebas).
    *   `delay_between_pages_selenium`: Pausa entre páginas cuando se usa Selenium.
    *   `enabled`: `true` o `false` para activar/desactivar el scraping de esta plataforma.
*   **`search_filters`**:
    *   `search_keywords`: Lista de palabras clave principales para buscar.
    *   `exclude_title_keywords`: Palabras clave que, si aparecen en el título, descartan la oferta.
    *   `include_title_keywords`: Si no está vacía, el título debe contener al menos una de estas para ser incluido.
*   **`timing`**:
    *   `delay_between_keywords`: Pausa entre la finalización de una keyword y el inicio de la siguiente.
    *   `retry_delay`: Pausa antes de reintentar una petición fallida.
*   **`selenium`**:
    *   `debugger_address`: Dirección y puerto para conectar Selenium a una instancia de Chrome en modo debug (ej. `localhost:9222`).

Un ejemplo de `config.yaml` se proporciona en el repositorio.

## Ejecución del Script

La ejecución puede requerir un paso especial si se utilizan plataformas basadas en Selenium (Indeed, LinkedIn) debido a sus protecciones.

1.  **Preparar Chrome para Selenium (¡Paso Crucial para Indeed/LinkedIn!):**
    *   **¿Por qué?** Sitios como Indeed y LinkedIn utilizan medidas (como Cloudflare) para detectar y bloquear scripts automatizados. Ejecutar Chrome en modo de depuración remota permite que Selenium se conecte a una instancia del navegador que tú iniciaste manualmente, haciendo que la sesión parezca más humana.
    *   **Cierra TODAS las ventanas de Chrome.**
    *   **Abre una terminal** (CMD, PowerShell, Git Bash, etc.).
    *   **Ejecuta el siguiente comando.** Reemplaza la ruta en `--user-data-dir` con la ruta a tu perfil de Chrome o a un directorio nuevo.

        ```bash
        # Ejemplo para Windows (ajusta la ruta a chrome.exe)
        # Usando tu perfil existente:
        "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\Users\TuUsuario\AppData\Local\Google\Chrome\User Data\Default"
        
        # O usando un perfil temporal nuevo (recomendado si tienes problemas):
        # Crea una carpeta, por ejemplo C:\ChromeDebugProfile
        "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\ChromeDebugProfile" 
        ```
        *   **Ruta del perfil:** Abre Chrome, ve a `chrome://version` y busca "Ruta del perfil".
        *   **Puerto:** `9222` es común. Si está ocupado, elige otro (ej. `9223`) y actualiza `debugger_address` en `config.yaml`.
    *   Se abrirá una ventana de Chrome. **¡Déjala abierta!** El script la controlará.
    *   **Opcional:** Si usaste un perfil nuevo, la primera vez, inicia sesión en Google/LinkedIn si es necesario.

2.  **Ejecutar el Script `job_scraper.py`:**
    *   Abre **otra** terminal.
    *   Navega hasta el directorio donde está `job_scraper.py`.
    *   Ejecuta el script:
        ```bash
        # Usando el config.yaml por defecto
        python job_scraper.py
        
        # Especificando un archivo de configuración diferente
        python job_scraper.py --config mi_otra_config.yaml
        ```
    *   El script cargará la configuración, intentará conectarse a Chrome si es necesario, e iterará por cada `keyword`.
    *   **Interacción Manual (Opcional para Selenium):** Mientras el script controla Chrome, mover el ratón o hacer scroll puede ayudar a evitar la detección de bots.

## Salida

*   El script genera (o actualiza) un archivo CSV definido en `config.yaml` (ej. `all_remote_jobs.csv`).
*   Contiene las ofertas de las plataformas habilitadas que pasaron los filtros.
*   Las columnas son las definidas en `final_columns_to_save` en `config.yaml`. Típicamente:
    *   `job_id`: Identificador único.
    *   `platform`: Fuente de la oferta (ej. 'OCC', 'Indeed', 'LinkedIn').
    *   `title`: Título del puesto.
    *   `company`: Nombre de la empresa.
    *   `salary`: Salario (o "No especificado").
    *   `timestamp_found`: Fecha y hora (`YYYY-MM-DD HH:MM:SS`) en que se encontró la oferta.
    *   `link`: Enlace directo a la oferta.
*   **Deduplicación:** El script lee los `job_id` del CSV existente. Solo añade ofertas nuevas. Al guardar, vuelve a eliminar duplicados por `job_id`, manteniendo la primera entrada.

## Funcionalidades Clave

*   **Scraping Multi-Plataforma:** Obtiene datos de varios sitios configurados.
*   **Configuración Externa (YAML):** Flexibilidad para cambiar parámetros sin modificar el código.
*   **Argumento de Configuración:** Permite usar diferentes archivos de configuración.
*   **Habilitar/Deshabilitar Plataformas:** Controla qué sitios se scrapean desde el config.
*   **Límite de Páginas:** `max_pages` por plataforma para controlar la profundidad del scraping.
*   **Filtrado Avanzado:** Por inclusión/exclusión de palabras clave en el título.
*   **Pausas Estratégicas:** Para reducir la carga en servidores y evitar bloqueos.
*   **Manejo de "Sin Resultados":** Detección para evitar esperas innecesarias.

## Troubleshooting (Solución de Problemas)

*   **Error al conectar con Chrome (Selenium):**
    *   Verifica que Chrome se lanzó con el comando y puerto correctos.
    *   Asegúrate de que **TODAS** las demás ventanas de Chrome estaban cerradas *antes*.
    *   Confirma que el puerto no está bloqueado y que `debugger_address` en `config.yaml` coincide.
    *   Verifica que la ruta en `--user-data-dir` es válida.
*   **Detección de Bot/Cloudflare (Selenium):**
    *   Intenta con un perfil nuevo (`--user-data-dir="C:\Ruta\Nueva\Carpeta"`).
    *   Interactúa manualmente con la ventana de Chrome.
    *   Aumenta los delays en `config.yaml`.
*   **El script deja de funcionar / No extrae datos:**
    *   Los sitios web cambian su HTML. Necesitarás actualizar los **selectores CSS/XPath** en las funciones `parse_job_card_...`, `get_total_results_...` y la lógica de paginación.
*   **Errores de `requests` (ej. OCC):** Problemas de red, timeouts (aumenta `request_timeout` en el config), o bloqueos temporales de IP (aumenta los `delay_...` en el config).
*   **Error `PyYAML` o `lxml` no encontrado:** Asegúrate de haber instalado las dependencias con `pip install -r requirements.txt`.

## Notas Adicionales

*   El web scraping es sensible a cambios en la estructura HTML de los sitios. Se requiere mantenimiento.
*   Usa los delays de forma responsable para evitar sobrecargar los servidores.
*   Ajusta los filtros en `config.yaml` para obtener resultados relevantes.