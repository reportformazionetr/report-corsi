import os
import pandas as pd
from typing import Dict, List, Set, Any
from config.settings import settings
from modules.loader import ExcelLoader
from utils.logger import logger
from models.course import Edition

class ReportParser:
    """Parser for report_corsi_ 2026.xlsx. Extracts edition, credits, and teaching cost details."""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.columns_map = settings["columns"]["report"]

    def parse(self) -> Dict[str, Dict[str, Any]]:
        """
        Parses report spreadsheet and returns a dictionary indexed by Course Title.
        Value is a dictionary containing:
          - 'edizioni_concluse': int (unique count of valid edition codes)
          - 'crediti_formativi': float (max credit value found for the course)
          - 'ore_svolte': float (sum of edition hours, deduplicated per edition)
          - 'costo_totale_docenti': float (calculated using docenti rate rules)
          - 'corso_codici': Set[str] (set of course codes matched to this title)
        """
        parsed_data: Dict[str, Dict[str, Any]] = {}
        
        sheet_names = ExcelLoader.list_sheets(self.file_path)
        if not sheet_names:
            logger.error("Nessun foglio trovato in report_corsi_ 2026.xlsx")
            return {}
            
        sheet_name = "Report" if "Report" in sheet_names else sheet_names[0]
        df = ExcelLoader.read_sheet(self.file_path, sheet_name)
        if df is None:
            return {}
            
        # Clean column headers
        df.columns = [str(c).strip() for c in df.columns]
        
        # Mapped columns checklist
        mapped = {}
        for key, expected_name in self.columns_map.items():
            # Check exact match
            if expected_name in df.columns:
                mapped[key] = expected_name
            else:
                # Case-insensitive / strip match
                found = False
                for c in df.columns:
                    if c.lower() == expected_name.lower():
                        mapped[key] = c
                        found = True
                        break
                if not found:
                    mapped[key] = None
                    
        # Log which columns were mapped
        filename = ExcelLoader.get_file_name(self.file_path)
        logger.info(f"Colonne mappate in {filename}: {mapped}")
        
        title_col = mapped.get("titolo")
        if not title_col:
            logger.error(f"Colonna Titolo Corso '{self.columns_map['titolo']}' non trovata nel report.")
            return {}
            
        edition_col = mapped.get("edizione")
        corso_col = mapped.get("corso")
        crediti_col = mapped.get("crediti")
        
        # Check docenti columns presence
        docente_col = mapped.get("docente")
        ore_docente_col = mapped.get("ore_docente")
        tipo_orario_col = mapped.get("tipo_orario")
        costo_servizio_col = mapped.get("costo_servizio")
        costo_fuori_servizio_col = mapped.get("costo_fuori_servizio")
        ore_svolte_ed_col = mapped.get("ore_svolte_edizione")
        
        # Intermediate structures to group by course title
        # title -> { edition_code -> {'ore_svolte': float, 'crediti': float, 'docente_rows': list} }
        course_editions: Dict[str, Dict[str, Dict[str, Any]]] = {}
        course_codes: Dict[str, Set[str]] = {}
        
        for idx, row in df.iterrows():
            title_val = row.get(title_col)
            if pd.isnull(title_val) or not str(title_val).strip():
                continue
                
            course_title = str(title_val).strip()
            
            # Unify ACLS monthly courses to a single title
            import re
            if re.match(r"^ACLS\s+(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)$", course_title, re.IGNORECASE):
                course_title = "ACLS"
            
            # Skip header replication rows or garbage if any
            if course_title == "Corsi 2026" or course_title == "Note":
                continue
                
            # Track course codes linked to this title
            c_code = str(row.get(corso_col)).strip() if pd.notnull(row.get(corso_col)) else ""
            if c_code:
                course_codes.setdefault(course_title, set()).add(c_code)
                
            # Get edition code (Codice C / Edizione)
            edition_val = row.get(edition_col)
            # Default to an anonymous unique key if empty, but usually it represents edition.
            # Avoid counting "/" or "No ECM" or "Acc al 66" as multiple if they are just placeholders,
            # but let's count valid unique editions.
            edition_code = str(edition_val).strip() if pd.notnull(edition_val) else ""
            
            # Parse credits
            credits_val = row.get(crediti_col)
            credits_num = 0.0
            if pd.notnull(credits_val):
                try:
                    # Clean up credit strings like "No ECM"
                    credits_str = str(credits_val).replace(",", ".").strip()
                    credits_num = float(credits_str)
                except ValueError:
                    credits_num = 0.0
                    
            # Parse hours svolte for the edition
            hours_svolte_num = 0.0
            if ore_svolte_ed_col and pd.notnull(row.get(ore_svolte_ed_col)):
                try:
                    hours_svolte_num = float(str(row.get(ore_svolte_ed_col)).replace(",", ".").strip())
                except ValueError:
                    hours_svolte_num = 0.0
            
            # Parse docente details for cost calculation
            docente = str(row.get(docente_col)).strip() if docente_col and pd.notnull(row.get(docente_col)) else None
            ore_docente = 0.0
            if ore_docente_col and pd.notnull(row.get(ore_docente_col)):
                try:
                    ore_docente = float(str(row.get(ore_docente_col)).replace(",", ".").strip())
                except ValueError:
                    ore_docente = 0.0
                    
            tipo_orario = str(row.get(tipo_orario_col)).strip().lower() if tipo_orario_col and pd.notnull(row.get(tipo_orario_col)) else ""
            
            costo_servizio = 0.0
            if costo_servizio_col and pd.notnull(row.get(costo_servizio_col)):
                try:
                    costo_servizio = float(str(row.get(costo_servizio_col)).replace(",", ".").strip())
                except ValueError:
                    costo_servizio = 0.0
                    
            costo_fuori = 0.0
            if costo_fuori_servizio_col and pd.notnull(row.get(costo_fuori_servizio_col)):
                try:
                    costo_fuori = float(str(row.get(costo_fuori_servizio_col)).replace(",", ".").strip())
                except ValueError:
                    costo_fuori = 0.0
                    
            # Grouping by course and edition code
            course_editions.setdefault(course_title, {})
            
            # Since edition_code could be empty (e.g. just a course title placeholder row),
            # we only record edition details if edition code is valid and not "/" or "Acc al ..." or empty.
            is_valid_edition = edition_code and edition_code not in ["/", "Ann.to", "Acc al 66", "Acc al 67", "Acc al 47", "Acc al 97", "Villa um.", "AUSL 1"]
            
            if is_valid_edition:
                edition_entry = course_editions[course_title].setdefault(edition_code, {
                    "ore_svolte": hours_svolte_num,
                    "crediti": credits_num,
                    "docente_rows": []
                })
                # Update with max credits or hours if found
                edition_entry["crediti"] = max(edition_entry["crediti"], credits_num)
                edition_entry["ore_svolte"] = max(edition_entry["ore_svolte"], hours_svolte_num)
                
                # Add teacher details if a teacher name is present
                if docente:
                    edition_entry["docente_rows"].append({
                        "docente": docente,
                        "ore": ore_docente,
                        "tipo_orario": tipo_orario,
                        "costo_servizio": costo_servizio,
                        "costo_fuori": costo_fuori
                    })
            else:
                # If there's no valid edition but credit info is on this row, let's track it
                # We can create a special key for course level metadata
                meta_entry = course_editions[course_title].setdefault("__course_meta__", {
                    "crediti": 0.0,
                    "docente_rows": []
                })
                meta_entry["crediti"] = max(meta_entry["crediti"], credits_num)
                if docente:
                    meta_entry["docente_rows"].append({
                        "docente": docente,
                        "ore": ore_docente,
                        "tipo_orario": tipo_orario,
                        "costo_servizio": costo_servizio,
                        "costo_fuori": costo_fuori
                    })
        
        # Now consolidate intermediate structures into final output
        for course_title, editions in course_editions.items():
            unique_valid_editions = [k for k in editions.keys() if k != "__course_meta__"]
            edizioni_concluse = len(unique_valid_editions)
            
            # Find max credits formativi across editions and course meta
            max_credits = 0.0
            for ed_code, ed_data in editions.items():
                max_credits = max(max_credits, ed_data["crediti"])
                
            # Sum hours svolte per unique edition
            total_ore_svolte = sum(editions[ed_code]["ore_svolte"] for ed_code in unique_valid_editions)
            
            # Calculate total docente costs
            total_docenti_cost = 0.0
            docenti_logged_warning = False
            
            for ed_code, ed_data in editions.items():
                for d_row in ed_data["docente_rows"]:
                    tipo = d_row["tipo_orario"]
                    ore = d_row["ore"]
                    
                    if "fuori servizio" in tipo or "fuori" in tipo:
                        rate = d_row["costo_fuori"]
                    elif "in servizio" in tipo or "servizio" in tipo:
                        rate = d_row["costo_servizio"]
                    else:
                        rate = 0.0
                        if not docenti_logged_warning:
                            logger.warning(f"Tipo orario docente '{tipo}' non riconosciuto per il corso '{course_title}'. Applicato costo orario pari a 0.")
                            docenti_logged_warning = True
                            
                    total_docenti_cost += ore * rate
                    
            # Check if teaching columns were altogether missing
            if not docente_col and not ore_docente_col:
                # We expect this for our sample file
                # Do not spam warnings, just log once at system level
                pass
                
            parsed_data[course_title] = {
                "edizioni_concluse": edizioni_concluse,
                "crediti_formativi": max_credits,
                "ore_svolte": total_ore_svolte,
                "costo_totale_docenti": total_docenti_cost,
                "corso_codici": course_codes.get(course_title, set())
            }
            
        logger.info(f"Parsing del report completato: caricati dati per {len(parsed_data)} titoli unici.")
        return parsed_data
