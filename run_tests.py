import unittest
import os
import pandas as pd
from models.course import Course
from modules.matcher import normalize_title, FuzzyMatcher
from modules.calculator import BusinessCalculator
from modules.parser_piano import PianoParser
from modules.parser_report import ReportParser
from modules.parser_lea import LeaParser
from modules.parser_docenze import DocenzeParser

class TestReportSystem(unittest.TestCase):
    
    def test_normalization(self):
        """Test Title Normalization logic and cleanup regex rules."""
        self.assertEqual(normalize_title("Cardiologia avanzata - ed"), "cardiologia avanzata")
        self.assertEqual(normalize_title("BLSD  (Basic Life Support Defibrillation)"), "blsd")
        self.assertEqual(normalize_title("Gestione dell'Ictus ischemico"), "gestione dell ictus ischemico")
        self.assertEqual(normalize_title("Convegno regionale “Sistema Umbria”"), "sistema umbria")
        self.assertEqual(normalize_title("  Spazi   multipli  "), "spazi multipli")
        self.assertEqual(normalize_title("àèìòùé"), "aeioue")

    def test_accreditation_costs(self):
        """Test ECM Accreditation calculation tiers."""
        calc = BusinessCalculator()
        # Credits < 10 -> 100 EUR
        self.assertEqual(calc.calculate_accreditation_cost(5), 100.0)
        self.assertEqual(calc.calculate_accreditation_cost(9.5), 100.0)
        
        # Credits >= 10 -> 10 * credits EUR
        self.assertEqual(calc.calculate_accreditation_cost(10), 100.0)
        self.assertEqual(calc.calculate_accreditation_cost(15), 150.0)
        self.assertEqual(calc.calculate_accreditation_cost(22.5), 225.0)
        
        # No credits -> None
        self.assertIsNone(calc.calculate_accreditation_cost(0.0))
        self.assertIsNone(calc.calculate_accreditation_cost(-2.0))

    def test_acls_additional_costs(self):
        """Test ACLS course specific per-participant extra costs."""
        calc = BusinessCalculator()
        # Non-ACLS titles should have 0.0 additional costs
        self.assertEqual(calc.get_additional_costs("Corso Cardiologia", 10), 0.0)
        
        # ACLS titles should calculate 55 + 20 = 75 EUR per participant
        # 10 participants * 75 = 750.0 EUR
        self.assertEqual(calc.get_additional_costs("Esecutore ACLS (Advanced Cardiac Life Support)", 10), 750.0)
        self.assertEqual(calc.get_additional_costs("ACLS Maggio", 5), 375.0)

    def test_excel_parsers_smoke(self):
        """Smoke test: execute parsers on actual sample Excel files in example_excel/."""
        folder = r"c:\Users\Andrea\Desktop\progetto_report_corsi\example_excel"
        piano_path = os.path.join(folder, "piano_unico_formazione.xlsx")
        report_path = os.path.join(folder, "report_corsi_ 2026.xlsx")
        lea_path = os.path.join(folder, "lea_corsi.xlsx")
        
        self.assertTrue(os.path.exists(piano_path), f"File non trovato: {piano_path}")
        self.assertTrue(os.path.exists(report_path), f"File non trovato: {report_path}")
        self.assertTrue(os.path.exists(lea_path), f"File non trovato: {lea_path}")
        
        # Parse Piano
        p_parser = PianoParser(piano_path)
        courses = p_parser.parse()
        self.assertGreater(len(courses), 0, "Dovrebbe caricare almeno un corso dal Piano.")
        
        # Verify filtering: all courses must belong to AO Terni
        for c in courses:
            self.assertEqual(c.ente_proponente.strip().lower(), "ao terni")
        
        # Parse Report
        r_parser = ReportParser(report_path)
        rep_data = r_parser.parse()
        self.assertGreater(len(rep_data), 0, "Dovrebbe caricare almeno un corso dal Report.")
        
        # Parse LEA
        l_parser = LeaParser(lea_path)
        lea_data = l_parser.parse()
        self.assertGreater(len(lea_data), 0, "Dovrebbe caricare almeno un corso dal file LEA.")
        
        # Verify fuzzy matching auto-matches
        matcher = FuzzyMatcher()
        piano_titles = [c.titolo for c in courses]
        report_titles = list(rep_data.keys())
        lea_titles = list(lea_data.keys())
        
        report_auto, lea_auto, doubtful = matcher.match_all(
            piano_titles, report_titles, lea_titles
        )
        
        # Print matching summaries in logs
        print(f"\n--- Smoke Test Match Summary ---")
        print(f"Piano: {len(piano_titles)} corsi")
        print(f"Auto-matches (Report): {len(report_auto)}")
        print(f"Auto-matches (LEA): {len(lea_auto)}")
        print(f"Doubtful matches (needs confirmation): {len(doubtful)}")

    def test_docenze_parser_and_calculation(self):
        """Test DocenzeParser extraction and BusinessCalculator integration."""
        folder = r"c:\Users\Andrea\Desktop\progetto_report_corsi\example_excel"
        docenze_path = os.path.join(folder, "riepilogo_docenze.xlsx")
        self.assertTrue(os.path.exists(docenze_path), f"File non trovato: {docenze_path}")
        
        parser = DocenzeParser(docenze_path)
        data = parser.parse()
        
        self.assertIn("by_code", data)
        self.assertIn("by_title", data)
        self.assertGreater(len(data["by_code"]), 0)
        self.assertGreater(len(data["by_title"]), 0)
        
        # Verify a specific mapping: C8769 -> 2852.34831
        self.assertIn("C8769", data["by_code"])
        self.assertAlmostEqual(data["by_code"]["C8769"], 2852.34831, places=4)
        
        # Check title normalization map: 'esecutore acls aha'
        norm_title = normalize_title("Esecutore ACLS AHA")
        self.assertIn(norm_title, data["by_title"])
        self.assertAlmostEqual(data["by_title"][norm_title], 2852.34831, places=4)

    def test_acronym_conflicts(self):
        """Test that conflicting acronyms are NOT matched despite high shared word count."""
        matcher = FuzzyMatcher()
        
        # 1. Esecutore BLSD vs Esecutore ACLS should not match (should yield None, 0.0)
        best_title, score = matcher.find_best_match(
            "Esecutore BLSD (Basic Life Support Defibrillation)",
            ["Esecutore ACLS (Advanced Cardiac Life Support) (AHA)"]
        )
        self.assertIsNone(best_title)
        self.assertEqual(score, 0.0)
        
        # 2. Aggiornamento RLS vs Formazione per i RUP should not match
        best_title, score = matcher.find_best_match(
            "Aggiornamento RLS ai sensi del D.lgs. 81/08",
            ["Formazione per i RUP"]
        )
        self.assertIsNone(best_title)
        self.assertEqual(score, 0.0)
        
        # 3. Compatible acronyms (or same acronym) should match
        best_title, score = matcher.find_best_match(
            "Esecutore BLSD (Basic Life Support Defibrillation)",
            ["BLSD UNIVERSITA' NO ECM", "Esecutore ACLS"]
        )
        self.assertEqual(best_title, "BLSD UNIVERSITA' NO ECM")
        self.assertGreater(score, 0.0)

    def test_manual_equivalences(self):
        """Test that configured manual equivalences map perfectly with score 100.0."""
        matcher = FuzzyMatcher()
        
        # Test mapped equivalence (should return the exact equivalent title with 100.0 score)
        piano_title = "Formazione generale ai sensi del D.lgs. 81/08"
        target_lea = "CORSO SICUREZZA LAVORATORI “LA FORMAZIONE GENERALE DEI LAVORATORI” (ai sensi del D.lgs. 81/2008 s.m.i. e accordi attuativi)"
        best_title, score = matcher.find_best_match(piano_title, [target_lea, "Unrelated Course"])
        self.assertEqual(best_title, target_lea)
        self.assertEqual(score, 100.0)

if __name__ == "__main__":
    unittest.main()
