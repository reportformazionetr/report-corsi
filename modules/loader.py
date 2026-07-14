import os
import pandas as pd
from typing import List, Optional
from utils.logger import logger

class ExcelLoader:
    """Utility class to read Excel files and sheets with safety checks."""
    
    @staticmethod
    def get_file_name(file_source) -> str:
        if hasattr(file_source, "name"):
            return file_source.name
        if isinstance(file_source, str):
            return os.path.basename(file_source)
        return str(file_source)
    
    @staticmethod
    def list_sheets(file_path) -> List[str]:
        try:
            xl = pd.ExcelFile(file_path)
            return xl.sheet_names
        except Exception as e:
            filename = ExcelLoader.get_file_name(file_path)
            logger.error(f"Errore durante l'apertura del file {filename}: {e}")
            return []

    @staticmethod
    def read_sheet(file_path, sheet_name: str, skiprows: int = 0, **kwargs) -> Optional[pd.DataFrame]:
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, skiprows=skiprows, **kwargs)
            filename = ExcelLoader.get_file_name(file_path)
            logger.info(f"Caricato foglio '{sheet_name}' da '{filename}' - Lette {len(df)} righe.")
            return df
        except Exception as e:
            filename = ExcelLoader.get_file_name(file_path)
            logger.error(f"Errore durante la lettura del foglio '{sheet_name}' da '{filename}': {e}")
            return None
