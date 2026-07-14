import os
import pandas as pd
from typing import Dict, Any
from config.settings import settings
from modules.loader import ExcelLoader
from utils.logger import logger
from modules.matcher import normalize_title

class DocenzeParser:
    """Parser for riepilogo_docenze.xlsx. Extracts total teaching cost mapped by course code or title."""
    
    def __init__(self, file_path: str):
        self.file_path = file_path

    def parse(self) -> Dict[str, Dict[str, float]]:
        """
        Parses the docenze spreadsheet and returns a dictionary with two mappings:
          - 'by_code': Dict[str, float] (course_code -> total_cost)
          - 'by_title': Dict[str, float] (normalized_title -> total_cost)
        """
        parsed_data = {"by_code": {}, "by_title": {}}
        
        sheet_names = ExcelLoader.list_sheets(self.file_path)
        if not sheet_names:
            logger.error("Nessun foglio trovato in riepilogo_docenze.xlsx")
            return parsed_data
            
        sheet_name = "Compensi x corso" if "Compensi x corso" in sheet_names else sheet_names[0]
        
        # Read the sheet without headers to inspect starting from row 0
        df = ExcelLoader.read_sheet(self.file_path, sheet_name, header=None)
        if df is None or df.empty:
            return parsed_data
            
        # Find the header row by searching for "cod.ev."
        header_row_idx = None
        for idx in range(len(df)):
            row_vals = [str(x).strip().lower() for x in df.iloc[idx] if pd.notnull(x)]
            if "cod.ev." in row_vals or "cod. ev." in row_vals:
                header_row_idx = idx
                break
                
        if header_row_idx is None:
            logger.error("Impossibile trovare la riga di intestazione (con 'Cod.Ev.') in riepilogo_docenze.xlsx")
            return parsed_data
            
        header_row = df.iloc[header_row_idx]
        
        # Identify columns
        code_col = None
        title_col = None
        
        for col_idx in range(len(header_row)):
            val = str(header_row[col_idx]).strip().lower()
            if val in ["cod.ev.", "cod. ev."]:
                code_col = col_idx
            elif val == "titolo":
                title_col = col_idx
                
        # Total per course is in the last column
        total_col = len(header_row) - 1
        
        if code_col is None or title_col is None:
            logger.error(f"Colonne richieste non trovate in riepilogo_docenze (code_col={code_col}, title_col={title_col})")
            return parsed_data
            
        by_code = {}
        by_title = {}
        
        current_code = None
        current_title = None
        
        # Parse data rows starting after header_row_idx
        for idx in range(header_row_idx + 1, len(df)):
            row = df.iloc[idx]
            
            code_val = row[code_col]
            title_val = row[title_col]
            
            code_str = str(code_val).strip() if pd.notnull(code_val) else ""
            title_str = str(title_val).strip() if pd.notnull(title_val) else ""
            
            # Skip overall total summary rows
            if code_str.lower() in ["totali", "totale", "cod.ev.", "cod. ev."]:
                current_code = None
                current_title = None
                continue
                
            # Detect title change to boundary distinct courses
            if title_str and title_str.lower() != "titolo":
                if current_title is None:
                    current_title = title_str
                    current_code = code_str if code_str else None
                elif normalize_title(title_str) != normalize_title(current_title):
                    # Title has changed: update title tracker and reset/update code tracker
                    current_title = title_str
                    current_code = code_str if code_str else None
                else:
                    # Same title: if a code is explicitly provided, update code tracker
                    if code_str:
                        current_code = code_str
            elif code_str:
                current_code = code_str
                
            # If we are inside a valid course title block
            if current_code or current_title:
                total_val = row[total_col]
                if pd.notnull(total_val):
                    try:
                        cost = float(total_val)
                    except ValueError:
                        cost = 0.0
                        
                    if cost > 0:
                        if current_code:
                            by_code[current_code] = by_code.get(current_code, 0.0) + cost
                        if current_title:
                            norm_title = normalize_title(current_title)
                            by_title[norm_title] = by_title.get(norm_title, 0.0) + cost
                            
        filename = ExcelLoader.get_file_name(self.file_path)
        logger.info(f"Parsing di {filename} completato con successo: trovati {len(by_code)} corsi con compensi consolidati.")
        
        parsed_data["by_code"] = by_code
        parsed_data["by_title"] = by_title
        return parsed_data
