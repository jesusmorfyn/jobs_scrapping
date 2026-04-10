import re
import time
import logging
from bs4 import BeautifulSoup
from datetime import datetime
from selenium.webdriver.common.by import By

from .base import BaseScraper
from core.models import JobOffer
from core.filter import filter_job_by_title
from utils.selenium_utils import close_cookie_popup, block_heavy_content, apply_stealth, load_cookies

logger = logging.getLogger(__name__)

class GenericScraper(BaseScraper):
    def __init__(self, config, platform_name, driver):
        super().__init__(config, platform_name)
        self.driver = driver
        self.p_cfg = self.config['platforms'][self.platform_name]

    def initialize_session(self):
        """Se ejecuta UNA SOLA VEZ cuando el contenedor nace."""
        logger.info(f"[{self.platform_name.upper()}] Inicializando sesión y camuflaje...")
        
        # 1. Aplicamos camuflaje (CDP se mantiene activo en toda la pestaña)
        apply_stealth(self.driver)
        
        # 2. Navegamos al dominio raíz para poder inyectar cookies
        # Usamos una URL genérica tonta (como un 404 o robots.txt) para no alertar al servidor
        base_url = self.p_cfg['base_url']
        domain = "/".join(base_url.split('/')[:3]) 
        self.driver.get(domain + "/robots.txt")
        time.sleep(1)
        
        # 3. Inyectamos cookies e instruimos bloqueo de imágenes
        load_cookies(self.driver, self.platform_name)
        block_heavy_content(self.driver)

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
        
        if url:
            # Como ya inyectamos cookies en initialize_session, solo navegamos directo
            self.driver.get(url)
            
            # --- APLICAR ZOOM CONFIGURABLE ---
            zoom_level = sel_rules.get('browser_zoom', 1.0)
            if zoom_level != 1.0:
                percentage = int(zoom_level * 100)
                logger.info(f"🔍 [{self.platform_name.upper()}] Aplicando zoom del {percentage}%...")
                self.driver.execute_script(f"document.body.style.zoom='{percentage}%'")
            
            time.sleep(2)

        wait_seconds = 0
        while True:
            # Re-aplicar zoom si la plataforma resetea el body al navegar
            zoom_level = sel_rules.get('browser_zoom', 1.0)
            if zoom_level != 1.0:
                self.driver.execute_script(f"document.body.style.zoom='{int(zoom_level * 100)}%'")

            current_html = self.driver.page_source
            current_url = self.driver.current_url.lower()
            
            try: close_cookie_popup(self.driver, None)
            except: pass

            if "cf-wrapper" in current_html or "challenge" in current_url or "security check" in current_html.lower() or "just a moment" in current_html.lower():
                if wait_seconds % 15 == 0:
                    logger.warning(f"🚨 [{self.platform_name.upper()}] Bloqueo detectado. ({wait_seconds}s)")
            else:
                soup = BeautifulSoup(current_html, 'lxml')
                wait_sel = sel_rules.get('wait_for_selector', '')
                selectors = [s.strip() for s in wait_sel.split(',')] if wait_sel else []
                
                if wait_sel and any(soup.select(sel) for sel in selectors):
                    scroll_pane = sel_rules.get('scroll_pane_selector')
                    if scroll_pane:
                        try:
                            pane = self.driver.find_element(By.CSS_SELECTOR, scroll_pane)
                            last_height = self.driver.execute_script("return arguments[0].scrollHeight", pane)
                            for _ in range(5):
                                self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", pane)
                                time.sleep(1.5)
                                new_height = self.driver.execute_script("return arguments[0].scrollHeight", pane)
                                if new_height == last_height: break
                                last_height = new_height
                        except: pass
                    html = self.driver.page_source
                    break
                    
                no_res = sel_rules.get('no_results_text', 'xxxxxx')
                if no_res.lower() in current_html.lower():
                    logger.info(f"[{self.platform_name.upper()}] No hay resultados en esta página.")
                    break
                
            time.sleep(4)
            wait_seconds += 4
            if wait_seconds > 0 and wait_seconds % 60 == 0:
                logger.warning(f"⏳ [{self.platform_name.upper()}] Sigue esperando carga...")
            
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
        
        debug_mode = self.config['general'].get('debug_mode', False)
        
        page_num = 1
        new_jobs = []
        processed_titles = {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}
        previous_page_job_ids = set()

        logger.info(f"[{self.platform_name.upper()}] Scrapeando '{keyword}' - Pág {page_num}...")
        html = self._get_html_selenium(base_url)

        while page_num <= self.p_cfg.get('max_pages', 50):
            if not html: break

            soup = BeautifulSoup(html, 'lxml')
            card_selector = self.p_cfg['selectors']['card']
            job_cards = soup.select(card_selector)
            
            if not job_cards: break

            found_on_page = 0
            parsed_count = 0
            current_page_job_ids = set()
            page_debug_info = []

            for card in job_cards:
                job_offer = self.parse_job_card(card)
                if not job_offer:
                    if debug_mode:
                        page_debug_info.append("  [⚠️ Error Parseo] No se pudo extraer ID o Título de una tarjeta HTML.")
                    continue
                
                parsed_count += 1
                current_page_job_ids.add(job_offer.job_id)

                filtro_resultado = filter_job_by_title(job_offer.title, self.config['search_filters'])
                
                if isinstance(filtro_resultado, tuple):
                    if len(filtro_resultado) == 3:
                        is_valid, r_type, r_kw = filtro_resultado
                    elif len(filtro_resultado) == 2:
                        is_valid, r_type = filtro_resultado
                        r_kw = None
                    else:
                        is_valid, r_type, r_kw = False, "excluded_implicit", None
                else:
                    is_valid, r_type, r_kw = False, "excluded_implicit", None

                
                if not is_valid:
                    if r_type in processed_titles:
                        processed_titles[r_type].append(job_offer.title)
                    if debug_mode:
                        motivo = f"Prohibida: '{r_kw}'" if r_type == 'excluded_explicit' else "No tiene palabras requeridas"
                        page_debug_info.append(f"  [❌ Descartada] {job_offer.title} | Motivo: {motivo}")
                    continue

                if job_offer.job_id not in found_job_ids:
                    new_jobs.append(job_offer)
                    found_job_ids.add(job_offer.job_id)
                    processed_titles['included'].append(job_offer.title)
                    found_on_page += 1
                    if debug_mode:
                        page_debug_info.append(f"  [✨ NUEVA] {job_offer.title} | Empresa: {job_offer.company} | ID: {job_offer.job_id}")
                else:
                    if debug_mode:
                        page_debug_info.append(f"  [🔄 Duplicada] {job_offer.title} | (Ya está en tu CSV)")

            logger.info(f"[{self.platform_name.upper()}] Pág {page_num} lista. Tarjetas HTML: {len(job_cards)} | Extraídas: {parsed_count} | Nuevas para CSV: +{found_on_page}")
            
            if debug_mode and page_debug_info:
                logger.info(f"--- REPORTE DEBUG PÁG {page_num} ({self.platform_name.upper()}) ---")
                for info in page_debug_info:
                    logger.info(info)
                logger.info("-" * 45)

            # --- DETECCIÓN VISUAL DE FIN DE PAGINACIÓN ---
            stop_present = sel_rules.get('stop_pagination_if_present')
            if stop_present and soup.select_one(stop_present):
                break
                
            stop_missing = sel_rules.get('stop_pagination_if_missing')
            if stop_missing:
                pagination_container_loaded = soup.find(class_=lambda x: x and any('pagination' in c.lower() or 'serp-page' in c.lower() for c in (x if isinstance(x, list) else [str(x)])))
                if pagination_container_loaded and not soup.select_one(stop_missing):
                    break

            if current_page_job_ids and current_page_job_ids == previous_page_job_ids:
                break
            
            previous_page_job_ids = current_page_job_ids

            # --- TRANSICIÓN A LA SIGUIENTE PÁGINA ---
            next_btn_sel = sel_rules.get('next_button_selector')
            
            if next_btn_sel:
                try:
                    btn = self.driver.find_element(By.CSS_SELECTOR, next_btn_sel)
                    self.driver.execute_script("arguments[0].click();", btn)
                    time.sleep(self.p_cfg.get('delay_between_pages', 4))
                    html = self._get_html_selenium(url=None)
                except Exception:
                    break
            else:
                if not pag_cfg: break
                current_pag_val += pag_cfg.get('increment', 1)
                url = f"{base_url}&{pag_cfg['param']}={current_pag_val}"
                html = self._get_html_selenium(url)

            page_num += 1

        return new_jobs, processed_titles