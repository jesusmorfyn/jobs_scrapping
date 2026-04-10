import os
import pandas as pd
import logging

logger = logging.getLogger(__name__)

class CSVHandler:
    def __init__(self, filepath, columns):
        self.filepath = filepath
        self.columns = columns
        self.existing_df = None

    def get_existing_ids(self) -> set:
        found_job_ids = set()
        if os.path.exists(self.filepath):
            try:
                self.existing_df = pd.read_csv(self.filepath)
                if 'job_id' in self.existing_df.columns:
                    self.existing_df['job_id'] = self.existing_df['job_id'].astype(str)
                    found_job_ids = set(self.existing_df['job_id'].dropna().tolist())
                logger.info(f"Se cargaron {len(found_job_ids)} IDs existentes.")
            except Exception as e:
                logger.error(f"Error al leer CSV: {e}. Se creará uno nuevo.")
                self.existing_df = pd.DataFrame(columns=self.columns)
        else:
            self.existing_df = pd.DataFrame(columns=self.columns)
            
        return found_job_ids

    def save_jobs(self, new_jobs_dicts: list):
        new_df = pd.DataFrame(new_jobs_dicts)
        new_df['job_id'] = new_df['job_id'].astype(str)
        
        combined_df = pd.concat([self.existing_df, new_df], ignore_index=True)
        combined_df.dropna(subset=['job_id'], inplace=True)
        combined_df = combined_df[combined_df['job_id'] != 'None']
        combined_df.drop_duplicates(subset=['job_id'], keep='first', inplace=True)
        
        # Asegurar que todas las columnas existan
        for col in self.columns:
            if col not in combined_df.columns: 
                combined_df[col] = pd.NA
                
        combined_df[self.columns].to_csv(self.filepath, index=False, encoding='utf-8-sig')
        logger.info(f"Datos combinados guardados en '{self.filepath}' ({len(combined_df)} ofertas en total).")