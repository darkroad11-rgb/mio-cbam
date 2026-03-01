import streamlit as st
import pandas as pd
import numpy as np
import os
import glob
import re
import io

st.set_page_config(page_title="CBAM Calculator PRO", layout="wide")

# --- FUNZIONI DI PULIZIA ---
def clean_num(val):
    if pd.isna(val) or str(val).strip() in ["", "#VALUE!", "NaN", "nan"]: return np.nan
    if isinstance(val, str):
        # Toglie spazi e gestisce la virgola europea
        val = val.strip().replace(",", ".")
        # Toglie eventuali caratteri non numerici residui (tranne il punto e il meno)
        val = re.sub(r'[^\d.-]', '', val)
        try: return float(val)
        except: return np.nan
    return float(val)

def robust_read_csv(file_path):
    """Legge il CSV provando diversi separatori e ignorando righe corrotte."""
    for sep in [';', ',']:
        try:
            # Leggiamo il file saltando righe vuote e ignorando errori di parsing
            df = pd.read_csv(
                file_path, 
                sep=sep, 
                encoding='utf-8', 
                on_bad_lines='skip', 
                skip_blank_lines=True,
                engine='python'
            )
            # Se ha caricato solo una colonna ma ce ne dovrebbero essere di più, prova l'altro separatore
            if df.shape[1] <= 1:
                continue
            return df
        except:
            continue
    # Ultimo tentativo con encoding diverso (Excel a volte usa latin1)
    return pd.read_csv(file_path, sep=None, engine='python', encoding='latin1', on_bad_lines='skip')

@st.cache_data
def load_data():
    # Cerca i file nella cartella corrente
    files = glob.glob("*.csv")
    f_bench = next((f for f in files if "bench" in f.lower()), None)
    f_def = next((f for f in files if "default" in f.lower()), None)
    
    if not f_bench or not f_def:
        st.error(f"❌ File mancanti! Trovati solo: {files}. Carica i CSV corretti.")
        st.stop()

    df_b = robust_read_csv(f_bench)
    df_d = robust_read_csv(f_def)

    # Pulizia nomi colonne
    df_b.columns = [re.sub(r'[\r\n\t"]', ' ', str(col)).strip() for col in df_b.columns]
    df_d.columns = [re.sub(r'[\r\n\t"]', ' ', str(col)).strip() for col in df_d.columns]

    # Identificazione Colonne HS
    col_hs_b = next((c for c in df_b.columns if "CN code" in c.lower()), df_b.columns[0])
    col_hs_d = next((c for c in df_d.columns if "CN code" in c.lower()), df_d.columns[2])

    # Riempimento celle unite (ffill) e pulizia codici HS
    df_b[col_hs_b] = df_b[col_hs_b].ffill().astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    df_d[col_hs_d] = df_d[col_hs_d].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

    return df_b, df_d, col_hs_b, col_hs_d

# --- LOGICA STREAMLIT ---
try:
    bench, defaults, HS_B, HS_D = load_data()
except Exception as e:
    st.error(f"Errore critico nel caricamento dati: {e}")
    st.stop()

st.title("🛡️ CBAM Calculator - Versione Corretta")

with st.sidebar:
    st.header("1. Parametri")
    anno = st.selectbox("Anno di riferimento", [2026, 2027, 2028, 2029, 2030])
    periodo_target = "(1)" if anno <= 2027 else "(2)"
    
    paese = st.selectbox("Paese di Origine", sorted(defaults['Country'].unique()))
    # Filtriamo i codici HS per quelli effettivamente presenti
    lista_hs = sorted([x for x in bench[HS_B].unique() if str(x) != 'nan'])
    codice_hs = st.selectbox("Codice HS Prodotto", lista_hs)
    
    vol = st.number_input("Volume Importato (Ton)", min_value=0.0, value=1.0)
    reali = st.number_input("Emissioni Reali Dirette (tCO2/t) [0 = Usa Default]", min_value=0.0, format="%.4f")





