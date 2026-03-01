import streamlit as st
import pandas as pd
import numpy as np
import os
import re

st.set_page_config(page_title="CBAM Pro Calculator", layout="wide")

# --- FUNZIONI DI PULIZIA ---

def pulisci_numero(val):
    """Converte stringhe Excel sporche in numeri validi."""
    if pd.isna(val) or str(val).strip() in ["", "#VALUE!", "nan", "NaN"]:
        return np.nan
    if isinstance(val, str):
        val = val.strip().replace(",", ".")
        val = re.sub(r'[^\d.-]', '', val)
        try: return float(val)
        except: return np.nan
    return float(val)

def estrai_rotta_lettera(val):
    """Mostra solo la lettera della rotta (C, D, E) ignorando nan/val."""
    if pd.isna(val) or str(val).strip().lower() in ["nan", "val", ""]:
        return "Standard"
    match = re.search(r'\(([A-Z])\)', str(val))
    if match:
        return f"Rotta {match.group(1)}"
    return str(val)

@st.cache_data
def load_data():
    f_bench = "benchmarks final.csv"
    f_def = "cbam defaults.xlsx - cbam defaults.csv"

    if not os.path.exists(f_bench) or not os.path.exists(f_def):
        st.error("⚠️ File CSV non trovati. Assicurati di caricarli con i nomi esatti.")
        st.stop()

    # Caricamento Benchmarks (Semicolon ;)
    df_b = pd.read_csv(f_bench, sep=";", engine='python', on_bad_lines='skip')
    df_b.columns = [c.strip().replace('"', '').replace('\n', ' ') for c in df_b.columns]
    
    # Caricamento Defaults (Comma ,)
    df_d = pd.read_csv(f_def, sep=",", engine='python', on_bad_lines='skip')
    df_d.columns = [c.strip().replace('"', '').replace('\n', ' ') for c in df_d.columns]

    # Pulizia HS Code (ffill e rimozione .0)
    col_hs_b = next(c for c in df_b.columns if "CN code" in c)
    df_b[col_hs_b] = df_b[col_hs_b].ffill().astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    
    col_hs_d = next(c for c in df_d.columns if "CN Code" in c)
    df_d[col_hs_d] = df_d[col_hs_d].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

    # Identificazione colonna Paese
    col_paese = next((c for c in df_d.columns if "country" in c.lower()), df_d.columns[0])

    return df_b, df_d, col_hs_b, col_hs_d, col_paese

# --- ESECUZIONE CARICAMENTO ---
try:
    bench, defaults, HS_B, HS_D, COL_PAESE = load_data()
except Exception as e:
    st.error(f"Errore caricamento database: {e}")
    st.stop()

st.title("🛡️ CBAM Pro Calculator")

with st.sidebar:
    st.header("1. Parametri Spedizione")
    anno = st.selectbox("Anno di riferimento", [2026, 2027, 2028, 2029, 2030])
    periodo_req = "(1)" if anno <= 2027 else "(2)"
    
    # Dropdown pulito dei paesi
    paese_sel = st.selectbox("Paese di Origine", sorted(defaults[COL_PAESE].unique()))
    codice_hs = st.selectbox("Codice HS Prodotto", sorted(bench[HS_B].unique()))
    
    volume = st.number_input("Volume (Ton)", min_value=0.0, value=1.0)
    reali_input = st.number_input("Emissioni Reali Dirette (tCO2e/t)", min_value=0.0, format="%.4f", help="Se 0, usa Default")
    prezzo_ets = st.number_input("Prezzo ETS (€/tCO2)", value=80.0)

# --- LOGICA CALCOLO ---

# Selezione Benchmark (Colonna A/B)
usare_reali = reali_input > 0
pref = "Column A" if usare_reali else "Column B"
col_bmg_bench = next(c for c in bench.columns if pref in c and "BMg" in c)
col_ind_bench = next(c for c in bench.columns if pref in c and "indicator" in c)

# Filtro HS e Periodo
df_hs = bench[bench[HS_B] == codice_hs].copy()
df_valido = df_hs[df_hs[col_ind_bench].apply(lambda x: periodo_req in str(x) or ("(1)" not in str(x) and "(2)" not in str(x)))]

# 1. SCELTA ROTTA (Solo Lettere)
benchmark_val = 0.0
if len(df_valido) > 1:
    mappa_rotte = {}
    for _, r in df_valido.iterrows():
        label = estrai_rotta_lettera(r[col_ind_bench])
        mappa_rotte[label] = pulisci_numero(r[col_bmg_bench])
    
    scelta_rotta = st.selectbox("Seleziona Rotta di Produzione:", list(mappa_rotte.keys()))
    benchmark_val = mappa_rotte[scelta_rotta]
else:
    benchmark_val = pulisci_numero(df_valido[col_bmg_bench].iloc[0]) if not df_valido.empty else 0.0

# 2. EMISSIONI (Fallback automatico Other Countries)
if usare_reali:
    emiss_finali = reali_input
    tipo_info = "Dato Reale"
else:
    col_yr = next(c for c in defaults.columns if str(min(anno, 2028)) in c)
    # Cerca paese specifico
    mask_paese = (defaults[HS_D] == codice_hs) & (defaults[COL_PAESE] == paese_sel)
    row_p = defaults[mask_paese]
    val_p = pulisci_numero(row_p[col_yr].iloc[0]) if not row_p.empty else np.nan
    
    # FALLBACK: Se il valore è vuoto o assente, passa a Other Countries
    if pd.isna(val_p):
        mask_other = (defaults[HS_D] == codice_hs) & (defaults[COL_PAESE].str.contains("Other Countries", na=False))
        row_o = defaults[mask_other]
        emiss_finali = pulisci_numero(row_o[col_yr].iloc[0]) if not row_o.empty else 0.0
        tipo_info = "Default (Other Countries - Fallback)"
        st.warning(f"Dati per {paese_sel} non trovati. Utilizzato valore globale.")
    else:
        emiss_finali = val_p
        tipo_info = f"Default ({paese_sel})"

# --- RISULTATI ---
st.divider()
c1, c2, c3 = st.columns(3)

fa_perc = 97.5 if anno <= 2026 else (95.0 if anno == 2027 else 92.5)
quota_esente = (benchmark_val if not pd.isna(benchmark_val) else 0.0) * (fa_perc / 100)
costo_totale = max(0, emiss_finali - quota_esente) * volume * prezzo_ets

c1.metric("Emissioni Applicate", f"{emiss_finali:.4f} tCO2/t", tipo_info)
c2.metric("Benchmark Scontato", f"{quota_esente:.4f} tCO2/t", f"Lordo: {benchmark_val:.4f}")
c3.metric("Costo CBAM Totale", f"€ {costo_totale:,.2f}")

with st.expander("Vedi dettagli tecnici"):
    st.write(f"**Descrizione:** {df_hs['CN Description'].iloc[0] if not df_hs.empty else 'N/A'}")
    st.write(f"**Formula:** `({emiss_finali:.4f} - {quota_esente:.4f}) * {volume} * {prezzo_ets}`")
















