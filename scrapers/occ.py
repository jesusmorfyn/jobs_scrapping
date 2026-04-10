import re
import time
import math
import requests
import logging
from bs4 import BeautifulSoup
from datetime import datetime
from .base import BaseScraper
from core.models import JobOffer
from core.filter import filter_job_by_title

logger = logging.getLogger(__name__)

class OCCScraper(BaseScraper):
    def __init__(self, config):
        super().__init__(config, 'occ')

    def get_total_results(self, soup):
        for selector in [soup.find('div', id='sort-jobs'), soup.find('p', string=re.compile(r'resultados')), soup.find('p', class_='text-sm font-light')]:
            if selector:
                text_element = selector.find_previous_sibling('p') if selector.name == 'div' else selector
                if text_element and 'resultados' in text_element.get_text():
                    match = re.search(r'(\d+)', text_element.get_text().replace(',', ''))
                    if match: return int(match.group(1))
        return 0

    def parse_job_card(self, card_soup):
        card_id = card_soup.get('id', '')
        match_id = re.search(r'\d+$', card_id)
        if not match_id: return None
        
        title_tag = card_soup.find('h2', class_='text-lg')
        title = title_tag.get_text(strip=True) if title_tag else None
        if not title: return None
        
        salary_tag = card_soup.find('span', class_='font-base')
        salary = salary_tag.get_text(strip=True) if salary_tag else "No especificado"
        
        company = "No especificado"
        company_section = card_soup.find('div', class_='flex flex-row justify-between items-center')
        if company_section:
            company_text = company_section.get_text(strip=True)
            company = "Empresa confidencial" if "Empresa confidencial" in company_text else company_text.split(' ')[0]

        return JobOffer(
            job_id=str(match_id.group(0)), title=title, company=company, 
            salary=salary, link=f"\"https://www.occ.com.mx/empleo/oferta/{match_id.group(0)}\"",
            platform='OCC', timestamp_found=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )

    def scrape_keyword(self, keyword: str, found_job_ids: set):
        keyword_formatted = keyword.replace(' ', '-')
        time_param = self.cfg['default_time_param_value']
        
        logger.info(f"--- Iniciando OCC para '{keyword}' ---")
        base_url = f"{self.cfg['base_url'].format(keyword=keyword_formatted)}&{self.cfg['time_param_name']}={time_param}"
        
        page = 1; max_pages = 1; new_jobs = []
        processed_titles = {'included': [], 'excluded_explicit': [], 'excluded_implicit': []}
        
        while True:
            try:
                url = f"{base_url}&page={page}" if page > 1 else base_url
                response = requests.get(url, headers=self.config['general']['headers'], timeout=self.cfg['request_timeout'])
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'lxml')
                
                job_cards = soup.find_all('div', id=lambda x: x and x.startswith('jobcard-'))
                if not job_cards: break
                
                if page == 1:
                    total_results = self.get_total_results(soup)
                    if total_results > 0 and len(job_cards) > 0:
                        max_pages = min(math.ceil(total_results / len(job_cards)), self.cfg.get('max_pages', 999))
                
                found_on_page = 0
                for card in job_cards:
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
                
                logger.info(f"OCC: Pág {page}. Nuevas: +{found_on_page}")
                if page >= max_pages: break
                page += 1
                time.sleep(self.config['timing']['delay_between_keywords'])
                
            except Exception as e:
                logger.error(f"OCC: Error en página {page}: {e}")
                break
                
        return new_jobs, processed_titles