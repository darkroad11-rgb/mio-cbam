import streamlit as st
import pandas as pd
import numpy as np
import os
import re

st.set_page_config(page_title="CBAM Calculator", layout="wide")

# Funzione per pulire i numeri (gestisce virgole e valori d'errore Excel)
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
    # Nomi dei file (assicurati che siano corretti nella tua cartella)
    file_bench = "benchmarks.csv" 
    file_defaults = "defaults.csv"

    # Verifica se i file esistono per evitare l'errore che hai visto
    if not os.path.exists(file_bench) or not os.path.exists(file_defaults):
        st.error(f"⚠️ File non trovati! Assicurati di aver caricato '{file_bench}' e '{file_defaults}'")
        st.stop()

    # Caricamento Benchmarks
    bench = pd.read_csv(file_bench, sep=";")
    bench['CN code'] = bench['CN code'].ffill().astype(str).str.replace(r'\.0$', '', regex=True)
    bench['CN Description'] = bench['CN Description'].ffill()
    for col in ['Column A\nBMg [tCO2e/t]', 'Column B\nBMg [tCO2e/t]']:
        bench[col] = bench[col].apply(clean_numeric)

    # Caricamento Defaults
    defaults = pd.read_csv(file_defaults)
    defaults['Product CN Code'] = defaults['Product CN Code'].astype(str).str.replace(r'\.0$', '', regex=True)
    for col in ['2026 Default Value (Including mark-up)', '2027 Default Value (Including mark-up)', '2028 Default Value (Including mark-up)']:
        defaults[col] = defaults[col].apply(clean_numeric)
        
    return bench, defaults

# --- INTERFACCIA ---
st.title("🛡️ Calcolatore Emissioni CBAM")

bench_df, def_df = load_data()

with st.sidebar:
    st.header("Configurazione")
    anno = st.selectbox("Anno di riferimento", [2026, 2027, 2028, 2029, 2030])
    periodo = "(1)" if anno <= 2027 else "(2)"
    
    paese = st.selectbox("Paese di Origine", sorted(def_df['Country'].unique()))
    hs_code = st.selectbox("Codice HS", sorted(bench_df['CN code'].unique()))
    
    volume = st.number_input("Volume Importato (Ton)", min_value=0.0, value=1.0)
    emissioni_reali = st.number_input("Emissioni Reali Dirette (tCO2e/t) - (Lascia 0 se non le hai)", min_value=0.0, value=0.0, format="%.4f")

# --- LOGICA CORE ---

# 1. Emissioni Reali o Default
usare_reali = emissioni_reali > 0
col_bench = 'Column A\nBMg [tCO2e/t]' if usare_reali else 'Column B\nBMg [tCO2e/t]'
col_route = 'Column A\nProduction route indicator' if usare_reali else 'Column B\nProduction route indicator'

# 2. Ricerca Emissioni di Default (se emissioni_reali == 0)
valore_emissioni = emissioni_reali
if not usare_reali:
    col_anno_def = f"{min(anno, 2028)} Default Value (Including mark-up)"
    # Filtro per paese e codice
    mask = (def_df['Product CN Code'] == hs_code) & (def_df['Country'] == paese)
    row_def = def_df[mask]
    
    val_def = row_def[col_anno_def].iloc[0] if not row_def.empty else np.nan
    
    # SE VUOTO -> Cerca Other Countries (come richiesto)
    if pd.isna(val_def):
        st.info(f"Dati non presenti per {paese}. Ricerca in 'Other Countries'...")
        other_mask = (def_df['Product CN Code'] == hs_code) & (def_df['Country'].str.contains("Other", case=False, na=False))
        row_other = def_df[other_mask]
        val_def = row_other[col_anno_def].iloc[0] if not row_other.empty else 0.0
    
    valore_emissioni = val_def

# 3. Selezione Benchmark e Production Route (Gestione Lettere C, D, E...)
filtro_bench = bench_df[bench_df['CN code'] == hs_code]

# Filtro per periodo (1) o (2) se l'indicatore lo specifica (es. (F)(1))
def check_period(ind):
    ind = str(ind)
    if periodo in ind: return True
    if "(1)" not in ind and "(2)" not in ind: return True
    return False

opzioni_valide = filtro_bench[filtro_bench[col_route].apply(check_period)]

# Se ci sono più righe (Production Routes diverse), chiedi all'utente
if len(opzioni_valide) > 1:
    st.warning("🔎 Trovate più rotte di produzione per questo codice. Seleziona quella corretta:")
    mappa_rotte = {}
    for idx, r in opzioni_valide.iterrows():
        label = str(r[col_route]) if pd.notna(r[col_route]) else f"Default (Riga {idx})"
        mappa_rotte[label] = r[col_bench]
    
    rotta_scelta = st.selectbox("Production Route", list(mappa_rotte.keys()))
    valore_benchmark = mappa_rotte[rotta_scelta]
else:
    valore_benchmark = opzioni_valide[col_bench].iloc[0] if not opzioni_valide.empty else 0.0

# --- RISULTATI ---
st.divider()
c1, c2, c3 = st.columns(3)

# Calcolo Free Allowance (Esempio semplificato: 97.5% per 2026)
fa_perc = 97.5 if anno <= 2026 else 95.0
prezzo_ets = 80.0 # Prezzo ipotetico certificates
quota_pagabile = max(0, valore_emissioni - (valore_benchmark * fa_perc / 100))
costo_totale = quota_pagabile * volume * prezzo_ets

with c1:
    st.metric("Emissioni Applicate", f"{valore_emissioni:.4f} tCO2/t")
    st.caption("Dato " + ("Reale" if usare_reali else "Default"))

with c2:
    st.metric("Benchmark", f"{valore_benchmark:.4f} tCO2/t")
    st.caption(f"Basato su Colonna {'A' if usare_reali else 'B'}")

with c3:
    st.metric("Costo Stimato", f"€ {costo_totale:,.2f}")
    st.caption(f"Volume: {volume} Ton")

st.info(f"**Descrizione:** {filtro_bench['CN Description'].iloc[0]}")
