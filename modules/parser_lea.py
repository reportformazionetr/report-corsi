import os
import pandas as pd
from typing import Dict, Any
from config.settings import settings
from modules.loader import ExcelLoader
from utils.logger import logger

class LeaParser:
    """Parser for lea_corsi.xlsx. Supports both course-aggregated and participant-level structures."""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.columns_map = settings["columns"]["lea"]

    def parse(self) -> Dict[str, Dict[str, int]]:
        """
        Parses the LEA spreadsheet and returns a dictionary mapping:
        Course Title -> Dict containing:
          - 'effettivi': int
          - 'crediti_ecm': int
        """
        parsed_data: Dict[str, Dict[str, int]] = {}
        
        sheet_names = ExcelLoader.list_sheets(self.file_path)
        if not sheet_names:
            logger.error("Nessun foglio trovato in lea_corsi.xlsx")
            return {}
            
        sheet_name = "Tabella dati" if "Tabella dati" in sheet_names else sheet_names[0]
        
        # skiprows=4 since row index 4 in Excel sheet (the 5th row) contains the actual table headers
        df = ExcelLoader.read_sheet(self.file_path, sheet_name, skiprows=4)
        if df is None:
            return {}
            
        # Clean headers
        df.columns = [str(c).strip() for c in df.columns]
        
        mapped = {}
        for key, expected_name in self.columns_map.items():
            if expected_name in df.columns:
                mapped[key] = expected_name
            else:
                found = False
                for c in df.columns:
                    if c.lower() == expected_name.lower():
                        mapped[key] = c
                        found = True
                        break
                if not found:
                    mapped[key] = None
                    
        title_col = mapped.get("titolo")
        if not title_col:
            logger.error("Colonna Titolo Corso non trovata nel file LEA.")
            return {}
            
        part_id_col = mapped.get("partecipante_id")
        if not part_id_col:
            for col in df.columns:
                if any(x in col.lower() for x in ["codice fiscale", "cf", "matricola", "discente", "partecipante", "cognome"]):
                    part_id_col = col
                    break
        
        iscritti_col = mapped.get("iscritti")
        effettivi_col = mapped.get("effettivi")
        crediti_ecm_col = mapped.get("crediti_ecm")
        
        has_aggregates = any([iscritti_col, effettivi_col, crediti_ecm_col])
        is_course_level = has_aggregates and len(df) <= df[title_col].nunique() * 1.2
        
        filename = ExcelLoader.get_file_name(self.file_path)
        logger.info(f"Struttura rilevata in {filename}: "
                    f"{'Livello Corso (Aggregato)' if is_course_level else 'Livello Partecipante (Dettagliato)'}")
        
        if is_course_level:
            # We read direct aggregates
            for idx, row in df.iterrows():
                title_val = row.get(title_col)
                if pd.isnull(title_val) or not str(title_val).strip():
                    continue
                title = str(title_val).strip()
                
                # Parse effettivi
                eff_col = effettivi_col or iscritti_col
                eff_val = row.get(eff_col) if eff_col else 0
                effettivi = 0
                if pd.notnull(eff_val):
                    try:
                        effettivi = int(float(str(eff_val).strip()))
                    except ValueError:
                        pass
                
                # Parse crediti_ecm
                ecm_col = crediti_ecm_col or eff_col
                ecm_val = row.get(ecm_col) if ecm_col else 0
                crediti_ecm = 0
                if pd.notnull(ecm_val):
                    try:
                        crediti_ecm = int(float(str(ecm_val).strip()))
                    except ValueError:
                        pass
                
                # Combine duplicates if the same title appears multiple times
                entry = parsed_data.setdefault(title, {"effettivi": 0, "crediti_ecm": 0})
                entry["effettivi"] += effettivi
                entry["crediti_ecm"] += crediti_ecm
        else:
            # Participant level
            logger.info(f"Deduplica e conteggio dei partecipanti per ciascun corso.")
            grouped = df.groupby(title_col)
            
            for title_val, group in grouped:
                if pd.isnull(title_val) or not str(title_val).strip():
                    continue
                title = str(title_val).strip()
                
                # Count effettivi
                if part_id_col:
                    effettivi = group[part_id_col].dropna().nunique()
                else:
                    effettivi = len(group)
                    logger.warning(f"Impossibile deduplicare i partecipanti per il corso '{title}': "
                                   f"nessuna colonna CF trovata. Conteggio righe.")
                    
                # Count crediti_ecm
                crediti_ecm = effettivi
                if crediti_ecm_col and crediti_ecm_col in group.columns:
                    sub_group = group[group[crediti_ecm_col].astype(str).str.lower().str.strip().isin(["si", "sì", "yes", "1", "1.0", "true"])]
                    if part_id_col:
                        crediti_ecm = sub_group[part_id_col].dropna().nunique()
                    else:
                        crediti_ecm = len(sub_group)
                        
                entry = parsed_data.setdefault(title, {"effettivi": 0, "crediti_ecm": 0})
                entry["effettivi"] += effettivi
                entry["crediti_ecm"] += crediti_ecm
                                    
        logger.info(f"Parsing LEA completato: trovati dati partecipanti per {len(parsed_data)} titoli.")
        return parsed_data
