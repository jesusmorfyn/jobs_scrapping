import time
import socket
import docker
import logging
import requests
import atexit

logger = logging.getLogger(__name__)

# 1. Creamos un registro global para rastrear todos los contenedores vivos
_active_managers = []

# 2. Esta función se ejecutará SIEMPRE, sin importar cómo muera el script (Ctrl+C, errores, etc.)
def _cleanup_all_containers():
    if _active_managers:
        logger.info(f"🧹 Limpieza de emergencia: Deteniendo {len(_active_managers)} contenedores huérfanos...")
        for manager in list(_active_managers):
            manager.stop()

atexit.register(_cleanup_all_containers)

def get_free_port():
    """Pide al OS un puerto que esté garantizado como libre."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

class SeleniumContainerManager:
    def __init__(self, image_name="selenium/standalone-chrome:latest"):
        self.image_name = image_name
        self.client = docker.from_env()
        self.container = None
        self.port = get_free_port()
        
        # Registramos este manager apenas nace
        _active_managers.append(self)

    def start(self):
        logger.info(f"Iniciando contenedor {self.image_name} en puerto {self.port}...")
        try:
            self.container = self.client.containers.run(
                self.image_name,
                detach=True,
                ports={'4444/tcp': self.port},
                remove=True, # ¡CRÍTICO! Docker lo destruirá en el momento que se detenga
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
                    logger.info(f"Contenedor en puerto {self.port} listo para recibir conexiones.")
                    return
            except requests.exceptions.RequestException:
                pass
            time.sleep(1)
        raise Exception("Timeout esperando a que el contenedor de Selenium estuviera listo.")

    def stop(self):
        if self.container:
            try:
                logger.info(f"Deteniendo y eliminando contenedor en puerto {self.port}...")
                self.container.stop(timeout=5)
            except Exception as e:
                # Silenciamos errores aquí para no interrumpir limpiezas masivas
                pass
            finally:
                self.container = None
                
        # Lo quitamos del registro de activos si se detuvo correctamente
        if self in _active_managers:
            _active_managers.remove(self)