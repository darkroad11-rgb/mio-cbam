import streamlit as st
import pandas as pd
import numpy as np
import re

st.set_page_config(page_title="CBAM Calculator PRO", layout="wide")

def clean_val(val):
    if pd.isna(val) or str(val).strip() in ["", "#VALUE!", "nan", "NaN"]:
        return np.nan
    if isinstance(val, str):
        val = val.strip().replace(",", ".")
        val = re.sub(r'[^\d.-]', '', val)
        try: return float(val)
        except: return np.nan
    return float(val)

@st.cache_data
def load_data():
    # Caricamento Benchmarks
    df_b = pd.read_csv("benchmarks final.csv", sep=";", engine='python', on_bad_lines='skip')
    df_b.columns = [c.replace("\n", " ").strip() for c in df_b.columns]
    col_hs_b = next(c for c in df_b.columns if "CN code" in c)
    df_b[col_hs_b] = df_b[col_hs_b].ffill().astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    
    # Caricamento Defaults
    df_d = pd.read_csv("cbam defaults.xlsx - cbam defaults.csv", engine='python', on_bad_lines='skip')
    df_d.columns = [c.strip() for c in df_d.columns]
    col_hs_d = next(c for c in df_d.columns if "CN Code" in c)
    df_d[col_hs_d] = df_d[col_hs_d].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    
    # Pulizia numerica
    for col in df_b.columns:
        if "BMg" in col: df_b[col] = df_b[col].apply(clean_val)
    for col in df_d.columns:
        if "Default Value" in col: df_d[col] = df_d[col].apply(clean_val)
        
    return df_b, df_d, col_hs_b, col_hs_d

bench, defaults, HS_B, HS_D = load_data()

st.title("📊 Calcolatore CBAM")

with st.sidebar:
    st.header("Configurazione")
    anno = st.selectbox("Anno", [2026, 2027, 2028, 2029, 2030])
    periodo_req = "(1)" if anno <= 2027 else "(2)"
    
    paesi = sorted(defaults['Country'].unique())
    paese_sel = st.selectbox("Paese di Origine", paesi)
    
    hs_list = sorted(bench[HS_B].unique())
    hs_sel = st.selectbox("Codice HS", hs_list)
    
    vol = st.number_input("Volume (Ton)", min_value=0.0, value=1.0)
    reali = st.number_input("Emissioni Reali (tCO2e/t) [Lascia 0 per Default]", min_value=0.0, format="%.4f")
    prezzo_ets = st.number_input("Prezzo ETS (€/tCO2)", value=80.0)

# --- LOGICA CALCOLO ---
usare_reali = reali > 0
tag = "Column A" if usare_reali else "Column B"
col_bmg = next(c for c in bench.columns if tag in c and "BMg" in c)
col_ind = next(c for c in bench.columns if tag in c and "indicator" in c)

# 1. Emissioni Applicate (con Fallback Country)
if usare_reali:
    emissioni_finali = reali
    tipo_orig = "Reale"
else:
    col_anno_def = next(c for c in defaults.columns if str(min(anno, 2028)) in c)
    # Cerca paese specifico
    row_def = defaults[(defaults[HS_D] == hs_sel) & (defaults['Country'] == paese_sel)]
    val_def = clean_val(row_def[col_anno_def].iloc[0]) if not row_def.empty else np.nan
    
    # FALLBACK: Se vuoto o assente, usa Other Countries
    if pd.isna(val_def):
        row_other = defaults[(defaults[HS_D] == hs_sel) & (defaults['Country'].str.contains("Other", na=False))]
        val_def = clean_val(row_other[col_anno_def].iloc[0]) if not row_other.empty else 0.0
        tipo_orig = "Default (Other Countries)"
        st.info(f"Dati per {paese_sel} non presenti. Utilizzato valore 'Other Countries'.")
    else:
        tipo_orig = f"Default ({paese_sel})"
    emissioni_finali = val_def

# 2. Benchmark e Rotte
df_hs = bench[bench[HS_B] == hs_sel].copy()

def check_period(val):
    v = str(val)
    if periodo_req in v: return True
    if "(1)" not in v and "(2)" not in v: return True
    return False

df_periodo = df_hs[df_hs[col_ind].apply(check_period)]

if len(df_periodo) > 1:
    rotte = {}
    for _, r in df_periodo.iterrows():
        label = str(r[col_ind]) if pd.notna(r[col_ind]) else "Default"
        rotte[label] = clean_val(r[col_bmg])
    scelta_rotta = st.selectbox("Seleziona Rotta di Produzione (Indicator)", list(rotte.keys()))
    benchmark_val = rotte[scelta_rotta]
else:
    benchmark_val = clean_val(df_periodo[col_bmg].iloc[0]) if not df_periodo.empty else 0.0

# --- RISULTATI ---
st.divider()
c1, c2, c3 = st.columns(3)

# Calcolo economico (Free Allowance 2026: 97.5%)
fa_perc = 97.5 if anno <= 2026 else (95.0 if anno == 2027 else 92.5)
quota_esente = benchmark_val * (fa_perc / 100)
costo = max(0, emissioni_finali - quota_esente) * vol * prezzo_ets

c1.metric("Emissioni Applicate", f"{emissioni_finali:.4f} tCO2/t", tipo_orig)
c2.metric("Benchmark Scontato", f"{quota_esente:.4f} tCO2/t", f"Lordo: {benchmark_val:.4f}")
c3.metric("Costo Totale Stimato", f"€ {costo:,.2f}")







