import streamlit as st
import pandas as pd
import numpy as np
import re

st.set_page_config(page_title="Calcolatore CBAM Pro", layout="wide")

# Funzione per pulizia numerica avanzata
def clean_numeric(val):
    if pd.isna(val) or val == '' or str(val).strip() in ['#VALUE!', 'nan', 'NaN']:
        return np.nan
    if isinstance(val, str):
        val = val.strip().replace(',', '.')
        try:
            return float(val)
        except ValueError:
            return np.nan
    return float(val)

@st.cache_data
def load_data():
    # Caricamento Benchmarks (Semicolon)
    bench = pd.read_csv("benchmarks final.csv", sep=";", engine='python')
    bench.columns = [c.replace("\n", " ").strip() for c in bench.columns]
    
    # Pulizia codici HS e riempimento celle unite (ffill)
    col_hs_b = next(c for c in bench.columns if "CN code" in c)
    bench[col_hs_b] = bench[col_hs_b].ffill().astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    
    # Caricamento Defaults (Comma)
    defaults = pd.read_csv("cbam defaults.xlsx - cbam defaults.csv", engine='python')
    defaults.columns = [c.strip() for c in defaults.columns]
    col_hs_d = next(c for c in defaults.columns if "CN Code" in c)
    defaults[col_hs_d] = defaults[col_hs_d].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    
    # Pulizia numerica
    for col in [c for c in bench.columns if "BMg" in c]:
        bench[col] = bench[col].apply(clean_numeric)
    for col in [c for c in defaults.columns if "Default Value" in c]:
        defaults[col] = defaults[col].apply(clean_numeric)
        
    return bench, defaults, col_hs_b, col_hs_d

try:
    bench_df, def_df, COL_HS_B, COL_HS_D = load_data()
except Exception as e:
    st.error(f"Errore caricamento file: {e}")
    st.stop()

st.title("🛡️ Calcolatore Emissioni e Costi CBAM")

# --- SIDEBAR INPUT ---
with st.sidebar:
    st.header("1. Parametri Generali")
    anno = st.selectbox("Anno di riferimento", [2026, 2027, 2028, 2029, 2030])
    periodo_req = "(1)" if anno <= 2027 else "(2)"
    
    paese_sel = st.selectbox("Paese di Origine", sorted(def_df['Country'].unique()))
    hs_sel = st.selectbox("Codice HS", sorted(bench_df[COL_HS_B].unique()))
    
    vol = st.number_input("Volume (Ton)", min_value=0.0, value=1.0)
    reali = st.number_input("Emissioni Reali (tCO2e/t) [0 = Default]", min_value=0.0, format="%.4f")
    prezzo_ets = st.number_input("Prezzo ETS (€/tCO2)", value=80.0)
    
    # Free Allowance (Stima standard: 97.5% nel 2026)
    fa_default = 97.5 if anno <= 2026 else (95.0 if anno == 2027 else 92.5)
    fa_perc = st.slider("Free Allowance (%)", 0.0, 100.0, fa_default)

# --- LOGICA CORE ---

# A. Determinazione Emissioni (Real vs Default Paese vs Other Countries)
usare_reali = reali > 0
if usare_reali:
    emissioni_finali = reali
    tipo_emiss = "Reale"
else:
    col_anno_def = next(c for c in def_df.columns if str(min(anno, 2028)) in c)
    # Cerca valore specifico per paese
    row_def = def_df[(def_df[COL_HS_D] == hs_sel) & (def_df['Country'] == paese_sel)]
    val_def = clean_numeric(row_def[col_anno_def].iloc[0]) if not row_def.empty else np.nan
    
    # FALLBACK: Se vuoto, usa 'Other Countries and Territories'
    if pd.isna(val_def):
        row_other = def_df[(def_df[COL_HS_D] == hs_sel) & (def_df['Country'].str.contains("Other", na=False))]
        val_def = clean_numeric(row_other[col_anno_def].iloc[0]) if not row_other.empty else 0.0
        tipo_emiss = "Default (Other Countries)"
        st.info(f"Valore per {paese_sel} assente. Utilizzato default globale.")
    else:
        tipo_emiss = f"Default ({paese_sel})"
    emissioni_finali = val_def

# B. Selezione Benchmark e Rotta
prefisso = "Column A" if usare_reali else "Column B"
c_bmg = next(c for c in bench_df.columns if prefisso in c and "BMg" in c)
c_ind = next(c for c in bench_df.columns if prefisso in c and "indicator" in c)

# Filtro per HS e Periodo (1) o (2)
df_hs = bench_df[bench_df[COL_HS_B] == hs_sel].copy()
def filter_period(val):
    v = str(val)
    if periodo_req in v: return True
    if "(1)" not in v and "(2)" not in v: return True
    return False

df_valido = df_hs[df_hs[c_ind].apply(filter_period)]

if len(df_valido) > 1:
    st.warning("Multiple rotte di produzione rilevate.")
    mappa_rotte = {f"{r[c_ind]} (Val: {r[c_bmg]})": clean_numeric(r[c_bmg]) for _, r in df_valido.iterrows()}
    scelta = st.selectbox("Seleziona Rotta (Production Route)", list(mappa_rotte.keys()))
    benchmark_val = mappa_rotte[scelta]
else:
    benchmark_val = clean_numeric(df_valido[c_bmg].iloc[0]) if not df_valido.empty else 0.0

# --- CALCOLO FINALE ---
quota_esente = benchmark_val * (fa_perc / 100)
eccesso = max(0, emissioni_finali - quota_esente)
costo_tot = eccesso * vol * prezzo_ets

# --- DISPLAY ---
st.divider()
col1, col2, col3 = st.columns(3)
col1.metric("Emissioni Applicate", f"{emissioni_finali:.4f} tCO2/t", tipo_emiss)
col2.metric("Benchmark Scontato", f"{quota_esente:.4f} tCO2/t", f"Lordo: {benchmark_val:.4f}")
col3.metric("Costo CBAM Totale", f"€ {costo_tot:,.2f}", f"Volume: {vol} t")

with st.expander("Dettagli Tecnici"):
    st.write(f"**Prodotto:** {df_hs['CN Description'].iloc[0]}")
    st.write(f"**Periodo:** {periodo_req}")
    st.write(f"**Formula:** `({emissioni_finali:.4f} - ({benchmark_val:.4f} * {fa_perc/100:.3f})) * {vol} * {prezzo_ets}`")










