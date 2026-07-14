from typing import Dict, Any, List, Optional
from models.course import Course
from config.settings import settings
from utils.logger import logger

class BusinessCalculator:
    """Calculates all report fields (editions, hours, participants, expenses) based on matching results."""
    
    def __init__(self):
        self.extra_costs_config = settings.get("additional_costs", [])

    def calculate_accreditation_cost(self, credits_ecm: float) -> Optional[float]:
        """
        Calculates accreditation cost based on ECM credits:
        - credits < 10 -> 100 EUR
        - credits >= 10 -> 10 * credits EUR
        - If credits are not available / 0.0 -> returns None (empty cell)
        """
        if credits_ecm is None or credits_ecm <= 0:
            return None
        
        if credits_ecm < 10:
            return 100.0
        else:
            return 10.0 * credits_ecm

    def get_additional_costs(self, title: str, num_participants: int) -> float:
        """
        Checks config patterns to apply any additional fixed/per-participant costs.
        Example: ACLS courses have manual (50 EUR) and secretariat (20 EUR) costs per participant.
        """
        total_additional = 0.0
        for rule in self.extra_costs_config:
            pattern = rule.get("pattern", "")
            if not pattern:
                continue
                
            # Case-insensitive substring match
            if pattern.lower() in title.lower():
                # Apply per-participant costs
                per_part = rule.get("per_participant", {})
                per_part_sum = sum(float(v) for v in per_part.values())
                cost_part = num_participants * per_part_sum
                
                # Apply fixed costs
                fixed = rule.get("fixed", {})
                cost_fixed = sum(float(v) for v in fixed.values())
                
                total_additional += cost_part + cost_fixed
                
                logger.info(f"Applicato costo aggiuntivo per '{title}' (regola '{pattern}'): "
                            f"{num_participants} partecipanti x {per_part_sum:.2f}€ (per-part) + {cost_fixed:.2f}€ (fissi) = {cost_part + cost_fixed:.2f}€")
                break
                
        return total_additional

    def calculate_course_report(
        self, 
        piano_courses: List[Course], 
        report_data: Dict[str, Dict[str, Any]], 
        lea_data: Dict[str, Any],
        matched_reports: Dict[str, str],
        matched_leas: Dict[str, str],
        teaching_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
        docenze_data: Optional[Dict[str, Dict[str, float]]] = None
    ) -> List[Course]:
        """
        Merges piano, report, and lea data based on resolved match maps.
        Performs all calculations and returns the list of fully populated Course objects.
        Supports manual teaching cost overrides passed from the UI and external docenze spreadsheet.
        """
        logger.info("Avvio calcolo dei campi del report per ciascun corso...")
        
        populated_courses: List[Course] = []
        teaching_overrides = teaching_overrides or {}
        
        for p_course in piano_courses:
            title = p_course.titolo
            
            # Retrieve match names
            rep_match_title = matched_reports.get(title)
            lea_match_title = matched_leas.get(title)
            
            # 1. Gather report details
            edizioni_concluse = 0
            crediti_ecm = 0.0
            ore_svolte = 0.0
            costo_docenti_excel = 0.0
            docenze_source = "Excel"
            
            if rep_match_title and rep_match_title in report_data:
                rep_info = report_data[rep_match_title]
                edizioni_concluse = rep_info.get("edizioni_concluse", 0)
                crediti_ecm = rep_info.get("crediti_formativi", 0.0)
                ore_svolte = rep_info.get("ore_svolte", 0.0)
                costo_docenti_excel = rep_info.get("costo_totale_docenti", 0.0)
                
                # Check in riepilogo_docenze data by course code first
                if docenze_data:
                    corso_codici = rep_info.get("corso_codici", set())
                    found_in_docenze = False
                    docenze_cost_sum = 0.0
                    for code in corso_codici:
                        if code in docenze_data.get("by_code", {}):
                            docenze_cost_sum += docenze_data["by_code"][code]
                            found_in_docenze = True
                    
                    if found_in_docenze:
                        costo_docenti_excel = docenze_cost_sum
                        docenze_source = "Riepilogo Docenze"
            else:
                logger.info(f"Nessun dato report associato a '{title}'. Valori impostati a 0.")
                
            # If not found by course code or not matched to report, try matching by clean title in docenze_data
            if docenze_data and docenze_source != "Riepilogo Docenze":
                from modules.matcher import normalize_title
                norm_title = normalize_title(title)
                if norm_title in docenze_data.get("by_title", {}):
                    costo_docenti_excel = docenze_data["by_title"][norm_title]
                    docenze_source = "Riepilogo Docenze"
                
            # 2. Gather LEA participants count
            num_participants = 0
            partecipanti_effettivi = 0
            if lea_match_title and lea_match_title in lea_data:
                lea_vals = lea_data[lea_match_title]
                if isinstance(lea_vals, dict):
                    partecipanti_effettivi = lea_vals.get("effettivi", 0)
                    num_participants = lea_vals.get("crediti_ecm", 0)
                else:
                    partecipanti_effettivi = lea_vals
                    num_participants = lea_vals
            else:
                logger.info(f"Nessun dato discenti LEA associato a '{title}'. Partecipanti impostati a 0.")
                
            # 3. Determine teaching cost (incorporating overrides)
            costo_docenti = costo_docenti_excel
            desc_docenza = ""
            
            if title in teaching_overrides:
                override = teaching_overrides[title]
                method = override.get("method", "excel")
                
                if method == "params":
                    n_docenti = override.get("n_docenti", 1)
                    ore_docenza = override.get("ore_docenza", 0.0)
                    tipo_orario = override.get("tipo_orario", "in servizio")
                    # Standard rates: 5.12 EUR/h for in-service, 25.82 EUR/h for out-of-service
                    rate = 5.12 if tipo_orario == "in servizio" else 25.82
                    costo_docenti = n_docenti * ore_docenza * rate
                    desc_docenza = f"Docenza (manuale): {n_docenti} doc. x {ore_docenza} ore @ {rate:.2f}€/h = {costo_docenti:.2f} €"
                elif method == "direct":
                    costo_docenti = override.get("costo_diretto", 0.0)
                    desc_docenza = f"Docenza (forfettaria): {costo_docenti:.2f} €"
                else:  # 'excel'
                    costo_docenti = costo_docenti_excel
                    if costo_docenti > 0:
                        desc_docenza = f"Docenza ({docenze_source}): {costo_docenti:.2f} €"
            else:
                if costo_docenti > 0:
                    desc_docenza = f"Docenza ({docenze_source}): {costo_docenti:.2f} €"
            
            # 4. Calculate accreditation cost
            costo_acc = self.calculate_accreditation_cost(crediti_ecm)
            desc_acc = ""
            costo_acc_val = 0.0
            if costo_acc is not None and costo_acc > 0:
                costo_acc_val = costo_acc
                desc_acc = f"Accreditamento ECM: {costo_acc:.2f} € ({crediti_ecm:.1f} crediti)"
                
            # 5. Calculate additional costs
            costo_extra = self.get_additional_costs(title, num_participants)
            desc_extra = ""
            if costo_extra > 0:
                desc_extra = f"Costi aggiuntivi (ACLS): {costo_extra:.2f} € ({num_participants} part.)"
                
            # 6. Total spesa
            spesa_totale = costo_acc_val + costo_docenti + costo_extra
            
            # 7. Build detailed calculation trace
            calculation_parts = []
            if costo_acc_val > 0:
                calculation_parts.append(desc_acc)
            if costo_docenti > 0:
                calculation_parts.append(desc_docenza)
            if costo_extra > 0:
                calculation_parts.append(desc_extra)
                
            if calculation_parts:
                dettaglio_calcolo = " + ".join(calculation_parts) + f" = {spesa_totale:.2f} €"
            else:
                dettaglio_calcolo = "Spesa nulla"
            
            # Logging expense detail for this course
            log_detail = (f"Corsi: '{title}' -> "
                          f"Accreditamento: {f'{costo_acc:.2f}€' if costo_acc is not None else 'N/D'}, "
                          f"Docenti: {costo_docenti:.2f}€, "
                          f"Aggiuntivi: {costo_extra:.2f}€ | "
                          f"Spesa Totale: {spesa_totale:.2f}€")
            logger.info(log_detail)
            
            # Create populated Course model
            course_res = Course(
                n=p_course.n,
                ente_proponente=p_course.ente_proponente,
                area=p_course.area,
                ambito=p_course.ambito,
                titolo=p_course.titolo,
                fonte_finanziamento=p_course.fonte_finanziamento,
                edizioni_concluse=edizioni_concluse,
                edizioni_da_completare=p_course.edizioni_da_completare,
                crediti_formativi=crediti_ecm,
                ore_svolte=ore_svolte,
                partecipanti_effettivi=partecipanti_effettivi,
                numero_partecipanti=num_participants,
                spesa_sostenuta=round(spesa_totale, 2),
                dettaglio_calcolo=dettaglio_calcolo
            )
            populated_courses.append(course_res)
            
        logger.info(f"Calcolo dei report completato per tutti i {len(populated_courses)} corsi.")
        return populated_courses
