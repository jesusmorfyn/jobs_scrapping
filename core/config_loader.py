import yaml
import logging

logger = logging.getLogger(__name__)

def load_config(config_path):
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        logger.info(f"Configuración cargada desde '{config_path}'")
        return config
    except FileNotFoundError:
        logger.error(f"Archivo de configuración '{config_path}' no encontrado.")
        exit(1)
    except yaml.YAMLError as e:
        logger.error(f"Archivo YAML no válido: {e}")
        exit(1)
    except Exception as e:
        logger.error(f"Error inesperado al cargar la configuración: {e}")
        exit(1)