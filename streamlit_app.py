import streamlit as st
import pandas as pd
import numpy as np
import os
import re

st.set_page_config(page_title="CBAM Calculator PRO", layout="wide")

# --- FUNZIONI DI PULIZIA ---
def clean_val(val):
    if pd.isna(val) or str(val).strip() in ["", "#VALUE!", "nan", "NaN"]:
        return np.nan
    if isinstance(val, str):
        val = val.strip().replace(",", ".")
        val = re.sub(r'[^\d.-]', '', val) # Tiene solo numeri, punti e meno
        try: return float(val)
        except: return np.nan
    return float(val)

@st.cache_data
def load_data():
    # Cerca i file nella cartella corrente in modo flessibile
    files = os.listdir(".")
    f_bench = next((f for f in files if "benchmarks" in f.lower() and f.endswith(".csv")), None)
    f_defaults = next((f for f in files if "defaults" in f.lower() and f.endswith(".csv")), None)

    if not f_bench or not f_defaults:
        st.error(f"❌ File non trovati! Assicurati di avere i file CSV nella cartella. File rilevati: {files}")
        st.stop()

    # Caricamento Benchmarks (Semicolon)
    df_b = pd.read_csv(f_bench, sep=";", engine='python', on_bad_lines='skip')
    df_b.columns = [c.replace("\n", " ").strip() for c in df_b.columns]
    
    # Caricamento Defaults (Comma)
    df_d = pd.read_csv(f_defaults, sep=",", engine='python', on_bad_lines='skip')
    df_d.columns = [c.strip() for c in df_d.columns]

    # Pulizia HS Code (ffill per celle unite di Excel)
    col_hs_b = next(c for c in df_b.columns if "CN code" in c)
    df_b[col_hs_b] = df_b[col_hs_b].ffill().astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    
    col_hs_d = next(c for c in df_d.columns if "CN Code" in c)
    df_d[col_hs_d] = df_d[col_hs_d].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

    return df_b, df_d, col_hs_b, col_hs_d

# --- CARICAMENTO ---
try:
    bench, defaults, HS_B, HS_D = load_data()
except Exception as e:
    st.error(f"Errore durante l'inizializzazione: {e}")
    st.stop()

st.title("🛡️ CBAM Professional Calculator")

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Configurazione")
    anno = st.selectbox("Anno di riferimento", [2026, 2027, 2028, 2029, 2030])
    periodo_key = "(1)" if anno <= 2027 else "(2)"
    
    paese = st.selectbox("Paese di Origine", sorted(defaults['Country'].unique()))
    codice_hs = st.selectbox("Codice HS Prodotto", sorted(bench[HS_B].unique()))
    
    volume = st.number_input("Volume (Tonnellate)", min_value=0.0, value=1.0, step=0.1)
    reali = st.number_input("Emissioni Reali (tCO2e/t)", min_value=0.0, format="%.4f", help="Lascia 0 per usare i Default")

    st.header("2. Parametri Economici")
    prezzo_ets = st.number_input("Prezzo ETS (€/tCO2)", value=80.0)
    fa_default = 97.5 if anno <= 2026 else (95.0 if anno == 2027 else 92.5)
    free_allowance = st.slider("Free Allowance (%)", 0.0, 100.0, fa_default)

# --- LOGICA CORE ---
usare_reali = reali > 0
pfx = "Column A" if usare_reali else "Column B"

# Identificazione colonne BMg e Indicator
col_bmg = next(c for c in bench.columns if pfx in c and "BMg" in c)
col_ind = next(c for c in bench.columns if pfx in c and "indicator" in c)

# Filtro HS e Periodo (1) o (2)
df_hs = bench[bench[HS_B] == codice_hs].copy()

def matches_period(val):
    v = str(val)
    if periodo_key in v: return True
    if "(1)" not in v and "(2)" not in v: return True
    return False

df_valido = df_hs[df_hs[col_ind].apply(matches_period)]

# Gestione Production Route (C, D, E...)
benchmark_base = 0.0
if len(df_valido) > 1:
    st.info(f"Rotte di produzione multiple rilevate per {codice_hs}")
    mappa = {}
    for _, r in df_valido.iterrows():
        # Label per selectbox (es: (C)(1))
        label = str(r[col_ind]) if pd.notna(r[col_ind]) else "Default"
        mappa[label] = clean_val(r[col_bmg])
    
    rotta_scelta = st.selectbox("Seleziona Rotta (Production Route):", list(mappa.keys()))
    benchmark_base = mappa[rotta_scelta]
else:
    benchmark_base = clean_val(

