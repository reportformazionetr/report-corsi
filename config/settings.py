import os
import yaml

def load_settings() -> dict:
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"File di configurazione non trovato in {config_path}")
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            if not config:
                raise ValueError("Il file config.yaml è vuoto o non valido.")
            return config
    except Exception as e:
        # Raise descriptive error to help debugging configuration errors
        raise RuntimeError(f"Errore durante il caricamento di config.yaml: {e}")

settings = load_settings()
