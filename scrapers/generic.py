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

    def _get_html_selenium(self, url=None):
        sel_rules = self.p_cfg.get('selenium_rules', {})
        html = None
        
        with self.browser_lock:
            self.driver.switch_to.window(self.tab_handle)
            # Si pasamos URL, es carga inicial. Si es None, solo evaluamos la página actual tras un Click.
            if url:
                block_heavy_content(self.driver)
                self.driver.get(url)
                time.sleep(2) # Espera base anti-staleness

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
                        logger.warning(f"🚨 [{self.platform_name.upper()}] Bloqueo detectado. Esperando manual... ({wait_seconds}s)")
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
                                    time.sleep(1)
                                    new_height = self.driver.execute_script("return arguments[0].scrollHeight", pane)
                                    if new_height == last_height: break
                                    last_height = new_height
                            except: pass
                        html = self.driver.page_source
                        break
                        
                    # 3. Validar página vacía legítima
                    no_res = sel_rules.get('no_results_text', 'xxxxxx')
                    if no_res.lower() in current_html.lower():
                        logger.info(f"[{self.platform_name.upper()}] No hay resultados.")
                        break
                    
            time.sleep(4)
            wait_seconds += 4
            
            # Timeout de seguridad
            if wait_seconds > 60 and "cf-wrapper" not in current_html and "challenge" not in current_url:
                logger.warning(f"[{self.platform_name.upper()}] Timeout esperando elementos. Avanzando...")
                break
            
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
        sel_rules = self.p_cfg.get('selenium_rules', {})
        pag_cfg = self.p_cfg.get('pagination', {})
        current_pag_val = pag_cfg.get('start', 0)
        
        page_num = 1
        new_jobs = []
        processed_titles = {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}
        previous_page_job_ids = set()

        logger.info(f"[{self.platform_name.upper()}] Scrapeando '{keyword}' - Pág {page_num}...")
        # 1. Carga inicial
        html = self._get_html_selenium(base_url)

        while page_num <= self.p_cfg.get('max_pages', 50):
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
            
            # --- DETECCIÓN VISUAL DE FIN DE PAGINACIÓN ---
            stop_present = sel_rules.get('stop_pagination_if_present')
            if stop_present and soup.select_one(stop_present):
                break
                
            stop_missing = sel_rules.get('stop_pagination_if_missing')
            if stop_missing:
                # Buscamos el contenedor de forma segura (previniendo crasheos de librerías)
                pagination_container_loaded = soup.find(class_=lambda x: x and any('pagination' in c.lower() or 'serp-page' in c.lower() for c in (x if isinstance(x, list) else [str(x)])))
                if pagination_container_loaded and not soup.select_one(stop_missing):
                    break

            if current_page_job_ids and current_page_job_ids == previous_page_job_ids:
                break
            
            previous_page_job_ids = current_page_job_ids

            # --- TRANSICIÓN A LA SIGUIENTE PÁGINA ---
            next_btn_sel = sel_rules.get('next_button_selector')
            
            if next_btn_sel:
                # Paginación por Click (Recomendado para SPAs como LinkedIn)
                try:
                    btn = self.driver.find_element(By.CSS_SELECTOR, next_btn_sel)
                    self.driver.execute_script("arguments[0].click();", btn)
                    time.sleep(self.p_cfg.get('delay_between_pages', 4))
                    html = self._get_html_selenium(url=None) # No recargamos la URL, evaluamos la misma página
                except Exception:
                    break
            else:
                # Paginación Clásica por URL (Fallback)
                if not pag_cfg: break
                current_pag_val += pag_cfg.get('increment', 1)
                url = f"{base_url}&{pag_cfg['param']}={current_pag_val}"
                html = self._get_html_selenium(url)

            page_num += 1

        return new_jobs, processed_titles