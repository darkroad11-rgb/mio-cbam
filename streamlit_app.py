import streamlit as st
import pandas as pd
import numpy as np
import os
import re

st.set_page_config(page_title="CBAM Calculator PRO", layout="wide")

# --- FUNZIONE PULIZIA DATI ---
def pulisci_numero(val):
    if pd.isna(val) or str(val).strip() in ["", "#VALUE!", "nan", "NaN"]:
        return 0.0
    if isinstance(val, str):
        val = val.strip().replace(",", ".")
        val = re.sub(r'[^\d.-]', '', val)
        try:
            return float(val)
        except:
            return 0.0
    return float(val)

# --- CARICAMENTO DATI ---
@st.cache_data
def load_data():
    f_bench = "benchmarks final.csv"
    f_def = "cbam defaults.xlsx - cbam defaults.csv"

    if not os.path.exists(f_bench) or not os.path.exists(f_def):
        st.error(f"⚠️ File non trovati! Assicurati che i nomi siano esattamente: '{f_bench}' e '{f_def}'")
        st.stop()

    # Benchmark (Semicolon ;)
    df_b = pd.read_csv(f_bench, sep=";", engine='python', on_bad_lines='skip')
    df_b.columns = df_b.columns.str.strip().str.replace('"', '').str.replace('\n', ' ')

    # Defaults (Comma ,) - Fondamentale per pulire il menu a tendina
    df_d = pd.read_csv(f_def, sep=",", engine='python', on_bad_lines='skip')
    df_d.columns = df_d.columns.str.strip().str.replace('"', '').str.replace('\n', ' ')

    # Normalizzazione Codici HS (rimuove .0 e spazi)
    col_hs_b = next(c for c in df_b.columns if "CN code" in c)
    df_b[col_hs_b] = df_b[col_hs_b].ffill().astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    
    col_hs_d = next(c for c in df_d.columns if "CN Code" in c)
    df_d[col_hs_d] = df_d[col_hs_d].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

    # Identificazione colonna Paese
    col_paese = next((c for c in df_d.columns if "Country" in c), df_d.columns[0])

    return df_b, df_d, col_hs_b, col_hs_d, col_paese

# --- AVVIO ---
try:
    bench, defaults, HS_B, HS_D, COL_PAESE = load_data()
except Exception as e:
    st.error(f"Errore caricamento database: {e}")
    st.stop()

st.title("🛡️ CBAM Professional Calculator")

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Parametri")
    anno = st.selectbox("Anno di riferimento", [2026, 2027, 2028, 2029, 2030])
    periodo_req = "(1)" if anno <= 2027 else "(2)"
    
    paese_origine = st.selectbox("Paese di Origine", sorted(defaults[COL_PAESE].unique()))
    codice_hs = st.selectbox("Codice HS Prodotto", sorted(bench[HS_B].unique()))
    
    volume = st.number_input("Volume (Ton)", min_value=0.0, value=1.0)
    reali_input = st.number_input("Emissioni Reali Dirette (tCO2e/t)", min_value=0.0, format="%.4f")
    prezzo_ets = st.number_input("Prezzo ETS (€/tCO2)", value=80.0)
    
    # Stima Free Allowance (97.5% nel 2026)
    fa_stima = 97.5 if anno <= 2026 else (95.0 if anno == 2027 else 92.5)
    free_allowance = st.slider("Free Allowance (%)", 0.0, 100.0, fa_stima)

# --- LOGICA CALCOLO ---

# Selezione Colonna A (Reali) o B (Default)
usare_reali = reali_input > 0
pref = "Column A" if usare_reali else "Column B"

col_bmg_bench = next(c for c in bench.columns if pref in c and "BMg" in c)
col_ind_bench = next(c for c in bench.columns if pref in c and "indicator" in c)

# Filtro HS e Periodo (1) o (2)
df_hs = bench[bench[HS_B] == codice_hs].copy()
def filter_period(val):
    v = str(val)
    if periodo_req in v: return True
    if "(1)" not in v and "(2)" not in v: return True
    return False

df_valido = df_hs[df_hs[col_ind_bench].apply(filter_period)]

# Benchmark Val
benchmark_val = 0.0
if len(df_valido) > 1:
    st.warning("🔎 Seleziona la Rotta di Produzione (Production Route):")
    rotte = {f"{r[col_ind_bench]} - Val: {r[col_bmg_bench]}": pulisci_numero(r[col_bmg_bench]) for _, r in df_valido.iterrows()}
    scelta = st.selectbox("Indicator", list(rotte.keys()))
    benchmark_val = float(rotte[scelta])
else:
    raw_bmg = df_valido[col_bmg_bench].iloc[0] if not df_valido.empty else 0.0
    benchmark_val = float(pulisci_numero(raw_bmg))

# --- DETERMINAZIONE EMISSIONI (Fallback Other Countries) ---
if usare_reali:
    emissioni_finali = float(reali_input)
    tipo_orig = "Dato Reale"
else:
    # Colonne Default per anno
    col_anno_def = next(c for c in defaults.columns if str(min(anno, 2028)) in c)
    
    row_p = defaults[(defaults[HS_D] == codice_hs) & (defaults[COL_PAESE] == paese_origine)]
    val_p = row_p[col_anno_def].iloc[0] if not row_p.empty else np.nan
    
    # Se il valore del paese è vuoto (NaN), usa Other Countries
    if pd.isna(val_p):
        row_o = defaults[(defaults[HS_D] == codice_hs) & (defaults[COL_PAESE].str.contains("Other", na=False))]
        emissioni_finali = float(pulisci_numero(row_o[col_anno_def].iloc[0])) if not row_o.empty else 0.0
        tipo_orig = "Default (Other Countries)"
        st.info(f"Dati per {paese_origine} assenti. Utilizzato valore globale.")
    else:
        emissioni_finali = float(pulisci_numero(val_p))
        tipo_orig = f"Default ({paese_origine})"

# --- RISULTATI ---
st.divider()
c1, c2, c3 = st.columns(3)

quota_esente = benchmark_val * (free_allowance / 100)
costo_totale = max(0, emissioni_finali - quota_esente) * volume * prezzo_ets

c1.metric("Emissioni Applicate", f"{emissioni_finali:.4f} tCO2/t", tipo_orig)
c2.metric("Benchmark Scontato", f"{quota_esente:.4f} tCO2/t", f"Lordo: {benchmark_val:.4f}")
c3.metric("Costo Totale", f"€ {costo_totale:,.2f}", f"Volume: {volume} t")












