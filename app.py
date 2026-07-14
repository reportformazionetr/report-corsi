import streamlit as st
import pandas as pd
from datetime import datetime
import io
import os

# Set page configuration first
st.set_page_config(
    page_title="Report Formazione Annuale",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom premium styling via markdown
st.markdown("""
<style>
    .main-title {
        font-family: 'Outfit', 'Inter', sans-serif;
        font-size: 2.8rem;
        font-weight: 700;
        background: linear-gradient(135deg, #1F497D, #4F81BD);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 1.5rem;
    }
    .section-header {
        font-family: 'Inter', sans-serif;
        font-size: 1.5rem;
        font-weight: 600;
        color: #1F497D;
        border-bottom: 2px solid #D9D9D9;
        padding-bottom: 0.5rem;
        margin-top: 2rem;
        margin-bottom: 1rem;
    }
    .metric-card {
        background-color: #F2F5F8;
        border-left: 5px solid #1F497D;
        border-radius: 8px;
        padding: 1.2rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        text-align: center;
        transition: transform 0.2s;
    }
    .metric-card:hover {
        transform: translateY(-2px);
    }
    .metric-title {
        font-size: 0.9rem;
        color: #595959;
        font-weight: 500;
        text-transform: uppercase;
        margin-bottom: 0.5rem;
    }
    .metric-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #1F497D;
    }
    .log-box {
        font-family: 'Courier New', Courier, monospace;
        font-size: 0.85rem;
        background-color: #1E1E1E;
        color: #D4D4D4;
        padding: 1rem;
        border-radius: 6px;
        height: 300px;
        overflow-y: scroll;
        white-space: pre-wrap;
    }
</style>
""", unsafe_allow_html=True)

from models.course import Course, MatchCandidate
from utils.logger import logger, get_streamlit_logs, clear_streamlit_logs
from config.settings import settings
from modules.parser_piano import PianoParser
from modules.parser_report import ReportParser
from modules.parser_lea import LeaParser
from modules.matcher import FuzzyMatcher
from modules.calculator import BusinessCalculator
from modules.exporter import ReportExporter
from modules.parser_docenze import DocenzeParser

# Sidebar for file upload
st.sidebar.image("https://img.icons8.com/clouds/150/000000/analytics.png", width=120)
st.sidebar.markdown("<h2 style='color:#1F497D;'>Caricamento File</h2>", unsafe_allow_html=True)
st.sidebar.info("Carica i tre file Excel richiesti per elaborare il report annuale.")

piano_file = st.sidebar.file_uploader(
    "1. Piano Unico di Formazione (piano_unico_formazione.xlsx)",
    type=["xlsx"],
    key="piano_upload"
)

report_file = st.sidebar.file_uploader(
    "2. Report Corsi (report_corsi_2026.xlsx)",
    type=["xlsx"],
    key="report_upload"
)

lea_file = st.sidebar.file_uploader(
    "3. Dati LEA (lea_corsi.xlsx)",
    type=["xlsx"],
    key="lea_upload"
)

docenze_file = st.sidebar.file_uploader(
    "4. Riepilogo Docenze (riepilogo_docenze.xlsx - Opzionale)",
    type=["xlsx"],
    key="docenze_upload"
)

st.markdown("<h1 class='main-title'>📊 Generatore Report Annuale Formazione</h1>", unsafe_allow_html=True)
st.write("Questo strumento permette di incrociare i dati del Piano Formativo Regionale con i consuntivi dei Corsi (edizioni, crediti e docenze) ed i flussi LEA (partecipanti).")

# Initialize session states
if 'matching_completed' not in st.session_state:
    st.session_state.matching_completed = False
if 'doubtful_matches' not in st.session_state:
    st.session_state.doubtful_matches = []
if 'user_resolutions' not in st.session_state:
    st.session_state.user_resolutions = {}
if 'final_courses' not in st.session_state:
    st.session_state.final_courses = None
if 'active_files' not in st.session_state:
    st.session_state.active_files = {}
if 'teaching_overrides' not in st.session_state:
    st.session_state.teaching_overrides = {}
if 'final_report_map' not in st.session_state:
    st.session_state.final_report_map = {}
if 'final_lea_map' not in st.session_state:
    st.session_state.final_lea_map = {}
if 'docenze_data' not in st.session_state:
    st.session_state.docenze_data = None

# Check if files changed
current_files = {
    "piano": piano_file.name if piano_file else None,
    "report": report_file.name if report_file else None,
    "lea": lea_file.name if lea_file else None,
    "docenze": docenze_file.name if docenze_file else None
}

if current_files != st.session_state.active_files:
    # Reset processing state
    st.session_state.matching_completed = False
    st.session_state.doubtful_matches = []
    st.session_state.user_resolutions = {}
    st.session_state.final_courses = None
    st.session_state.teaching_overrides = {}
    st.session_state.final_report_map = {}
    st.session_state.final_lea_map = {}
    st.session_state.docenze_data = None
    st.session_state.active_files = current_files
    clear_streamlit_logs()

if not piano_file or not report_file or not lea_file:
    st.warning("⚠️ Per iniziare, carica tutti e tre i file Excel richiesti nella barra laterale sinistra.")
    
    # Showcase placeholders / guides
    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("1. Piano Formativo")
        st.write("Fonte primaria. Definisce l'elenco ufficiale dei corsi e delle aree di formazione.")
    with col2:
        st.subheader("2. Report Corsi ed Edizioni")
        st.write("Contiene i dettagli su edizioni concluse, crediti formativi, ore svolte e costi docenti.")
    with col3:
        st.subheader("3. Dati LEA")
        st.write("Fornisce il numero di iscritti ed effettivi partecipanti per ciascun corso.")
else:
    # Process files
    if not st.session_state.matching_completed:
        with st.spinner("Analisi e matching in corso..."):
            clear_streamlit_logs()
            logger.info("File caricati dall'utente. Inizio analisi dei contenuti.")
            
            # Save uploaded files temporarily to read sheets
            # In order for pandas to open them we can pass the uploaded file-like object directly
            try:
                # 1. Parse piano
                logger.info(f"Lettura file Piano: {piano_file.name}")
                piano_parser = PianoParser(piano_file)
                piano_courses = piano_parser.parse()
                
                # 2. Parse report
                logger.info(f"Lettura file Report: {report_file.name}")
                report_parser = ReportParser(report_file)
                report_data = report_parser.parse()
                
                # 3. Parse LEA
                logger.info(f"Lettura file LEA: {lea_file.name}")
                lea_parser = LeaParser(lea_file)
                lea_data = lea_parser.parse()
                
                # 4. Parse docenze (optional)
                docenze_data = None
                if docenze_file:
                    logger.info(f"Lettura file Riepilogo Docenze: {docenze_file.name}")
                    docenze_parser = DocenzeParser(docenze_file)
                    docenze_data = docenze_parser.parse()
                st.session_state.docenze_data = docenze_data
                
                if not piano_courses:
                    st.error("Errore: Impossibile caricare corsi dal Piano. Verifica la struttura del file.")
                    st.stop()
                    
                # Store parsed objects in session state for later
                st.session_state.piano_courses = piano_courses
                st.session_state.report_data = report_data
                st.session_state.lea_data = lea_data
                
                # Match titles
                matcher = FuzzyMatcher()
                piano_titles = [c.titolo for c in piano_courses]
                report_titles = list(report_data.keys())
                lea_titles = list(lea_data.keys())
                
                report_auto, lea_auto, doubtful = matcher.match_all(
                    piano_titles, report_titles, lea_titles
                )
                
                st.session_state.report_auto = report_auto
                st.session_state.lea_auto = lea_auto
                st.session_state.doubtful_matches = doubtful
                st.session_state.matching_completed = True
                
                # Default user resolutions: confirmed = True for all doubtful matches
                # Initialize UI resolutions
                for idx, dm in enumerate(doubtful):
                    st.session_state.user_resolutions[idx] = True # Default to accept
                    
            except Exception as e:
                logger.error(f"Errore durante l'elaborazione dei file: {e}", exc_info=True)
                st.error(f"Si è verificato un errore durante la lettura dei file Excel: {e}")
                st.stop()

    # If there are doubtful matches, ask the user to resolve them
    if st.session_state.matching_completed and st.session_state.doubtful_matches and st.session_state.final_courses is None:
        st.markdown("<div class='section-header'>⚠️ Risoluzione Corrispondenze Dubbie</div>", unsafe_allow_html=True)
        st.write(f"Sono state individuate **{len(st.session_state.doubtful_matches)}** corrispondenze con punteggio di similarità compreso tra 85% e 95%. Conferma o rifiuta ciascun match:")
        
        # Grid display for resolution
        for idx, dm in enumerate(st.session_state.doubtful_matches):
            col_piano, col_source, col_match, col_score, col_action = st.columns([3, 1, 3, 1, 2])
            with col_piano:
                st.markdown(f"**Piano:**  \n`{dm.piano_title}`")
            with col_source:
                st.markdown(f"**File:**  \n*{dm.source_file.upper()}*")
            with col_match:
                st.markdown(f"**Match trovato:**  \n`{dm.matched_title}`")
            with col_score:
                color = "green" if dm.score >= 90 else "orange"
                st.markdown(f"**Score:**  \n<span style='color:{color}; font-weight:bold;'>{dm.score:.1f}%</span>", unsafe_allow_html=True)
            with col_action:
                choice = st.radio(
                    f"Azione per match {idx}",
                    options=["Conferma", "Rifiuta"],
                    index=0,
                    key=f"dm_radio_{idx}",
                    horizontal=True,
                    label_visibility="collapsed"
                )
                st.session_state.user_resolutions[idx] = (choice == "Conferma")
            st.markdown("<hr style='margin: 0.5rem 0; border: 0; border-top: 1px solid #eee;' />", unsafe_allow_html=True)
            
        if st.button("Conferma Selezionati e Genera Report", type="primary"):
            # Build the finalized matching maps
            final_report_map = st.session_state.report_auto.copy()
            final_lea_map = st.session_state.lea_auto.copy()
            
            # Apply user resolutions
            for idx, dm in enumerate(st.session_state.doubtful_matches):
                confirmed = st.session_state.user_resolutions[idx]
                logger.info(f"Risoluzione utente per '{dm.piano_title}' -> '{dm.matched_title}' ({dm.source_file}): "
                            f"{'CONFERMATO' if confirmed else 'RIFIUTATO'}")
                if confirmed:
                    if dm.source_file == 'report':
                        final_report_map[dm.piano_title] = dm.matched_title
                    else:
                        final_lea_map[dm.piano_title] = dm.matched_title
                        
            st.session_state.final_report_map = final_report_map
            st.session_state.final_lea_map = final_lea_map
            
            # Execute calculations
            calculator = BusinessCalculator()
            final_courses = calculator.calculate_course_report(
                st.session_state.piano_courses,
                st.session_state.report_data,
                st.session_state.lea_data,
                final_report_map,
                final_lea_map,
                st.session_state.teaching_overrides,
                st.session_state.docenze_data
            )
            st.session_state.final_courses = final_courses
            st.rerun()

    # If matching is completed and there are NO doubtful matches, or they have already been resolved
    elif st.session_state.matching_completed and (not st.session_state.doubtful_matches or st.session_state.final_courses is not None):
        
        # If final_courses is not calculated (because there were no doubtful matches to resolve)
        if st.session_state.final_courses is None:
            final_report_map = st.session_state.report_auto.copy()
            final_lea_map = st.session_state.lea_auto.copy()
            st.session_state.final_report_map = final_report_map
            st.session_state.final_lea_map = final_lea_map
            
            calculator = BusinessCalculator()
            st.session_state.final_courses = calculator.calculate_course_report(
                st.session_state.piano_courses,
                st.session_state.report_data,
                st.session_state.lea_data,
                final_report_map,
                final_lea_map,
                st.session_state.teaching_overrides,
                st.session_state.docenze_data
            )
            
        final_courses = st.session_state.final_courses
        
        # Display Summary Metrics
        st.markdown("<div class='section-header'>📊 Indicatori Sintetici</div>", unsafe_allow_html=True)
        
        # Calculations for metrics
        total_corsi = len(final_courses)
        total_edizioni = sum(c.edizioni_concluse for c in final_courses)
        total_partecipanti = sum(c.numero_partecipanti for c in final_courses)
        total_spesa = sum(c.spesa_sostenuta for c in final_courses)
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f"""
            <div class='metric-card'>
                <div class='metric-title'>Totale Corsi a Piano</div>
                <div class='metric-value'>{total_corsi}</div>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            st.markdown(f"""
            <div class='metric-card'>
                <div class='metric-title'>Edizioni Concluse</div>
                <div class='metric-value'>{total_edizioni}</div>
            </div>
            """, unsafe_allow_html=True)
        with col3:
            st.markdown(f"""
            <div class='metric-card'>
                <div class='metric-title'>Partecipanti Effettivi ECM</div>
                <div class='metric-value'>{total_partecipanti}</div>
            </div>
            """, unsafe_allow_html=True)
        with col4:
            st.markdown(f"""
            <div class='metric-card'>
                <div class='metric-title'>Spesa Totale Sostenuta</div>
                <div class='metric-value'>{total_spesa:,.2f} €</div>
            </div>
            """, unsafe_allow_html=True)
            
        # Overrides section
        st.markdown("<div class='section-header'>⚙️ Personalizzazione Costi Docenza per Corso</div>", unsafe_allow_html=True)
        st.write("Puoi forzare o ricalcolare manualmente le spese docenti per ciascun corso dell'AO Terni. Seleziona il corso e scegli la modalità di calcolo:")
        
        col_select, col_config = st.columns([2, 3])
        
        with col_select:
            ao_terni_titles = [c.titolo for c in final_courses]
            selected_title = st.selectbox("Seleziona il Corso da personalizzare:", options=ao_terni_titles)
            
            # Find default Excel cost if matched
            rep_match = st.session_state.final_report_map.get(selected_title)
            default_cost = 0.0
            if rep_match and rep_match in st.session_state.report_data:
                default_cost = st.session_state.report_data[rep_match].get("costo_totale_docenti", 0.0)
            
            st.info(f"Costo docenza calcolato da file Excel: **{default_cost:.2f} €**")
            
        with col_config:
            curr_override = st.session_state.teaching_overrides.get(selected_title, {"method": "excel"})
            curr_method = curr_override.get("method", "excel")
            
            method_opts = ["Excel (Calcolato automaticamente)", "Inserimento parametri manuali", "Costo totale forfettario"]
            method_idx = 0
            if curr_method == "params":
                method_idx = 1
            elif curr_method == "direct":
                method_idx = 2
                
            choice_method = st.radio(
                "Metodo di imputazione costi docenza:",
                options=method_opts,
                index=method_idx,
                key=f"method_radio_{selected_title}"
            )
            
            method_key = "excel"
            n_docenti = 1
            ore_docenza = 0.0
            tipo_orario = "in servizio"
            costo_diretto = 0.0
            
            if choice_method == "Inserimento parametri manuali":
                method_key = "params"
                col_n, col_h, col_t = st.columns(3)
                with col_n:
                    n_docenti = st.number_input("N. Docenti", min_value=1, value=curr_override.get("n_docenti", 1), step=1, key=f"n_doc_{selected_title}")
                with col_h:
                    ore_docenza = st.number_input("Ore Docenza (cad.)", min_value=0.0, value=curr_override.get("ore_docenza", 0.0), step=0.5, key=f"ore_doc_{selected_title}")
                with col_t:
                    tipo_orario = st.selectbox("Tipo Orario", options=["in servizio", "fuori servizio"], 
                                               index=0 if curr_override.get("tipo_orario", "in servizio") == "in servizio" else 1,
                                               key=f"tipo_or_{selected_title}")
            elif choice_method == "Costo totale forfettario":
                method_key = "direct"
                costo_diretto = st.number_input("Costo Totale Docenza (€)", min_value=0.0, value=curr_override.get("costo_diretto", 0.0), step=10.0, key=f"cost_dir_{selected_title}")
                
            # Apply button
            new_override = {"method": method_key}
            if method_key == "params":
                new_override.update({"n_docenti": n_docenti, "ore_docenza": ore_docenza, "tipo_orario": tipo_orario})
            elif method_key == "direct":
                new_override.update({"costo_diretto": costo_diretto})
                
            if st.button("Applica e Ricalcola Costi Docenza"):
                st.session_state.teaching_overrides[selected_title] = new_override
                st.session_state.final_courses = None # Force recalculation
                st.rerun()

        # Display data table
        st.markdown("<div class='section-header'>📝 Tabella Report Annuale</div>", unsafe_allow_html=True)
        df_out = ReportExporter.to_dataframe(final_courses)
        
        # Style table view
        st.dataframe(
            df_out,
            use_container_width=True,
            hide_index=True,
            column_config={
                "N.": st.column_config.NumberColumn("N.", format="%d"),
                "Spesa sostenuta": st.column_config.NumberColumn("Spesa sostenuta (€)", format="%.2f"),
                "Crediti formativi": st.column_config.NumberColumn("Crediti formativi", format="%.1f"),
                "Ore svolte": st.column_config.NumberColumn("Ore svolte", format="%.1f"),
                "Partecipanti effettivi": st.column_config.NumberColumn("Partecipanti effettivi", format="%d"),
                "Edizioni concluse": st.column_config.NumberColumn("Edizioni concluse", format="%d"),
                "Numero partecipanti ECM": st.column_config.NumberColumn("Numero partecipanti ECM", format="%d"),
                "Dettaglio Calcolo": st.column_config.TextColumn("Dettaglio Calcolo")
            }
        )
        
        # Download Excel
        st.markdown("### 📥 Scarica Report")
        
        # Write styled output in bytes buffer
        buffer = io.BytesIO()
        ReportExporter.export(final_courses, buffer)
        excel_data = buffer.getvalue()
        
        filename = f"report_formazione_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
        
        st.download_button(
            label="Scarica il file Excel formattato",
            data=excel_data,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )

    # Logging panel at the bottom (collapsible expander)
    st.markdown("<div class='section-header'>📋 Registro delle Operazioni</div>", unsafe_allow_html=True)
    with st.expander("Mostra Registro Log di Elaborazione", expanded=True):
        logs = get_streamlit_logs()
        if logs:
            log_text = "\n".join(logs)
            st.markdown(f"<div class='log-box'>{log_text}</div>", unsafe_allow_html=True)
        else:
            st.info("Nessuna operazione registrata nel log.")
