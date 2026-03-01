import streamlit as st
import pandas as pd
import numpy as np
import os
import re

st.set_page_config(page_title="CBAM Professional Calculator", layout="wide")

# --- FUNZIONI DI PULIZIA ---
def clean_numeric(val):
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

@st.cache_data
def load_all_data():
    # Definiamo i nomi dei file come caricati
    f_bench = "benchmarks final.csv"
    f_def = "cbam defaults.xlsx - cbam defaults.csv"

    if not os.path.exists(f_bench) or not os.path.exists(f_def):
        st.error(f"⚠️ File non trovati! Assicurati che nella cartella ci siano: '{f_bench}' e '{f_def}'")
        st.stop()

    # Caricamento Benchmarks (Semicolon)
    df_b = pd.read_csv(f_bench, sep=";", engine='python', on_bad_lines='skip')
    df_b.columns = [c.replace("\n", " ").strip() for c in df_b.columns]
    
    # Caricamento Defaults (Comma)
    df_d = pd.read_csv(f_def, sep=",", engine='python', on_bad_lines='skip')
    df_d.columns = [c.strip() for c in df_d.columns]

    # Riempimento HS Code e pulizia
    col_hs_b = [c for c in df_b.columns if "CN code" in c][0]
    df_b[col_hs_b] = df_b[col_hs_b].ffill().astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    
    col_hs_d = [c for c in df_d.columns if "CN Code" in c][0]
    df_d[col_hs_d] = df_d[col_hs_d].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

    return df_b, df_d, col_hs_b, col_hs_d

# --- CARICAMENTO ---
bench, defaults, HS_B, HS_D = load_all_data()

st.title("🛡️ Calcolatore CBAM - Modulo Integrale")

# --- SIDEBAR INPUT ---
with st.sidebar:
    st.header("1. Configurazione")
    anno = st.selectbox("Anno di riferimento", [2026, 2027, 2028, 2029, 2030])
    periodo_key = "(1)" if anno <= 2027 else "(2)"
    
    paese = st.selectbox("Paese di Origine", sorted(defaults['Country'].unique()))
    codice_hs = st.selectbox("Codice HS Prodotto", sorted(bench[HS_B].unique()))
    
    tonnellate = st.number_input("Volume Importato (Ton)", min_value=0.0, value=1.0, step=0.1)
    reali_input = st.number_input("Emissioni Reali Dirette (tCO2e/t)", min_value=0.0, value=0.0, format="%.4f", help="Lascia 0 se non hai dati reali")

    st.header("2. Parametri Economici")
    prezzo_ets = st.number_input("Prezzo ETS (€/tCO2)", value=80.0)
    # Calcolo Free Allowance stima
    fa_stima = 97.5 if anno <= 2026 else (95.0 if anno == 2027 else 92.5)
    free_allowance = st.slider("Free Allowance (%)", 0.0, 100.0, fa_stima)

# --- LOGICA CORE ---

# A. Emissioni: Reali o Default?
usare_reali = reali_input > 0
etichetta_col = "Column A" if usare_reali else "Column B"

# B. Selezione Benchmark e Rotta di Produzione
col_bmg_val = [c for c in bench.columns if etichetta_col in c and "BMg" in c][0]
col_ind_val = [c for c in bench.columns if etichetta_col in c and "indicator" in c][0]

# Filtro HS e Periodo (1/2)
df_prodotto = bench[bench[HS_B] == codice_hs].copy()

def matches_period(val):
    v = str(val)
    if periodo_key in v: return True
    if "(1)" not in v and "(2)" not in v: return True
    return False

df_valido = df_prodotto[df_prodotto[col_ind_val].apply(matches_period)]

# Scelta Rotta se presenti più opzioni (C, D, E...)
benchmark_finale = 0.0
if len(df_valido) > 1:
    st.warning(f"Rotte di produzione multiple trovate per il codice {codice_hs}")
    rotte = {}
    for _, r in df_valido.iterrows():
        # Crea label leggibile per la rotta
        label = str(r[col_ind_val]) if pd.notna(r[col_ind_val]) else "Default"
        rotte[label] = clean_numeric(r[col_bmg_val])
    
    scelta_rotta = st.selectbox("Seleziona Production Route:", list(rotte.keys()))
    benchmark_finale = rotte[scelta_rotta]
else:
    benchmark_finale = clean_numeric(df_valido[col_bmg_val].iloc[0]) if not df_valido.empty else 0.0

# C. Calcolo Emissioni Applicate (con fallback su Other Countries)
if usare_reali:
    emissioni_applicate = reali_input
    desc_origine = "Dato Reale fornito"
else:
    # Trova colonna anno nei default
    col_anno_def = [c for c in defaults.columns if str(min(anno, 2028)) in c][0]
    
    # Cerca Paese + HS
    row_def = defaults[(defaults[HS_D] == codice_hs) & (defaults['Country'] == paese)]
    val_def = clean_numeric(row_def[col_anno_def].iloc[0]) if not row_def.empty else np.nan
    
    # Se vuoto -> Altri Paesi
    if pd.isna(val_def):
        st.info("Emissioni specifiche non trovate. Utilizzo 'Other Countries and Territories'.")
        row_other = defaults[(defaults[HS_D] == codice_hs) & (defaults['Country'].str.contains("Other", na=False))]
        val_def = clean_numeric(row_other[col_anno_def].iloc[0]) if not row_other.empty else 0.0
        desc_origine = "Default (Other Countries)"
    else:
        desc_origine = f"Default ({paese})"
    
    emissioni_applicate = val_def

# --- CALCOLO FINALE ---
# Formula: (Emissioni - (Benchmark * FA%)) * Volume * Prezzo
quota_esente = benchmark_finale * (free_allowance / 100)
eccesso = max(0, emissioni_applicate - quota_esente)
costo_totale = eccesso * tonnellate * prezzo_ets

# --- DISPLAY RISULTATI ---
st.divider()
c1, c2, c3 = st.columns(3)

c1.metric("Emissioni Applicate", f"{emissioni_applicate:.4f} tCO2/t", desc_origine)
c2.metric("Benchmark (Scontato FA)", f"{quota_esente:.4f} tCO2/t", f"Lordo: {benchmark_finale:.4f}")
c3.metric("Costo CBAM Stimato", f"€ {costo_totale:,.2f}", f"Su {tonnellate} t")

with st.expander("Dettagli Tecnici"):
    st.write(f"**Descrizione Merce:** {df_prodotto['CN Description'].iloc[0] if not df_prodotto.empty else 'N/A'}")
    st.write(f"**Periodo Benchmark:** {periodo_key}")
    st.write(f"**Formula:** `({emissioni_applicate:.4f} - {quota_esente:.4f}) * {tonnellate} * {prezzo_ets}`")
