import streamlit as st
import pandas as pd
import numpy as np
import os
import re

st.set_page_config(page_title="CBAM Pro Calculator", layout="wide")

# --- FUNZIONI DI PULIZIA ---

def pulisci_numero(val):
    if pd.isna(val) or str(val).strip() in ["", "#VALUE!", "nan", "NaN"]:
        return np.nan
    if isinstance(val, str):
        val = val.strip().replace(",", ".")
        val = re.sub(r'[^\d.-]', '', val)
        try: return float(val)
        except: return np.nan
    return float(val)

def estrai_solo_lettera(val):
    if pd.isna(val) or str(val).strip().lower() in ["nan", "val", ""]:
        return "Standard"
    match = re.search(r'\(([A-Z])\)', str(val))
    if match:
        return f"Rotta {match.group(1)}"
    return str(val)

@st.cache_data
def load_data():
    files = os.listdir(".")
    f_bench = next((f for f in files if "bench" in f.lower() and f.endswith(".csv")), None)
    f_def = next((f for f in files if "default" in f.lower() and f.endswith(".csv")), None)

    if not f_bench or not f_def:
        st.error(f"❌ File non rilevati!")
        st.stop()

    with open(f_def, 'r', encoding='utf-8', errors='ignore') as f:
        line = f.readline()
    sep_def = ';' if ';' in line else ','

    df_b = pd.read_csv(f_bench, sep=";", engine='python', on_bad_lines='skip')
    df_d = pd.read_csv(f_def, sep=sep_def, engine='python', on_bad_lines='skip')

    df_b.columns = df_b.columns.str.strip().str.replace('\n', ' ')
    df_d.columns = df_d.columns.str.strip().str.replace('\n', ' ')

    col_hs_b = next(c for c in df_b.columns if "CN code" in c)
    df_b[col_hs_b] = df_b[col_hs_b].ffill().astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    
    col_hs_d = next(c for c in df_d.columns if "CN Code" in c)
    df_d[col_hs_d] = df_d[col_hs_d].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

    col_paese = next((c for c in df_d.columns if "country" in c.lower()), df_d.columns[0])

    return df_b, df_d, col_hs_b, col_hs_d, col_paese

try:
    bench, defaults, HS_B, HS_D, COL_PAESE = load_data()
except Exception as e:
    st.error(f"Errore: {e}")
    st.stop()

st.title("🛡️ CBAM Professional Calculator")

with st.sidebar:
    st.header("1. Parametri Spedizione")
    anno = st.selectbox("Anno di riferimento", [2026, 2027, 2028, 2029, 2030])
    periodo_req = "(1)" if anno <= 2027 else "(2)"
    
    paese_sel = st.selectbox("Paese di Origine", sorted(defaults[COL_PAESE].unique()))
    hs_sel = st.selectbox("Codice HS Prodotto", sorted(bench[HS_B].unique()))
    
    volume = st.number_input("Volume (Tonnellate)", min_value=0.0, value=1.0)
    reali_input = st.number_input("Emissioni Reali (tCO2e/t)", min_value=0.0, format="%.4f")
    prezzo_ets = st.number_input("Prezzo ETS (€/tCO2)", value=80.0)

# --- LOGICA DI CALCOLO ---

# Benchmark
usare_reali = reali_input > 0
pref = "Column A" if usare_reali else "Column B"
col_bmg_bench = next(c for c in bench.columns if pref in c and "BMg" in c)
col_ind_bench = next(c for c in bench.columns if pref in c and "indicator" in c)

df_hs = bench[bench[HS_B] == hs_sel].copy()
df_valido = df_hs[df_hs[col_ind_bench].apply(lambda x: periodo_req in str(x) or ("(1)" not in str(x) and "(2)" not in str(x)))]

benchmark_val = 0.0
if len(df_valido) > 1:
    mappa_rotte = {estrai_solo_lettera(r[col_ind_bench]): pulisci_numero(r[col_bmg_bench]) for _, r in df_valido.iterrows()}
    scelta = st.selectbox("Seleziona Rotta di Produzione:", list(mappa_rotte.keys()))
    benchmark_val = mappa_rotte[scelta]
else:
    benchmark_val = pulisci_numero(df_valido[col_bmg_bench].iloc[0]) if not df_valido.empty else 0.0

# 2. EMISSIONI (LOGICA GERARCHICA 8-6-4 cifre)
if usare_reali:
    emiss_finali = reali_input
    tipo_info = "Dato Reale"
else:
    col_yr = next(c for c in defaults.columns if str(min(anno, 2028)) in c)
    emiss_finali = np.nan
    tipo_info = "Non trovato"

    # Prova HS intero, poi 6 cifre, poi 4 cifre
    for lung in [8, 6, 4]:
        hs_prefisso = hs_sel[:lung]
        row_p = defaults[(defaults[HS_D].str.startswith(hs_prefisso)) & (defaults[COL_PAESE] == paese_sel)]
        
        if not row_p.empty:
            val = pulisci_numero(row_p[col_yr].iloc[0])
            if not pd.isna(val):
                emiss_finali = val
                tipo_info = f"Default ({paese_sel}) - Match {lung} cifre"
                break
        
        # Se non trovato per il paese, prova "Other Countries" per questo prefisso
        row_o = defaults[(defaults[HS_D].str.startswith(hs_prefisso)) & (defaults[COL_PAESE].str.contains("Other", case=False, na=False))]
        if not row_o.empty:
            val = pulisci_numero(row_o[col_yr].iloc[0])
            if not pd.isna(val):
                emiss_finali = val
                tipo_info = f"Default (Other Countries) - Match {lung} cifre"
                break

    if pd.isna(emiss_finali):
        st.error(f"❌ Impossibile trovare un valore di default per HS {hs_sel} (nemmeno a 4 cifre).")

# --- RISULTATI ---
st.divider()
c1, c2, c3 = st.columns(3)

fa_perc = 97.5 if anno <= 2026 else (95.0 if anno == 2027 else 92.5)
benchmark_val = benchmark_val if not pd.isna(benchmark_val) else 0.0
quota_esente = benchmark_val * (fa_perc / 100)

# Calcolo finale con LaTeX
costo_totale = max(0, (emiss_finali or 0.0) - quota_esente) * volume * prezzo_ets

c1.metric("Emissioni Applicate", f"{emiss_finali:.4f} tCO2/t" if not pd.isna(emiss_finali) else "N/A", tipo_info)
c2.metric("Benchmark Scontato", f"{quota_esente:.4f} tCO2/t", f"Lordo: {benchmark_val:.4f}")
c3.metric("Costo CBAM Totale", f"€ {costo_totale:,.2f}")

with st.expander("Vedi dettagli calcolo"):
    st.write(f"**Formula applicata:**")
    st.latex(r"Cost_{CBAM} = (E_{incorporated} - (BM \times FA\%)) \times Volume \times Price_{ETS}")




















