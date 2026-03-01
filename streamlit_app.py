import streamlit as st
import pandas as pd
import numpy as np
import os
import re

st.set_page_config(page_title="CBAM Professional Calculator", layout="wide")

# --- FUNZIONE PULIZIA NUMERI ---
def pulisci_numero(val):
    if pd.isna(val) or str(val).strip() in ["", "#VALUE!", "nan", "NaN"]:
        return np.nan
    if isinstance(val, str):
        val = val.strip().replace(",", ".")
        val = re.sub(r'[^\d.-]', '', val)
        try: return float(val)
        except: return np.nan
    return float(val)

# --- CARICAMENTO DATI CON PULIZIA COLONNE ---
@st.cache_data
def load_data():
    files = os.listdir(".")
    f_bench = next((f for f in files if "bench" in f.lower() and f.endswith(".csv")), None)
    f_def = next((f for f in files if "default" in f.lower() and f.endswith(".csv")), None)

    if not f_bench or not f_def:
        st.error(f"❌ File non trovati! Assicurati di aver caricato i file CSV. File rilevati: {files}")
        st.stop()

    # Caricamento e pulizia immediata nomi colonne (rimuove spazi e caratteri invisibili)
    df_b = pd.read_csv(f_bench, sep=";", engine='python', on_bad_lines='skip')
    df_b.columns = df_b.columns.str.strip().str.replace('"', '')
    
    df_d = pd.read_csv(f_def, sep=",", engine='python', on_bad_lines='skip')
    df_d.columns = df_d.columns.str.strip().str.replace('"', '')

    # Gestione HS Code e ffill
    col_hs_b = next(c for c in df_b.columns if "CN code" in c)
    df_b[col_hs_b] = df_b[col_hs_b].ffill().astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    
    col_hs_d = next(c for c in df_d.columns if "CN Code" in c)
    df_d[col_hs_d] = df_d[col_hs_d].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

    # Identificazione colonna Paese (evita KeyError)
    col_paese = next((c for c in df_d.columns if "country" in c.lower()), df_d.columns[0])

    return df_b, df_d, col_hs_b, col_hs_d, col_paese

# --- ESECUZIONE ---
try:
    bench, defaults, HS_B, HS_D, COL_PAESE = load_data()
except Exception as e:
    st.error(f"Errore critico: {e}")
    st.stop()

st.title("🛡️ CBAM Professional Calculator")

[Image of a logical flowchart showing CBAM decision making: If Real Emissions > 0 use Column A, else use Column B and check country defaults with fallback to Other Countries]

with st.sidebar:
    st.header("1. Parametri")
    anno = st.selectbox("Anno", [2026, 2027, 2028, 2029, 2030])
    periodo_req = "(1)" if anno <= 2027 else "(2)"
    
    # Usiamo COL_PAESE per sicurezza
    paese_sel = st.selectbox("Paese di Origine", sorted(defaults[COL_PAESE].unique()))
    hs_sel = st.selectbox("Codice HS", sorted(bench[HS_B].unique()))
    
    volume = st.number_input("Volume (Ton)", min_value=0.0, value=1.0)
    reali = st.number_input("Emissioni Reali (tCO2e/t)", min_value=0.0, format="%.4f")
    prezzo_ets = st.number_input("Prezzo ETS (€/tCO2)", value=80.0)

# --- LOGICA CALCOLO ---
usare_reali = reali > 0
tag = "Column A" if usare_reali else "Column B"
col_bmg = next(c for c in bench.columns if tag in c and "BMg" in c)
col_ind = next(c for c in bench.columns if tag in c and "indicator" in c)

# 1. EMISSIONI (Paese vs Other Countries)
if usare_reali:
    emissioni_finali = reali
    orig_info = "Dato Reale"
else:
    col_anno_def = next(c for c in defaults.columns if str(min(anno, 2028)) in c)
    r_paese = defaults[(defaults[HS_D] == hs_sel) & (defaults[COL_PAESE] == paese_sel)]
    val_default = pulisci_numero(r_paese[col_anno_def].iloc[0]) if not r_paese.empty else np.nan
    
    if pd.isna(val_default):
        r_other = defaults[(defaults[HS_D] == hs_sel) & (defaults[COL_PAESE].str.contains("Other", na=False))]
        val_default = pulisci_numero(r_other[col_anno_def].iloc[0]) if not r_other.empty else 0.0
        orig_info = "Default (Other Countries)"









