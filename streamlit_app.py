import streamlit as st
import pandas as pd
import numpy as np
import os
import re

st.set_page_config(page_title="CBAM Calculator Suite", layout="wide")

# --- FUNZIONI DI UTILITÀ ---
def pulisci_numero(val):
    if pd.isna(val) or str(val).strip() in ["", "#VALUE!", "nan"]:
        return np.nan
    if isinstance(val, str):
        val = val.strip().replace(",", ".")
        val = re.sub(r'[^\d.-]', '', val)
        try:
            return float(val)
        except:
            return np.nan
    return float(val)

@st.cache_data
def carica_database():
    # Nomi dei file basati sui tuoi caricamenti
    f_bench = "benchmarks final.csv"
    f_defaults = "cbam defaults.xlsx - cbam defaults.csv"

    if not os.path.exists(f_bench) or not os.path.exists(f_defaults):
        st.error("⚠️ File CSV non trovati nella cartella. Assicurati che i nomi siano corretti.")
        st.stop()

    # Lettura flessibile per evitare errori di parsing
    df_b = pd.read_csv(f_bench, sep=";", engine='python', on_bad_lines='skip')
    df_d = pd.read_csv(f_defaults, sep=",", engine='python', on_bad_lines='skip')

    # Pulizia nomi colonne (rimuove \n e spazi)
    df_b.columns = [c.replace("\n", " ").strip() for c in df_b.columns]
    df_d.columns = [c.strip() for c in df_d.columns]

    # Gestione codici HS e riempimento celle vuote (ffill)
    col_hs_b = [c for c in df_b.columns if "CN code" in c][0]
    df_b[col_hs_b] = df_b[col_hs_b].ffill().astype(str).str.replace(r'\.0$', '', regex=True)
    
    col_hs_d = [c for c in df_d.columns if "CN Code" in c][0]
    df_d[col_hs_d] = df_d[col_hs_d].astype(str).str.replace(r'\.0$', '', regex=True)

    # Pulizia valori numerici nel benchmark
    cols_bmg = [c for c in df_b.columns if "BMg" in c]
    for c in cols_bmg:
        df_b[c] = df_b[c].apply(pulisci_numero)

    # Pulizia valori numerici nei default
    cols_def = [c for c in df_d.columns if "Default Value" in c]
    for c in cols_def:
        df_d[c] = df_d[c].apply(pulisci_numero)

    return df_b, df_d, col_hs_b, col_hs_d

# --- CARICAMENTO DATI ---
try:
    bench, defaults, HS_B, HS_D = carica_database()
except Exception as e:
    st.error(f"Errore tecnico nel database: {e}")
    st.stop()

# --- INTERFACCIA UTENTE ---
st.title("🛡️ CBAM Calculator - Modulo Completo")

with st.sidebar:
    st.header("1. Input Spedizione")
    anno = st.selectbox("Anno di importazione", [2026, 2027, 2028, 2029, 2030])
    periodo_req = "(1)" if anno <= 2027 else "(2)"
    
    paese_input = st.selectbox("Paese di Origine", sorted(defaults['Country'].unique()))
    hs_input = st.selectbox("Codice HS", sorted(bench[HS_B].unique()))
    
    tonnellate = st.number_input("Volume (Tonnellate)", min_value=0.0, value=1.0, step=0.1)
    emissioni_reali = st.number_input("Emissioni Reali Dirette (tCO2e/t)", 
                                      help="Inserisci il dato reale se disponibile, altrimenti lascia 0 per usare i default",
                                      min_value=0.0, format="%.4f")
    
    st.header("2. Parametri Economici")
    prezzo_ets = st.number_input("Prezzo Certificato CBAM (€/tCO2)", value=75.0)
    # Calcolo Free Allowance standard decrescente
    fa_stima = 97.5 if anno <= 2026 else (95.0 if anno == 2027 else 92.5)
    free_allowance = st.slider("Free Allowance (%)", 0.0, 100.0, fa_stima)

# --- LOGICA DI CALCOLO ---
usare_reali = emissioni_reali > 0

# A. Selezione Colonne Benchmark
col_val = [c for c in bench.columns if ("Column A" if usare_reali else "Column B") in c and "BMg" in c][0]
col_ind = [c for c in bench.columns if ("Column A" if usare_reali else "Column B") in c and "indicator" in c][0]

# B. Filtro Benchmark per HS e Periodo (1)/(2)
mask_hs = (bench[HS_B] == hs_input)
righe_prodotto = bench[mask_hs].copy()

# Funzione per filtrare (1) o (2) nell'indicatore
def matches_period(val):
    v = str(val)
    if periodo_req in v: return True
    if "(1)" not in v and "(2)" not in v: return True
    return False

righe_filtrate = righe_prodotto[righe_prodotto[col_ind].apply(matches_period)]

# C. Scelta Rotta di Produzione (C, D, E...)
benchmark_applicato = 0.0
if len(righe_filtrate) > 1:
    st.info("ℹ️ Trovate più rotte di produzione. Seleziona quella corrispondente al tuo processo:")
    opzioni_rotte = {}
    for _, r in righe_filtrate.iterrows():
        label = str(r[col_ind]) if pd.notna(r[col_ind]) else "Default






