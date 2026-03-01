import streamlit as st
import pandas as pd
import numpy as np
import os
import re

st.set_page_config(page_title="CBAM Pro Calculator", layout="wide")

# --- FUNZIONI DI SUPPORTO ---

def pulisci_numero(val):
    if pd.isna(val) or str(val).strip() in ["", "#VALUE!", "nan", "NaN"]:
        return np.nan
    if isinstance(val, str):
        val = val.strip().replace(",", ".")
        val = re.sub(r'[^\d.-]', '', val)
        try: return float(val)
        except: return np.nan
    return float(val)

def pulisci_rotta(val):
    """Estrae solo la lettera (es. C o D) ignorando tutto il resto."""
    if pd.isna(val) or str(val).strip().lower() in ["nan", "val", ""]:
        return "Standard"
    match = re.search(r'\(([A-Z])\)', str(val))
    if match:
        return match.group(1)
    return str(val)

@st.cache_data
def load_data():
    files = os.listdir(".")
    f_bench = next((f for f in files if "bench" in f.lower() and f.endswith(".csv")), None)
    f_def = next((f for f in files if "default" in f.lower() and f.endswith(".csv")), None)

    if not f_bench or not f_def:
        st.error(f"⚠️ File non trovati! Assicurati di caricare i CSV. Rilevati: {files}")
        st.stop()

    # Benchmark (Semicolon ;)
    df_b = pd.read_csv(f_bench, sep=";", engine='python', on_bad_lines='skip')
    df_b.columns = [c.strip().replace('"', '').replace('\n', ' ') for c in df_b.columns]
    
    # Defaults (Comma ,)
    df_d = pd.read_csv(f_def, sep=",", engine='python', on_bad_lines='skip')
    df_d.columns = [c.strip().replace('"', '').replace('\n', ' ') for c in df_d.columns]

    # Pulizia HS Code (ffill e rimozione .0)
    col_hs_b = next(c for c in df_b.columns if "CN code" in c)
    df_b[col_hs_b] = df_b[col_hs_b].ffill().astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    
    col_hs_d = next(c for c in df_d.columns if "CN Code" in c)
    df_d[col_hs_d] = df_d[col_hs_d].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

    col_paese = next((c for c in df_d.columns if "country" in c.lower()), df_d.columns[0])

    return df_b, df_d, col_hs_b, col_hs_d, col_paese

# --- CARICAMENTO ---
try:
    bench, defaults, HS_B, HS_D, COL_PAESE = load_data()
except Exception as e:
    st.error(f"Errore: {e}")
    st.stop()

st.title("🛡️ CBAM Pro Calculator")

with st.sidebar:
    st.header("Configurazione")
    anno = st.selectbox("Anno di riferimento", [2026, 2027, 2028, 2029, 2030])
    periodo_req = "(1)" if anno <= 2027 else "(2)"
    
    paese_sel = st.selectbox("Paese di Origine", sorted(defaults[COL_PAESE].unique()))
    hs_sel = st.selectbox("Codice HS Prodotto", sorted(bench[HS_B].unique()))
    
    vol = st.number_input("Volume (Ton)", min_value=0.0, value=1.0)
    reali = st.number_input("Emissioni Reali (tCO2e/t) [0 = Default]", min_value=0.0, format="%.4f")
    prezzo_ets = st.number_input("Prezzo ETS (€/tCO2)", value=80.0)

# --- LOGICA CALCOLO ---

# Selezione Benchmark
usare_reali = reali > 0
pref = "Column A" if usare_reali else "Column B"
c_bmg = next(c for c in bench.columns if pref in c and "BMg" in c)
c_ind = next(c for c in bench.columns if pref in c and "indicator" in c)

df_hs = bench[bench[HS_B] == hs_sel].copy()
df_valido = df_hs[df_hs[c_ind].apply(lambda x: periodo_req in str(x) or ("(1)" not in str(x) and "(2)" not in str(x)))]

# Gestione Rotte (Solo Lettere)
benchmark_val = 0.0
if len(df_valido) > 1:
    mappa_rotte = {}
    for _, r in df_valido.iterrows():
        label = pulisci_rotta(r[c_ind])
        mappa_rotte[label] = pulisci_numero(r[c_bmg])
    
    scelta = st.selectbox("Seleziona Rotta (Production Route):", list(mappa_rotte.keys()))
    benchmark_val = mappa_rotte[scelta]
else:
    benchmark_val = pulisci_numero(df_valido[c_bmg].iloc[0]) if not df_valido.empty else 0.0

# Emissioni con Fallback Avanzato
if usare_reali:
    emiss_finali = reali
    tipo_info = "Dato Reale"
else:
    col_yr = next(c for c in defaults.columns if str(min(anno, 2028)) in c)
    
    def find_default(hs, target_country):
        # Prova HS esatto, poi 6 cifre, poi 4 cifre
        for length in [len(hs), 6, 4]:
            hs_cut = hs[:length]
            subset = defaults[defaults[HS_D].str.startswith(hs_cut)]
            
            # 1. Cerca Paese specifico
            row = subset[subset[COL_PAESE] == target_country]
            val = pulisci_numero(row[col_yr].iloc[0]) if not row.empty else np.nan
            
            # 2. Se vuoto, cerca "Other Countries"
            if pd.isna(val):
                row_o = subset[subset[COL_PAESE].str.contains("Other", na=False)]
                val = pulisci_numero(row_o[col_yr].iloc[0]) if not row_o.empty else np.nan
            
            if not pd.isna(val):
                return val, "Default (Other Countries)" if "Other" in str(row_o[COL_PAESE].iloc[0] if not row_o.empty else "") else f"Default ({target_country})"
        return 0.0, "Nessun dato"

    emiss_finali, tipo_info = find_default(hs_sel, paese_sel)
    if "Other" in tipo_info: st.warning(f"Utilizzato valore globale 'Other Countries' per {hs_sel}.")

# --- RISULTATI ---
st.divider()
c1, c2, c3 = st.columns(3)

fa_perc = 97.5 if anno <= 2026 else (95.0 if anno == 2027 else 92.5)
quota_esente = (benchmark_val if not pd.isna(benchmark_val) else 0.0) * (fa_perc / 100)
costo_tot = max(0, emiss_finali - quota_esente) * vol * prezzo_ets

c1.metric("Emissioni Applicate", f"{emiss_finali:.4f} tCO2/t", tipo_info)
c2.metric("Benchmark Scontato", f"{quota_esente:.4f} tCO2/t", f"Lordo: {benchmark_val:.4f}")
c3.metric("Costo CBAM Totale", f"€ {costo_tot:,.2f}")















