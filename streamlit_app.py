import streamlit as st
import pandas as pd
import numpy as np
import os
import glob
import re

st.set_page_config(page_title="CBAM Calculator PRO", layout="wide")

# --- FUNZIONI DI SUPPORTO ---
def clean_num(val):
    if pd.isna(val) or str(val).strip() in ["", "#VALUE!", "NaN"]: return np.nan
    if isinstance(val, str):
        val = val.replace(",", ".").strip()
        try: return float(val)
        except: return np.nan
    return float(val)

def find_file(pattern):
    files = glob.glob(f"*{pattern}*.csv")
    return files[0] if files else None

@st.cache_data
def load_data():
    f_bench = find_file("benchmark")
    f_def = find_file("default")
    
    if not f_bench or not f_def:
        st.error("❌ File non trovati! Assicurati che i CSV siano nella stessa cartella dello script.")
        st.stop()

    # Caricamento con gestione errori
    try:
        df_b = pd.read_csv(f_bench, sep=";", encoding='utf-8', engine='python')
        df_d = pd.read_csv(f_def, sep=",", encoding='utf-8', engine='python')
    except:
        df_b = pd.read_csv(f_bench, sep=";", encoding='latin1', engine='python')
        df_d = pd.read_csv(f_def, sep=",", encoding='latin1', engine='python')

    # Pulizia nomi colonne (rimuove \n, spazi e virgolette)
    df_b.columns = [re.sub(r'[\r\n\t"]', ' ', col).strip() for col in df_b.columns]
    df_d.columns = [re.sub(r'[\r\n\t"]', ' ', col).strip() for col in df_d.columns]

    # Riempimento codici HS (ffill per le celle unite)
    col_hs_b = [c for c in df_b.columns if "CN code" in c][0]
    df_b[col_hs_b] = df_b[col_hs_b].ffill().astype(str).str.replace(r'\.0$', '', regex=True)
    
    col_hs_d = [c for c in df_d.columns if "CN Code" in c][0]
    df_d[col_hs_d] = df_d[col_hs_d].astype(str).str.replace(r'\.0$', '', regex=True)

    return df_b, df_d, col_hs_b, col_hs_d

# --- AVVIO APP ---
try:
    bench, defaults, HS_B, HS_D = load_data()
except Exception as e:
    st.error(f"Errore critico nel caricamento: {e}")
    st.stop()

st.title("🛡️ Calcolatore CBAM Professionale")

# --- INPUT UTENTE ---
with st.sidebar:
    anno = st.selectbox("Anno", [2026, 2027, 2028, 2029, 2030])
    periodo_target = "(1)" if anno <= 2027 else "(2)"
    
    paese = st.selectbox("Paese di Origine", sorted(defaults['Country'].unique()))
    codice_hs = st.selectbox("Codice HS", sorted(bench[HS_B].unique()))
    
    vol = st.number_input("Volume (Ton)", min_value=0.0, value=1.0)
    reali = st.number_input("Emissioni Reali (tCO2/t) - [0 = Usa Default]", min_value=0.0, format="%.4f")

# --- LOGICA DI CALCOLO ---
usare_reali = reali > 0
pfx = "Column A" if usare_reali else "Column B"

# 1. Trova le colonne corrette del Benchmark
col_bmg = [c for c in bench.columns if pfx in c and "BMg" in c][0]
col_ind = [c for c in bench.columns if pfx in c and "indicator" in c][0]

# 2. Filtra per HS e Periodo (1)/(2)
mask = (bench[HS_B] == codice_hs)
opzioni = bench[mask].copy()

def filter_periodo(val):
    v = str(val)
    if periodo_target in v: return True
    if "(1)" not in v and "(2)" not in v: return True
    return False

opzioni = opzioni[opzioni[col_ind].apply(filter_periodo)]

# 3. Gestione Production Route (C, D, E...)
if len(opzioni) > 1:
    st.info("Multiple Production Routes rilevate.")
    rotte = {}
    for i, row in opzioni.iterrows():
        label = str(row[col_ind]) if pd.notna(row[col_ind]) else "Default"
        rotte[label] = clean_num(row[col_bmg])
    scelta = st.selectbox("Seleziona Rotta (Production Route)", list(rotte.keys()))
    benchmark_val = rotte[scelta]
else:
    benchmark_val = clean_num(opzioni[col_bmg].iloc[0]) if not opzioni.empty else 0.0

# 4. Calcolo Emissioni Applicate (Logica Defaults + Fallback)
if usare_reali:
    emissioni_finali = reali
else:
    col_def = [c for c in defaults.columns if str(min(anno, 2028)) in c][0]
    # Cerca per paese
    row_def = defaults[(defaults[HS_D] == codice_hs) & (defaults['Country'] == paese)]
    val = clean_num(row_def[col_def].iloc[0]) if not row_def.empty else np.nan
    
    # SE VUOTO -> Altri Paesi (Other Countries)
    if pd.isna(val):
        row_other = defaults[(defaults[HS_D] == codice_hs) & (defaults['Country'].str.contains("Other", na=False))]
        val = clean_num(row_other[col_def].iloc[0]) if not row_other.empty else 0.0
        st.warning(f"Dati non trovati per {paese}. Usato valore di default 'Other Countries'.")
    emissioni_finali = val

# --- RISULTATI ---
st.divider()
c1, c2, c3 = st.columns(3)

# Calcolo costi (Esempio: Prezzo ETS 80€, Free Allowance 97.5% decrescente)
fa = 97.5 if anno <= 2026 else (95.0 if anno == 2027 else 92.5)
prezzo_ets = 75.0
costo = max(0, emissioni_finali - (benchmark_val * fa / 100)) * vol * prezzo_ets

c1.metric("Emissioni Applicate", f"{emissioni_finali:.4f} tCO2/t")
c2.metric("Benchmark CBAM", f"{benchmark_val:.4f}")
c3.metric("Costo Totale Stimato", f"€ {costo:,.2f}")

st.write(f"**Prodotto:** {bench[bench[HS_B]==codice_hs]['CN Description'].iloc[0]}")



