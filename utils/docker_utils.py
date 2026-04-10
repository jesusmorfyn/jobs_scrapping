import time
import socket
import docker
import logging
import requests
import atexit

logger = logging.getLogger(__name__)

_active_managers = []

def _cleanup_all_containers():
    if _active_managers:
        logger.info(f"🧹 Limpieza de emergencia: Pulverizando {len(_active_managers)} contenedor(es) de Selenium...")
        for manager in list(_active_managers):
            manager.stop()

atexit.register(_cleanup_all_containers)

def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

class SeleniumContainerManager:
    def __init__(self, scraper_name, image_name="selenium/standalone-chrome:latest"):
        self.scraper_name = scraper_name
        self.image_name = image_name
        self.client = docker.from_env()
        self.container = None
        self.port = get_free_port()
        _active_managers.append(self)

    def start(self):
        container_name = f"selenium-{self.scraper_name}-{self.port}"
        logger.info(f"Iniciando contenedor '{container_name}' en puerto {self.port}...")
        try:
            self.container = self.client.containers.run(
                self.image_name,
                name=container_name,  # Bautizamos el contenedor
                detach=True,
                ports={'4444/tcp': self.port},
                remove=True,
                shm_size="2g" 
            )
            self._wait_for_ready()
            return f"http://host.docker.internal:{self.port}/wd/hub"
            
        except Exception as e:
            logger.error(f"Error al iniciar el contenedor Docker: {e}")
            self.stop()
            raise

    def _wait_for_ready(self, timeout=30):
        url = f"http://host.docker.internal:{self.port}/wd/hub/status"
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(url, timeout=2)
                if response.status_code == 200 and response.json().get('value', {}).get('ready'):
                    logger.info(f"Contenedor '{self.scraper_name}' en puerto {self.port} listo.")
                    return
            except requests.exceptions.RequestException:
                pass
            time.sleep(1)
        raise Exception("Timeout esperando a que el contenedor de Selenium estuviera listo.")

    def stop(self):
        if self.container:
            try:
                self.container.stop(timeout=2)
            except Exception:
                pass
            finally:
                self.container = None
                
        if self in _active_managers:
            _active_managers.remove(self)