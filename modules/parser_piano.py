import os
import pandas as pd
from typing import List
from models.course import Course
from config.settings import settings
from modules.loader import ExcelLoader
from utils.logger import logger

class PianoParser:
    """Parser for piano_unico_formazione.xlsx. Loads course definitions from all Area sheets."""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.columns_map = settings["columns"]["piano"]

    def parse(self) -> List[Course]:
        courses: List[Course] = []
        
        sheet_names = ExcelLoader.list_sheets(self.file_path)
        if not sheet_names:
            logger.error("Nessun foglio trovato in piano_unico_formazione.xlsx")
            return []
            
        area_sheets = [s for s in sheet_names if s.startswith("Area ")]
        logger.info(f"Fogli area individuati per il piano: {area_sheets}")
        
        course_counter = 1
        
        for sheet in area_sheets:
            # Skip the first row (skiprows=1) since row 0 is the area title block,
            # and row 1 contains the actual table headers
            df = ExcelLoader.read_sheet(self.file_path, sheet, skiprows=1)
            if df is None:
                continue
                
            # Log the mapping
            mapped_cols = {}
            for key, val in self.columns_map.items():
                val_clean = " ".join(str(val).split()).lower()
                found = False
                for col in df.columns:
                    col_clean = " ".join(str(col).split()).lower()
                    if col_clean == val_clean:
                        mapped_cols[key] = col
                        found = True
                        break
                if not found:
                    logger.warning(f"Colonna '{val}' (messa a '{key}') non trovata nel foglio '{sheet}'.")
            
            # Map required columns
            title_col = mapped_cols.get("titolo")
            if not title_col:
                logger.error(f"Impossibile procedere: colonna del Titolo Corso non trovata nel foglio '{sheet}'")
                continue
                
            ente_col = mapped_cols.get("ente")
            area_col = mapped_cols.get("area")
            ambito_col = mapped_cols.get("ambito")
            fonte_col = mapped_cols.get("fonte")
            
            rows_processed = 0
            for idx, row in df.iterrows():
                title_val = row.get(title_col)
                if pd.isnull(title_val) or not str(title_val).strip():
                    continue
                    
                # Extract details safely
                titolo = str(title_val).strip()
                ente = str(row.get(ente_col)).strip() if pd.notnull(row.get(ente_col)) else ""
                area = str(row.get(area_col)).strip() if pd.notnull(row.get(area_col)) else ""
                ambito = str(row.get(ambito_col)).strip() if pd.notnull(row.get(ambito_col)) else ""
                fonte = str(row.get(fonte_col)).strip() if pd.notnull(row.get(fonte_col)) else ""
                
                # Filter: keep only AO Terni courses
                if ente.strip().lower() != "ao terni":
                    continue
                    
                # Check for placeholders or empty descriptions
                if title_val == "Note" or title_val == "Titolo":
                    continue
                    
                course = Course(
                    n=course_counter,
                    ente_proponente=ente,
                    area=area,
                    ambito=ambito,
                    titolo=titolo,
                    fonte_finanziamento=fonte
                )
                courses.append(course)
                course_counter += 1
                rows_processed += 1
                
            logger.info(f"Elaborati {rows_processed} corsi nel foglio '{sheet}'")
            
        logger.info(f"Parsing del piano completato: trovati {len(courses)} corsi totali.")
        return courses
