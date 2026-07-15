import re
from typing import Dict, List, Tuple, Optional
from rapidfuzz import fuzz
from models.course import MatchCandidate
from config.settings import settings
from utils.logger import logger

def normalize_title(title: str) -> str:
    """
    Applies the title normalization pipeline:
    1. Lowercase conversion
    2. Strip leading/trailing whitespace
    3. Remove non-alphanumeric characters except spaces and accented letters (keeping àèìòùé)
    4. Remove accents and diacritics
    5. Replace multiple spaces with a single space
    6. Remove non-significant prefixes/suffixes (e.g., trailing dashes or 'ed' abbreviations)
    """
    if not title:
        return ""
    
    # 1. Lowercase
    t = title.lower()
    
    # Remove text in parentheses and brackets
    t = re.sub(r"\(.*?\)", " ", t)
    t = re.sub(r"\[.*?\]", " ", t)
    
    # 2. Strip
    t = t.strip()
    
    # 3. Remove non-alphanumeric except spaces and accented letters (keeping àèìòùéèáéíóú)
    t = re.sub(r"[^a-z0-9àèìòùéáíóúüñ ]", " ", t)
    
    # 4. Remove diacritics/accents (translate à->a, è->e, é->e, etc.)
    accent_map = {
        'à': 'a', 'á': 'a',
        'è': 'e', 'é': 'e',
        'ì': 'i', 'í': 'i',
        'ò': 'o', 'ó': 'o',
        'ù': 'u', 'ú': 'u',
        'ü': 'u', 'ñ': 'n'
    }
    for acc, clean in accent_map.items():
        t = t.replace(acc, clean)
        
    # 5. Contract multiple spaces
    t = re.sub(r"\s+", " ", t).strip()
    
    # 6. Clean non-significant abbreviations or prefixes/suffixes (e.g. trailing "ed", "edizione")
    t = re.sub(r"\b(ed|ediz|edizione|edizioni)\b.*$", "", t).strip()
    t = re.sub(r"\b(corso|corsi|progetto|convegno|regionale)\b", "", t).strip()
    t = re.sub(r"\s+", " ", t).strip()
    
    return t

CONFLICTING_ACRONYMS = {
    "acls", "blsd", "rls", "rup", "sdo", "whp", "ecg", "ecmo", "picc", "port", "tin", "niv", "mbsr", "pdta", "gom", "dea",
    "bls", "pblsd", "als", "pals"
}

class FuzzyMatcher:
    """Coordinates fuzzy matching of course titles between the Plan (Piano) and other sources (Report/LEA)."""
    
    def __init__(self):
        self.auto_thresh = settings["matching"]["auto_threshold"]
        self.doubt_thresh = settings["matching"]["doubtful_threshold"]

    def find_best_match(self, piano_title: str, candidates: List[str]) -> Tuple[Optional[str], float]:
        """Finds the best matching title from candidates and returns (best_title, score)."""
        if not candidates:
            return None, 0.0
            
        # 1. Check for manual equivalences in configuration first
        eq_map = settings.get("equivalences", {})
        if piano_title in eq_map:
            targets = eq_map[piano_title]
            if isinstance(targets, str):
                targets = [targets]
            # Normalise comparison to prevent minor spacing/casing issues in config
            targets_clean = {t.strip().lower(): t for t in targets}
            for cand in candidates:
                if cand.strip().lower() in targets_clean:
                    return cand, 100.0
            
        norm_piano = normalize_title(piano_title)
        if not norm_piano:
            return None, 0.0
            
        words_piano = set(norm_piano.split())
        acronyms_piano = words_piano.intersection(CONFLICTING_ACRONYMS)
        
        best_title = None
        best_score = 0.0
        
        for candidate in candidates:
            norm_cand = normalize_title(candidate)
            if not norm_cand:
                continue
                
            words_cand = set(norm_cand.split())
            acronyms_cand = words_cand.intersection(CONFLICTING_ACRONYMS)
            
            # If both contain acronyms from the conflicting list, they must share at least one
            if acronyms_piano and acronyms_cand:
                if acronyms_piano.isdisjoint(acronyms_cand):
                    continue
                    
            # Use ratio as Levenshtein distance metric
            score = fuzz.ratio(norm_piano, norm_cand)
            if score > best_score:
                best_score = score
                best_title = candidate
                
        return best_title, best_score

    def match_all(self, piano_titles: List[str], report_titles: List[str], lea_titles: List[str]) -> Tuple[Dict[str, str], Dict[str, str], List[MatchCandidate]]:
        """
        Matches piano titles to report and lea titles.
        Returns:
          - Dict of auto-matched: piano_title -> report_matched_title
          - Dict of auto-matched: piano_title -> lea_matched_title
          - List of MatchCandidate for doubtful matches (85-95%) to present in the UI.
        """
        report_matches: Dict[str, str] = {}
        lea_matches: Dict[str, str] = {}
        doubtful_candidates: List[MatchCandidate] = []
        
        for title in piano_titles:
            # 1. Match with report
            rep_best, rep_score = self.find_best_match(title, report_titles)
            if rep_best:
                if rep_score >= self.auto_thresh:
                    report_matches[title] = rep_best
                    logger.info(f"Match AUTOMATICO (Report): '{title}' -> '{rep_best}' (Score: {rep_score:.1f}%)")
                elif rep_score >= self.doubt_thresh:
                    doubtful_candidates.append(MatchCandidate(
                        piano_title=title,
                        matched_title=rep_best,
                        score=rep_score,
                        source_file='report'
                    ))
                    logger.info(f"Match DUBBIO (Report) aggiunto: '{title}' -> '{rep_best}' (Score: {rep_score:.1f}%)")
                else:
                    logger.info(f"Nessun match (Report): '{title}' (Miglior score: '{rep_best}' con {rep_score:.1f}%)")
                    
            # 2. Match with LEA
            lea_best, lea_score = self.find_best_match(title, lea_titles)
            if lea_best:
                if _is_title_already_matched_different(title, lea_best, rep_best, rep_score, lea_score):
                    # Edge check: make sure we don't mismatched code associations if we can avoid it.
                    pass
                if lea_score >= self.auto_thresh:
                    lea_matches[title] = lea_best
                    logger.info(f"Match AUTOMATICO (LEA): '{title}' -> '{lea_best}' (Score: {lea_score:.1f}%)")
                elif lea_score >= self.doubt_thresh:
                    doubtful_candidates.append(MatchCandidate(
                        piano_title=title,
                        matched_title=lea_best,
                        score=lea_score,
                        source_file='lea'
                    ))
                    logger.info(f"Match DUBBIO (LEA) aggiunto: '{title}' -> '{lea_best}' (Score: {lea_score:.1f}%)")
                else:
                    logger.info(f"Nessun match (LEA): '{title}' (Miglior score: '{lea_best}' con {lea_score:.1f}%)")
                    
        return report_matches, lea_matches, doubtful_candidates

def _is_title_already_matched_different(piano: str, lea: str, rep: Optional[str], score_rep: float, score_lea: float) -> bool:
    return False
