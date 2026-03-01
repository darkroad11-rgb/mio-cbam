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
        try:
            return float(val)
        except:
            return np.nan
    return float(val)

# --- FUNZIONE CARICAMENTO DATI ---
@st.cache_data
def load_data():
    files = os.listdir(".")
    f_bench = next((f for f in files if "benchmarks" in f.lower() and f.endswith(".csv")), None)
    f_def = next((f for f in files if "defaults" in f.lower() and f.endswith(".csv")), None)

    if not f_bench or not f_def:
        st.error(f"❌ File non trovati! Assicurati di avere i file CSV nella cartella. Rilevati: {files}")
        st.stop()

    # Leggi Benchmark (delimitatore ;)
    df_b = pd.read_csv(f_bench, sep=";", engine='python', on_bad_lines='skip')
    df_b.columns = [c.strip() for c in df_b.columns] # Rimuove spazi dai nomi colonne

    # Leggi Defaults (delimitatore ,)
    df_d = pd.read_csv(f_def, sep=",", engine='python', on_bad_lines='skip')
    df_d.columns = [c.strip() for c in df_d.columns]

    # Normalizzazione Codici HS e riempimento celle unite (ffill)
    col_hs_b = next(c for c in df_b.columns if "CN code" in c)
    df_b[col_hs_b] = df_b[col_hs_b].ffill().astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    
    col_hs_d = next(c for c in df_d.columns if "CN Code" in c)
    df_d[col_hs_d] = df_d[col_hs_d].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

    # Identificazione Colonne Paese e Default (Usa indici se i nomi variano)
    col_paese = next((c for c in df_d.columns if "country" in c.lower()), df_d.columns[0])
    
    return df_b, df_d, col_hs_b, col_hs_d, col_paese

# --- INIZIO LOGICA ---
try:
    bench, defaults, HS_B, HS_D, COL_PAESE = load_data()
except Exception as e:
    st.error(f"Errore nell'inizializzazione dei dati: {e}")
    st.stop()

st.title("🛡️ CBAM Professional Calculator")

[Image of CBAM calculation logic flowchart]

# --- SIDEBAR: INPUT ---
with st.sidebar:
    st.header("1. Configurazione")
    anno = st.selectbox("Anno di riferimento", [2026, 2027, 2028, 2029, 2030])
    periodo_req = "(1)" if anno <= 2027 else "(2)"
    
    # Risoluzione Errore Country: usiamo COL_PAESE identificata dinamicamente
    paese_origine = st.selectbox("Paese di Origine", sorted(defaults[COL_PAESE].unique()))
    codice_hs = st.selectbox("Codice HS Prodotto", sorted(bench[HS_B].unique()))
    
    volume = st.number_input("Volume Importato (Ton)", min_value=0.0, value=1.0, step=0.1)
    reali_input = st.number_input("Emissioni Reali Dirette (tCO2e/t)", 
                                  min_value=0.0, value=0.0, format="%.4f", 
                                  help="Inserisci il dato reale se disponibile, altrimenti lascia 0 per i default")

    st.header("2. Parametri Economici")
    prezzo_ets = st.number_input("Prezzo ETS (€/tCO2)", value=80.0)
    fa_stima = 97.5 if anno <= 2026 else (95.0 if anno == 2027 else 92.5)
    free_allowance = st.slider("Free Allowance (%)", 0.0, 100.0, fa_stima)

# --- CALCOLO BENCHMARK (Logica Colonna A/B e Rotte C,D,E) ---
usare_reali = reali_input > 0
prefisso = "Column A" if usare_reali else "Column B"

# Identifica le colonne corrette (BMg e Indicator) per la sezione scelta
col_bmg_bench = next(c for c in bench.columns if prefisso in c and "BMg" in c)
col_ind_bench = next(c for c in bench.columns if prefisso in c and "indicator" in c)

# Filtra per HS e Periodo (1) o (2)
df_hs = bench[bench[HS_B] == codice_hs].copy()

def matches_period(val):
    v = str(val)
    if periodo_req in v: return True
    if "(1)" not in v and "(2)" not in v: return True
    return False

df_valido = df_hs[df_hs[col_ind_bench].apply(matches_period)]





