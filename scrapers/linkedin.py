import re
import time
import math
import logging
from bs4 import BeautifulSoup
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from .base import BaseScraper
from core.models import JobOffer
from core.filter import filter_job_by_title
from utils.selenium_utils import close_cookie_popup

logger = logging.getLogger(__name__)

class LinkedinScraper(BaseScraper):
    def __init__(self, config, driver):
        super().__init__(config, 'linkedin')
        self.driver = driver

    def get_total_results(self):
        try:
            subtitle_element = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(@class, 'jobs-search-results-list__text') or contains(@class, 'jobs-search-results-list__subtitle')]"))
            )
            clean_text = subtitle_element.text.replace(',', '').replace('+', '')
            match = re.search(r'(\d+)', clean_text)
            if match:
                total = int(match.group(1))
                limit = self.cfg['max_pages'] * self.cfg['page_increment']
                return limit if total > limit else total
            return 0
        except TimeoutException:
            try:
                self.driver.find_element(By.CSS_SELECTOR, "main[class*='scaffold-layout__list'] div[data-job-id]")
                return self.cfg['page_increment']
            except NoSuchElementException:
                return 0

    def parse_job_card(self, job_div):
        job_id = job_div.get('data-job-id')
        if not job_id: return None

        title = "No especificado"
        title_link = job_div.find('a', class_=lambda x: x and 'job-card-list__title--link' in x)
        if title_link:
            strong_tag = title_link.find('strong')
            title = strong_tag.get_text(strip=True) if strong_tag else title_link.get_text(strip=True)

        company = "No especificado"
        company_div = job_div.find('div', class_=lambda x: x and 'artdeco-entity-lockup__subtitle' in x)
        if company_div: company = company_div.get_text(strip=True)

        if title == "No especificado" or company == "No especificado": return None

        return JobOffer(
            job_id=str(job_id), title=title, company=company, 
            salary="No especificado", link=f"\"https://www.linkedin.com/jobs/view/{job_id}\"",
            platform='LinkedIn', timestamp_found=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )

    def scrape_keyword(self, keyword: str, found_job_ids: set):
        if not self.driver: return [], {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}
        
        keyword_formatted = keyword.replace(' ', '%20')
        time_param = self.cfg['default_time_param_value']
        logger.info(f"--- Iniciando LinkedIn para '{keyword}' ---")
        base_url = f"{self.cfg['base_url'].format(keyword=keyword_formatted)}&{self.cfg['time_param_name']}={time_param}"
        
        page = 1; max_pages = 1; new_jobs = []
        processed_titles = {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}
        wait_long = WebDriverWait(self.driver, self.cfg['request_timeout_selenium'])
        wait_short = WebDriverWait(self.driver, 5)
        
        while True:
            start_index = (page - 1) * self.cfg['page_increment']
            self.driver.get(f"{base_url}&start={start_index}" if page > 1 else base_url)
            time.sleep(5)
            close_cookie_popup(self.driver, wait_short)
            
            if self.driver.find_elements(By.XPATH, "//*[contains(@class, 'jobs-search-no-results')]"):
                logger.info("LinkedIn: 'Sin resultados' detectado.")
                break
                
            try:
                wait_long.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-job-id]")))
                
                if page == 1:
                    total_results = self.get_total_results()
                    max_pages = min(math.ceil(total_results / self.cfg['page_increment']), self.cfg['max_pages']) if total_results > 0 else 1
                
                try:
                    pane = self.driver.find_element(By.CSS_SELECTOR, "div.jobs-search-results-list")
                    self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", pane)
                    time.sleep(2)
                except: pass
                    
                job_divs = BeautifulSoup(self.driver.page_source, 'lxml').find_all('div', attrs={'data-job-id': True})
                if not job_divs: break
                    
                found_on_page = 0
                for div in job_divs:
                    job_offer = self.parse_job_card(div)
                    if not job_offer: continue
                    
                    is_valid, r_type, r_kw = filter_job_by_title(job_offer.title, self.config['search_filters'])
                    if not is_valid:
                        processed_titles[r_type].append(job_offer.title)
                        continue
                        
                    if job_offer.job_id not in found_job_ids:
                        new_jobs.append(job_offer)
                        found_job_ids.add(job_offer.job_id)
                        processed_titles['included'].append(job_offer.title)
                        found_on_page += 1
                        
                logger.info(f"LinkedIn: Pág {page}/{max_pages}. Nuevas: +{found_on_page}")
                if page >= max_pages: break
                page += 1
                time.sleep(self.cfg.get('delay_between_pages_selenium', 3))
                
            except TimeoutException:
                logger.error(f"LinkedIn: Timeout en página {page}.")
                break
                
        return new_jobs, processed_titles