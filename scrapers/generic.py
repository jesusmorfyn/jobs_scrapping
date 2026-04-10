import re
import time
import logging
from bs4 import BeautifulSoup
from datetime import datetime
from selenium.webdriver.common.by import By

from .base import BaseScraper
from core.models import JobOffer
from core.filter import filter_job_by_title
from utils.selenium_utils import close_cookie_popup, block_heavy_content

logger = logging.getLogger(__name__)

class GenericScraper(BaseScraper):
    def __init__(self, config, platform_name, driver, browser_lock, tab_handle):
        super().__init__(config, platform_name)
        self.driver = driver
        self.browser_lock = browser_lock
        self.tab_handle = tab_handle
        self.p_cfg = self.config['platforms'][self.platform_name]

    def _extract_field(self, soup_element, rules):
        if not rules or rules == "NONE": return "No especificado"
        target = soup_element.select_one(rules['selector']) if 'selector' in rules else soup_element
        if not target: return "No especificado"

        val = target.get(rules['attribute']) if 'attribute' in rules else target.get_text(strip=True)
        if not val: return "No especificado"

        if 'regex' in rules:
            match = re.search(rules['regex'], val)
            if match:
                return match.group(1) if match.groups() else match.group(0)
        return val

    def _get_html_selenium(self, url):
        sel_rules = self.p_cfg.get('selenium_rules', {})
        html = None
        
        with self.browser_lock:
            self.driver.switch_to.window(self.tab_handle)
            block_heavy_content(self.driver)
            self.driver.get(url)

        wait_seconds = 0
        while True:
            with self.browser_lock:
                self.driver.switch_to.window(self.tab_handle)
                current_html = self.driver.page_source
                current_url = self.driver.current_url.lower()
                
                try: close_cookie_popup(self.driver, None)
                except: pass

                # 1. Detector de Cloudflare / Checkpoints
                if "cf-wrapper" in current_html or "challenge" in current_url or "security check" in current_html.lower() or "just a moment" in current_html.lower():
                    if wait_seconds % 15 == 0:
                        logger.warning(f"🚨 [{self.platform_name.upper()}] Bloqueo detectado. Esperando intervención manual... ({wait_seconds}s)")
                else:
                    soup = BeautifulSoup(current_html, 'lxml')
                    wait_sel = sel_rules.get('wait_for_selector', '')
                    selectors = [s.strip() for s in wait_sel.split(',')] if wait_sel else []
                    
                    # 2. Carga exitosa de tarjetas
                    if wait_sel and any(soup.select(sel) for sel in selectors):
                        scroll_pane = sel_rules.get('scroll_pane_selector')
                        if scroll_pane:
                            try:
                                pane = self.driver.find_element(By.CSS_SELECTOR, scroll_pane)
                                # SCROLL PERSISTENTE
                                last_height = self.driver.execute_script("return arguments[0].scrollHeight", pane)
                                for _ in range(5):
                                    self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", pane)
                                    time.sleep(1.5)
                                    new_height = self.driver.execute_script("return arguments[0].scrollHeight", pane)
                                    if new_height == last_height:
                                        break
                                    last_height = new_height
                            except: pass
                        html = self.driver.page_source
                        break
                        
                    # 3. Validar si es una página vacía legítima
                    no_res = sel_rules.get('no_results_text', 'xxxxxx')
                    if no_res.lower() in current_html.lower():
                        logger.info(f"[{self.platform_name.upper()}] No hay resultados en esta página.")
                        break
                    
            time.sleep(5)
            wait_seconds += 5
            if wait_seconds % 15 == 0 and "cf-wrapper" not in current_html and "challenge" not in current_url:
                logger.warning(f"⏳ [{self.platform_name.upper()}] La página aún está cargando elementos... ({wait_seconds}s)")
            
        return html

    def parse_job_card(self, card_soup):
        selectors = self.p_cfg['selectors']
        job_id = self._extract_field(card_soup, selectors['job_id'])
        if job_id == "No especificado": return None

        title = self._extract_field(card_soup, selectors['title'])
        company = self._extract_field(card_soup, selectors['company'])
        salary = self._extract_field(card_soup, selectors.get('salary', 'NONE'))
        if title == "No especificado": return None

        link_format = self.p_cfg.get('link_format', '')
        link = link_format.format(job_id=job_id) if link_format else ""

        return JobOffer(
            job_id=str(job_id), title=title, company=company, 
            salary=salary, link=link, platform=self.platform_name.capitalize(), 
            timestamp_found=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )

    def scrape_keyword(self, keyword: str, found_job_ids: set):
        keyword_formatted = keyword.replace(' ', '%20')
        base_url = self.p_cfg['base_url'].format(keyword=keyword_formatted)
        pag_cfg = self.p_cfg['pagination']
        sel_rules = self.p_cfg.get('selenium_rules', {})
        
        current_pag_val = pag_cfg['start']
        page_num = 1
        new_jobs = []
        processed_titles = {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}
        
        # Guardaremos los IDs de la página anterior para detectar bucles infinitos reales
        previous_page_job_ids = set()

        while page_num <= self.p_cfg.get('max_pages', 50):
            url = f"{base_url}&{pag_cfg['param']}={current_pag_val}" if current_pag_val > 0 else base_url
            
            logger.info(f"[{self.platform_name.upper()}] Scrapeando '{keyword}' - Pág {page_num}...")
            
            html = self._get_html_selenium(url)
            if not html: break

            soup = BeautifulSoup(html, 'lxml')
            card_selector = self.p_cfg['selectors']['card']
            job_cards = soup.select(card_selector)
            
            if not job_cards: break

            found_on_page = 0
            current_page_job_ids = set()

            for card in job_cards:
                job_offer = self.parse_job_card(card)
                if not job_offer: continue
                
                # Agregamos a la lista de la página actual para el comparador de bucle
                current_page_job_ids.add(job_offer.job_id)

                is_valid, r_type, _ = filter_job_by_title(job_offer.title, self.config['search_filters'])
                if not is_valid:
                    processed_titles[r_type].append(job_offer.title)
                    continue

                if job_offer.job_id not in found_job_ids:
                    new_jobs.append(job_offer)
                    found_job_ids.add(job_offer.job_id)
                    processed_titles['included'].append(job_offer.title)
                    found_on_page += 1

            logger.info(f"[{self.platform_name.upper()}] Pág {page_num} completada. Nuevas: +{found_on_page}")
            
            # --- DETECCIÓN VISUAL Y LÓGICA DE FIN DE PAGINACIÓN ---
            
            # 1. El botón de Siguiente existe, pero está desactivado (Ej: OCC, LinkedIn a veces)
            stop_present = sel_rules.get('stop_pagination_if_present')
            if stop_present and soup.select_one(stop_present):
                logger.info(f"[{self.platform_name.upper()}] Última página detectada por interfaz (Botón Siguiente desactivado).")
                break
                
            # 2. El botón de Siguiente desapareció del HTML (Ej: Indeed, LinkedIn al final)
            stop_missing = sel_rules.get('stop_pagination_if_missing')
            if stop_missing:
                pagination_container_loaded = soup.find(class_=lambda x: x and ('pagination' in x.lower() or 'serp-page' in x.lower()))
                if pagination_container_loaded and not soup.select_one(stop_missing):
                    logger.info(f"[{self.platform_name.upper()}] Última página detectada por interfaz (Botón Siguiente no existe).")
                    break

            # 3. BUCLE INFINITO REAL: ¿La página actual me dio las mismas tarjetas que la página anterior?
            if current_page_job_ids and current_page_job_ids == previous_page_job_ids:
                logger.info(f"[{self.platform_name.upper()}] El portal devolvió los mismos resultados que la página anterior. Forzando fin.")
                break
            
            # Guardar el estado para la siguiente iteración
            previous_page_job_ids = current_page_job_ids

            current_pag_val += pag_cfg['increment']
            page_num += 1
            time.sleep(self.p_cfg.get('delay_between_pages', self.config['timing']['delay_between_keywords']))

        return new_jobs, processed_titles