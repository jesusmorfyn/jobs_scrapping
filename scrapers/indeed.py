import time
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

class IndeedScraper(BaseScraper):
    def __init__(self, config, driver):
        super().__init__(config, 'indeed')
        self.driver = driver

    def parse_job_card(self, card_soup):
        a_tag = card_soup.find('a', class_=lambda x: x and 'jcs-JobTitle' in x)
        if not a_tag: return None
        
        job_id = a_tag.get('data-jk')
        if not job_id: return None
        
        title_tag = card_soup.find('span', id=lambda x: x and str(x).startswith('jobTitle-'))
        title = title_tag.get_text(strip=True) if title_tag else a_tag.get_text(strip=True)
        if not title or title == "": return None
        
        company_tag = card_soup.find('span', {'data-testid': 'company-name'})
        company = company_tag.get_text(strip=True) if company_tag else "No especificado"
        
        salary = "No especificado"
        salary_tag = card_soup.find(lambda tag: tag.has_attr('data-testid') and 'salary-snippet-container' in tag['data-testid'])
        if salary_tag:
            salary = salary_tag.get_text(strip=True)
        else:
            metadata_group = card_soup.find('div', class_=lambda x: x and 'jobMetaDataGroup' in x)
            if metadata_group:
                for text in metadata_group.stripped_strings:
                    if '$' in text:
                        salary = text
                        break

        return JobOffer(
            job_id=str(job_id), title=title, company=company, 
            salary=salary, link=f"\"https://mx.indeed.com/viewjob?jk={job_id}\"",
            platform='Indeed', timestamp_found=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )

    def scrape_keyword(self, keyword: str, found_job_ids: set):
        if not self.driver: return [], {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}
        
        keyword_formatted = keyword.replace(' ', '+')
        time_param = self.cfg['default_time_param_value']
        
        logger.info(f"--- Iniciando Indeed para '{keyword}' ---")
        base_url = f"{self.cfg['base_url']}&{self.cfg['time_param_name']}={time_param}"
        
        page = 1; new_jobs = []
        processed_titles = {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}
        wait_long = WebDriverWait(self.driver, self.cfg['request_timeout_selenium'])
        wait_short = WebDriverWait(self.driver, 3)
        
        while page <= self.cfg.get('max_pages', 999):
            start_index = (page - 1) * self.cfg['page_increment']
            self.driver.get(base_url.format(keyword=keyword_formatted, start=start_index))
            close_cookie_popup(self.driver, wait_short)
            
            try:
                if "challenge-platform" in self.driver.page_source or "Cloudflare" in self.driver.page_source:
                    logger.warning("⚠️ Indeed está mostrando un Captcha/Cloudflare. Resuélvelo manualmente.")
                    time.sleep(10)
                
                if self.driver.find_elements(By.XPATH, "//*[contains(text(), 'no produjo ningún resultado') or contains(text(), 'did not match any jobs')]"):
                    logger.info("Indeed: 'Sin resultados' detectado.")
                    break
                    
                wait_long.until(EC.presence_of_element_located((By.ID, "mosaic-provider-jobcards")))
                time.sleep(3)
                
                soup = BeautifulSoup(self.driver.page_source, 'lxml')
                jobcards_container = soup.find('div', id='mosaic-provider-jobcards')
                if not jobcards_container: break
                
                ul_list = jobcards_container.find('ul')
                job_cards_li = []
                if ul_list:
                    for li in ul_list.find_all('li', recursive=False):
                        if li.find('div', class_=lambda x: x and 'cardOutline' in x):
                            job_cards_li.append(li)
                
                if not job_cards_li: break
                    
                found_on_page = 0
                for card in job_cards_li:
                    job_offer = self.parse_job_card(card)
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
                
                logger.info(f"Indeed: Pág {page}. Nuevas: +{found_on_page}")
                
                try:
                    next_button = self.driver.find_element(By.CSS_SELECTOR, "a[data-testid='pagination-page-next']")
                    if "disabled" in next_button.get_attribute("class"): break
                except NoSuchElementException:
                    break
                    
                page += 1
                time.sleep(self.cfg.get('delay_between_pages_selenium', 3))
                
            except TimeoutException:
                logger.error(f"Indeed: Timeout en página {page}.")
                break
            except Exception as e:
                logger.error(f"Indeed: Error en página {page}: {e}")
                break
                
        return new_jobs, processed_titles