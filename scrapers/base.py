from abc import ABC, abstractmethod

class BaseScraper(ABC):
    def __init__(self, config, platform_name):
        self.config = config
        self.platform_name = platform_name
        self.cfg = config['platforms'][platform_name] # Configuración específica de la plataforma

    @abstractmethod
    def scrape_keyword(self, keyword: str, found_job_ids: set):
        """Debe retornar (lista_de_JobOffers, diccionario_de_titulos_procesados)"""
        pass