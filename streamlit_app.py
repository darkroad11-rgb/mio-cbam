import streamlit as st
import pandas as pd
import numpy as np
import os
import re

st.set_page_config(page_title="CBAM Calculator PRO", layout="wide")

# --- FUNZIONE DI PULIZIA DATI ---
def clean_val(val):
    if pd.isna(val) or str(val).strip() in ["", "#VALUE!", "nan", "NaN"]:
        return np.nan
    if isinstance(val, str):
        val = val.strip().replace(",", ".")
        # Rimuove tutto ciò che non è numero, punto o meno
        val = re.sub(r'[^\d.-]', '', val)
        try:
            return float(val)
        except:
            return np.nan
    return float(val)

@st.cache_data
def load_database():
    # Nomi dei file esatti caricati
    f_bench = "benchmarks final.csv"
    f_def = "cbam defaults.xlsx - cbam defaults.csv"

    if not os.path.exists(f_bench) or not os.path.exists(f_def):
        st.error(f"⚠️ File non trovati! Assicurati che nella cartella ci siano: '{f_bench}' e '{f_def}'")
        st.stop()

    # Caricamento Benchmarks (Semicolon)
    # on_bad_lines='skip' evita l'errore "saw 4 fields" se ci sono righe sporche
    df_b = pd.read_csv(f_bench, sep=";", engine='python', on_bad_lines='skip')
    df_b.columns = [c.replace("\n", " ").strip() for c in df_b.columns]
    
    # Caricamento Defaults (Comma)
    df_d = pd.read_csv(f_def, sep=",", engine='python', on_bad_lines='skip')
    df_d.columns = [c.strip() for c in df_d.columns]

    # Pulizia HS Code (ffill per le celle unite di Excel)
    col_hs_b = next(c for c in df_b.columns if "CN code" in c)
    df_b[col_hs_b] = df_b[col_hs_b].ffill().astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    
    col_hs_d = next(c for c in df_d.columns if "CN Code" in c)
    df_d[col_hs_d] = df_d[col_hs_d].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

    return df_b, df_d, col_hs_b, col_hs_d

# --- CARICAMENTO ---
try:
    bench, defaults, HS_B, HS_D = load_database()
except Exception as e:
    st.error(f"Errore tecnico nel caricamento: {e}")
    st.stop()

# --- INTERFACCIA UTENTE ---
st.title("🛡️ Calcolatore Emissioni CBAM")



with st.sidebar:
    st.header("1. Input Spedizione")
    anno = st.selectbox("Anno di riferimento", [2026, 2027, 2028, 2029, 2030])
    periodo_req = "(1)" if anno <= 2027 else "(2)"
    
    paese_sel = st.selectbox("Paese di Origine", sorted(defaults['Country'].unique()))
    hs_sel = st.selectbox("Codice HS", sorted(bench[HS_B].unique()))
    
    volume = st.number_input("Volume (Tonnellate)", min_value=0.0, value=1.0)
    emissioni_reali = st.number_input("Emissioni Reali (tCO2e/t)", min_value=0.0, format="%.4f", help="Se 0, verranno usati i Default")

    st.header("2. Parametri ETS")
    prezzo_ets = st.number_input("Prezzo Certificato (€/tCO2)", value=80.0)
    # Stima Free Allowance (97.5% nel 2026)
    fa_default = 97.5 if anno <= 2026 else (95.0 if anno == 2027 else 92.5)
    fa_perc = st.slider("Free Allowance (%)", 0.0, 100.0, fa_default)

# --- LOGICA DI CALCOLO ---

# Selezione Colonna A (Reali) o B (Default)
usa_reali = emissioni_reali > 0
pfx = "Column A" if usa_reali else "Column B"

# Trova colonne BMg e Indicator per la colonna scelta
col_bmg = next(c for c in bench.columns if pfx in c and "BMg" in c)
col_ind = next(c for c in bench.columns if pfx in c and "indicator" in c)

# Filtro HS e Periodo (1) o (2)
df_filtro = bench[bench[HS_B] == hs_sel].copy()

def matches_period(val):
    v = str(val)
    if periodo_req in v: return True
    if "(1)" not in v and "(2)" not in v: return True
    return False

df_valido = df_filtro[df_filtro[col_ind].apply(matches_period)]

# Gestione Production Route (Scelta della lettera C, D, E...)
benchmark_applicato = 0.0
if len(df_valido) > 1:
    st.warning(f"Rotte di produzione multiple trovate per HS {hs_sel}")
    mappa_rotte = {}
    for idx, r in df_valido.iterrows():
        # Crea label (es. (C)(1) o (D))
        label = str(r[col_ind]) if pd.notna(r[col_ind]) else "Default"
        mappa_rotte[label] = clean_val(r[col_bmg])
    
    scelta = st.selectbox("Seleziona Rotta di Produzione (Production Route):", list(mappa_rotte.keys()))
    benchmark_applicato = mappa_rotte[scelta]
else:
    if not df_valido.empty:
        benchmark_applicato = clean_val(df_valido[col_bmg].iloc[0])
    else:
        benchmark_applicato = 0.0

# Calcolo Emissioni (con Fallback Country)
if usa_reali:
    emissioni_finali = emissioni_reali
    tipo_e = "Reale"
else:
    tipo_e = "Default"
    col_anno_def = next(c for c in defaults.columns if str(min(anno, 2028)) in c)
    
    # Cerca Paese + HS
    r_def = defaults[(defaults[HS_D] == hs_sel) & (defaults['Country'] == paese_sel)]
    val_def = clean_val(r_def[col_anno_def].iloc[0]) if not r_def.empty else np.nan
    
    # SE VUOTO -> Fallback Other Countries
    if pd.isna(val_def):
        st.info(f"Dati non trovati per {paese_sel}. Utilizzo 'Other Countries'.")
        r_other = defaults[(defaults[HS_D] == hs_sel) & (defaults['Country'].str.contains("Other", na=False))]
        val_def = clean_val(r_other[col_anno_def].iloc[0]) if not r_other.empty else 0.0
    
    emissioni_finali = val_def

# --- RISULTATI ---
st.divider()
c1, c2, c3 = st.columns(3)

# Calcolo: (Emissioni - (Benchmark * FA%)) * Volume * Prezzo
quota_esente = benchmark_applicato * (fa_perc / 100)
eccesso = max(0, emissioni_finali - quota_esente)
costo_tot = eccesso * volume * prezzo_ets

c1.metric("Emissioni Applicate", f"{emissioni_finali:.4f} tCO2/t", f"Origine: {tipo_e}")
c2.metric("Benchmark Scontato", f"{quota_esente:.4f} tCO2/t", f"Lordo: {benchmark_applicato:.4f}")
c3.metric("Costo CBAM Totale", f"€ {costo_tot:,.2f}", f"Volume: {volume}t")

with st.expander("Vedi dettagli tecnici"):
    desc = df_filtro['CN Description'].iloc[0] if not df_filtro.empty else "N/A"
    st.write(f"**Prodotto:** {desc}")
    st.write(f"**Formula:** `({emissioni_finali:.4f} - {quota_esente:.4f}) * {volume} * {prezzo_ets}`")


