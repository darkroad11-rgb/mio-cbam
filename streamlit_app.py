import streamlit as st
import pandas as pd
import numpy as np
import os
import re

st.set_page_config(page_title="CBAM Calculator Pro", layout="wide")

def clean_numeric(val):
    if pd.isna(val) or val == "" or str(val).strip() == "#VALUE!":
        return np.nan
    if isinstance(val, str):
        val = val.strip().replace(",", ".")
        try:
            return float(val)
        except ValueError:
            return np.nan
    return float(val)

@st.cache_data
def load_data():
    file_bench = "benchmarks.csv"
    file_defaults = "defaults.csv"

    if not os.path.exists(file_bench) or not os.path.exists(file_defaults):
        st.error(f"⚠️ File non trovati! Assicurati che nella cartella ci siano: '{file_bench}' e '{file_defaults}'")
        st.stop()

    # --- CARICAMENTO BENCHMARKS ---
    bench = pd.read_csv(file_bench, sep=";")
    
    # Pulizia Nomi Colonne: rimuoviamo a capo, virgolette e spazi extra
    bench.columns = [c.replace("\n", " ").replace('"', '').strip() for c in bench.columns]
    
    # Identificazione dinamica delle colonne per evitare KeyError
    col_hs = next((c for c in bench.columns if "CN code" in c), None)
    col_desc = next((c for c in bench.columns if "Description" in c), None)
    cols_bmg = [c for c in bench.columns if "BMg" in c]
    cols_ind = [c for c in bench.columns if "indicator" in c]

    if not col_hs or not cols_bmg:
        st.error(f"Errore: Colonne non riconosciute nel file Benchmarks. Colonne trovate: {list(bench.columns)}")
        st.stop()

    bench[col_hs] = bench[col_hs].ffill().astype(str).str.replace(r'\.0$', '', regex=True)
    if col_desc: bench[col_desc] = bench[col_desc].ffill()
    
    for col in cols_bmg:
        bench[col] = bench[col].apply(clean_numeric)

    # --- CARICAMENTO DEFAULTS ---
    defaults = pd.read_csv(file_defaults)
    defaults.columns = [c.strip() for c in defaults.columns]
    
    col_hs_def = next((c for c in defaults.columns if "CN Code" in c), None)
    if col_hs_def:
        defaults[col_hs_def] = defaults[col_hs_def].astype(str).str.replace(r'\.0$', '', regex=True)
    
    # Pulizia colonne numeriche dei default
    for col in defaults.columns:
        if "Default Value" in col:
            defaults[col] = defaults[col].apply(clean_numeric)
        
    return bench, defaults, col_hs, cols_bmg, cols_ind

# Carichiamo i dati e otteniamo i nomi corretti delle colonne
bench_df, def_df, COL_HS, COLS_BMG, COLS_IND = load_data()

# --- INTERFACCIA ---
st.title("🛡️ Calcolatore Emissioni CBAM")

with st.sidebar:
    st.header("Configurazione")
    anno = st.selectbox("Anno di riferimento", [2026, 2027, 2028, 2029, 2030])
    periodo_key = "(1)" if anno <= 2027 else "(2)"
    
    paese = st.selectbox("Paese di Origine", sorted(def_df['Country'].unique()))
    hs_code = st.selectbox("Codice HS", sorted(bench_df[COL_HS].unique()))
    
    volume = st.number_input("Volume Importato (Ton)", min_value=0.0, value=1.0)
    emissioni_reali = st.number_input("Emissioni Reali Dirette (tCO2e/t)", min_value=0.0, value=0.0, format="%.4f")

# --- LOGICA CORE ---
usare_reali = emissioni_reali > 0

# Selezioniamo Colonna A (Reali) o B (Default) basandoci sulla posizione o sul nome
# Di solito Col A è la prima BMg trovata, Col B è la seconda.
c_bench = COLS_BMG[0] if usare_reali else COLS_BMG[1]
c_route = COLS_IND[0] if usare_reali else COLS_IND[1]

# 1. Calcolo Emissioni Applicate
valore_emissioni = emissioni_reali
if not usare_reali:
    col_anno_def = next((c for c in def_df.columns if str(min(anno, 2028)) in c), def_df.columns[-1])
    
    mask = (def_df['Product CN Code'] == hs_code) & (def_df['Country'] == paese)
    row_def = def_df[mask]
    
    val_def = row_def[col_anno_def].iloc[0] if not row_def.empty else np.nan
    
    # Fallback su 'Other Countries'
    if pd.isna(val_def):
        other_mask = (def_df['Product CN Code'] == hs_code) & (def_df['Country'].str.contains("Other", case=False, na=False))
        row_other = def_df[other_mask]
        val_def = row_other[col_anno_def].iloc[0] if not row_other.empty else 0.0
    valore_emissioni = val_def

# 2. Selezione Benchmark e Rotta di Produzione
opzioni = bench_df[bench_df[COL_HS] == hs_code]

# Filtro per (1) o (2)
def filter_p(val):
    val = str(val)
    if periodo_key in val: return True
    if "(1)" not in val and "(2)" not in val: return True
    return False

opzioni_valide = opzioni[opzioni[c_route].apply(filter_p)]

if len(opzioni_valide) > 1:
    st.warning("Seleziona la Rotta di Produzione (Production Route):")
    nomi_rotte = {f"{r[c_route]} - Valore: {r[c_bench]}": r[c_bench] for _, r in opzioni_valide.iterrows()}
    scelta = st.selectbox("Rotta", list(nomi_rotte.keys()))
    valore_benchmark = nomi_rotte[scelta]
else:
    valore_benchmark = opzioni_valide[c_bench].iloc[0] if not opzioni_valide.empty else 0.0

# --- DISPLAY RISULTATI ---
st.divider()
col1, col2, col3 = st.columns(3)

# Esempio Calcolo Economico
fa_perc = 97.5 if anno <= 2026 else (95.0 if anno == 2027 else 92.5)
prezzo_ets = 80.0
quota_pagabile = max(0, valore_emissioni - (valore_benchmark * fa_perc / 100))
costo_totale = quota_pagabile * volume * prezzo_ets

col1.metric("Emissioni Applicate", f"{valore_emissioni:.4f} tCO2/t")
col2.metric("Benchmark Applicato", f"{valore_benchmark:.4f}")
col3.metric("Costo Stimato Certificati", f"€ {costo_totale:,.2f}")

