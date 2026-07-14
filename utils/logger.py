import logging
from typing import List

# Memory handler to store logs for Streamlit UI
class StreamlitLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.logs: List[str] = []

    def emit(self, record):
        log_entry = self.format(record)
        self.logs.append(log_entry)

    def clear(self):
        self.logs.clear()

# Setup logger
logger = logging.getLogger("progetto_report_corsi")
logger.setLevel(logging.INFO)

# Avoid adding multiple handlers if re-imported
if not logger.handlers:
    # Console Handler
    c_handler = logging.StreamHandler()
    c_handler.setLevel(logging.INFO)
    c_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
    c_handler.setFormatter(c_format)
    logger.addHandler(c_handler)

    # Streamlit Memory Handler
    st_handler = StreamlitLogHandler()
    st_handler.setLevel(logging.INFO)
    st_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
    st_handler.setFormatter(st_format)
    logger.addHandler(st_handler)

def get_streamlit_logs() -> List[str]:
    for handler in logger.handlers:
        if isinstance(handler, StreamlitLogHandler):
            return handler.logs
    return []

def clear_streamlit_logs():
    for handler in logger.handlers:
        if isinstance(handler, StreamlitLogHandler):
            handler.clear()
