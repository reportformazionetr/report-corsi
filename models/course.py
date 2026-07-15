from dataclasses import dataclass, field
from typing import Optional, List

@dataclass
class Course:
    n: int
    ente_proponente: str
    area: str
    ambito: str
    titolo: str
    fonte_finanziamento: str
    edizioni_concluse: int = 0
    edizioni_da_completare: str = ""
    crediti_formativi: float = 0.0
    ore_svolte: float = 0.0
    partecipanti_effettivi: int = 0
    numero_partecipanti: int = 0
    spesa_sostenuta: float = 0.0
    dettaglio_calcolo: str = ""
    note: str = ""

    @property
    def crediti_x_partecipanti(self) -> float:
        cf = self.crediti_formativi or 0.0
        np = self.numero_partecipanti or 0
        return round(cf * np, 2)

@dataclass
class Edition:
    codice_corso: str
    codice_edizione: str
    titolo: str
    crediti: float
    trimestre: str
    stato: str
    docenti: List[dict] = field(default_factory=list)
    ore_svolte: float = 0.0

@dataclass
class MatchCandidate:
    piano_title: str
    matched_title: str
    score: float
    source_file: str # 'report' or 'lea'
    confirmed: Optional[bool] = None
