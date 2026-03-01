import streamlit as st
import pandas as pd
import numpy as np
import os

st.set_page_config(page_title="CBAM Calculator", layout="wide")

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
    # Usa i nomi esatti dei file che hai caricato
    f_bench = "benchmarks final.csv"
    f_defaults = "cbam defaults.xlsx - cbam defaults.csv"

    # 1. Verifica Esistenza
    if not os.path.exists(f_bench) or not os.path.exists(f_defaults):
        st.error(f"⚠️ File mancanti! Carica '{f_bench}' e '{f_defaults}' nella cartella dell'app.")
        st.stop()

    # 2. Verifica se sono vuoti (Previene EmptyDataError)
    if os.path.getsize(f_bench) == 0 or os.path.getsize(f_defaults) == 0:
        st.error("⚠️ Uno dei file CSV è vuoto. Carica una versione con dati.")
        st.stop()

    try:
        # Caricamento Benchmarks (Semicolon)
        bench = pd.read_csv(f_bench, sep=";", engine='python')
        bench.columns = [c.replace("\n", " ").strip() for c in bench.columns]
        
        # Caricamento Defaults (Comma)
        defaults = pd.read_csv(f_defaults, engine='python')
        defaults.columns = [c.strip() for c in defaults.columns]

        # Pulizia HS Code (rimuove .0 se presente)
        col_hs_bm = next(c for c in bench.columns if "CN code" in c)
        bench[col_hs_bm] = bench[col_hs_bm].ffill().astype(str).str.replace(r'\.0$', '', regex=True)
        
        col_hs_def = next(c for c in defaults.columns if "CN Code" in c)
        defaults[col_hs_def] = defaults[col_hs_def].astype(str).str.replace(r'\.0$', '', regex=True)

        return bench, defaults, col_hs_bm, col_hs_def

    except Exception as e:
        st.error(f"Errore durante la lettura dei file: {e}")
        st.stop()

# Caricamento
bench_df, def_df, COL_HS_BM, COL_HS_DEF = load_data()

st.title("📊 Calcolatore Emissioni CBAM")

# --- SIDEBAR ---
with st.sidebar:
    st.header("Configurazione")
    anno = st.selectbox("Anno di riferimento", [2026, 2027, 2028, 2029, 2030])
    periodo_key = "(1)" if anno <= 2027 else "(2)"
    
    paese = st.selectbox("Paese di Origine", sorted(def_df['Country'].unique()))
    hs_code = st.selectbox("Codice HS", sorted(bench_df[COL_HS_BM].unique()))
    
    volume = st.number_input("Volume (Ton)", min_value=0.0, value=1.0)
    emissioni_reali = st.number_input("Emissioni Reali Dirette (tCO2e/t)", min_value=0.0, format="%.4f")

# --- LOGICA CBAM ---
usare_reali = emissioni_reali > 0

# Identificazione colonne Benchmark
col_bmg_a = next(c for c in bench_df.columns if "Column A" in c and "BMg" in c)
col_ind_a = next(c for c in bench_df.columns if "Column A" in c and "indicator" in c)
col_bmg_b = next(c for c in bench_df.columns if "Column B" in c and "BMg" in c)
col_ind_b = next(c for c in bench_df.columns if "Column B" in c and "indicator" in c)

# Selezione colonne in base a reali/default
c_bench = col_bmg_a if usare_reali else col_bmg_b
c_route = col_ind_a if usare_reali else col_ind_b

# 1. Calcolo Emissioni Applicate
if usare_reali:
    valore_emissioni = emissioni_reali
else:
    # Cerca nei default per anno (H=2026, I=2027, L=2028...)
    col_def_anno = next((c for c in def_df.columns if str(min(anno, 2028)) in c), None)
    
    row_def = def_df[(def_df[COL_HS_DEF] == hs_code) & (def_df['Country'] == paese)]
    val_def = clean_numeric(row_def[col_def_anno].iloc[0]) if not row_def.empty else np.nan
    
    # Fallback Other Countries
    if pd.isna(val_def):
        st.info("Dato non trovato per il paese. Uso 'Other Countries'.")
        row_other = def_df[(def_df[COL_HS_DEF] == hs_code) & (def_df['Country'].str.contains("Other", na=False))]
        val_def = clean_numeric(row_other[col_def_anno].iloc[0]) if not row_other.empty else 0.0
    valore_emissioni = val_def

# 2. Selezione Benchmark e Rotta
opzioni = bench_df[bench_df[COL_HS_BM] == hs_code]

def filter_period(val):
    val = str(val)
    if periodo_key in val: return True
    if "(1)" not in val and "(2)" not in val: return True
    return False

opzioni_valide = opzioni[opzioni[c_route].apply(filter_period)]

if len(opzioni_valide) > 1:
    st.warning("Seleziona la rotta di produzione:")
    mappa = {f"{r[c_route]} (Valore: {r[c_bench]})": clean_numeric(r[c_bench]) for _, r in opzioni_valide.iterrows()}
    scelta = st.selectbox("Rotta", list(mappa.keys()))
    valore_benchmark = mappa[scelta]
else:
    val_raw = opzioni_valide[c_bench].iloc[0] if not opzioni_valide.empty else 0.0
    valore_benchmark = clean_numeric(val_raw)

# --- RISULTATI ---
st.divider()
c1, c2, c3 = st.columns(3)

# Calcolo economico stimato (ETS ~80€, FA 97.5%)
fa_perc = 97.5 if anno <= 2026 else 95.0
prezzo_ets = 75.0
costo = max(0, valore_emissioni - (valore_benchmark * fa_perc / 100)) * volume * prezzo_ets

c1.metric("Emissioni Applicate", f"{valore_emissioni:.4f} tCO2/t")
c2.metric("Benchmark", f"{valore_benchmark:.4f}")
c3.metric("Costo Stimato Certificati", f"€ {costo:,.2f}")


