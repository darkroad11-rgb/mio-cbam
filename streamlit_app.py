import streamlit as st
import pandas as pd
import numpy as np
import os
import re

st.set_page_config(page_title="CBAM Professional Calculator", layout="wide")

# --- FUNZIONE PULIZIA NUMERI ---
def pulisci_numero(val):
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

# --- CARICAMENTO DINAMICO DEI FILE ---
@st.cache_data
def load_data():
    files = os.listdir(".")
    # Cerca i file contenenti parole chiave per evitare errori di nome esatto
    f_bench = next((f for f in files if "bench" in f.lower() and f.endswith(".csv")), None)
    f_def = next((f for f in files if "default" in f.lower() and f.endswith(".csv")), None)

    if not f_bench or not f_def:
        st.error(f"❌ File non trovati! Assicurati di aver caricato i file CSV. File rilevati nella cartella: {files}")
        st.stop()

    # Caricamento Benchmarks (Semicolon ;)
    df_b = pd.read_csv(f_bench, sep=";", engine='python', on_bad_lines='skip')
    df_b.columns = df_b.columns.str.strip() # Pulisce spazi dai nomi colonne
    
    # Caricamento Defaults (Comma ,)
    df_d = pd.read_csv(f_def, sep=",", engine='python', on_bad_lines='skip')
    df_d.columns = df_d.columns.str.strip()

    # Pulizia HS Code (ffill per celle unite e rimozione .0)
    col_hs_b = next(c for c in df_b.columns if "CN code" in c)
    df_b[col_hs_b] = df_b[col_hs_b].ffill().astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    
    col_hs_d = next(c for c in df_d.columns if "CN Code" in c)
    df_d[col_hs_d] = df_d[col_hs_d].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

    # Identificazione sicura colonna Paese
    col_paese = next((c for c in df_d.columns if "country" in c.lower()), df_d.columns[0])

    return df_b, df_d, col_hs_b, col_hs_d, col_paese

# --- ESECUZIONE CARICAMENTO ---
try:
    bench, defaults, HS_B, HS_D, COL_PAESE = load_data()
except Exception as e:
    st.error(f"Errore critico: {e}")
    st.stop()

st.title("🛡️ CBAM Professional Calculator")

with st.sidebar:
    st.header("1. Parametri di Calcolo")
    anno = st.selectbox("Anno di riferimento", [2026, 2027, 2028, 2029, 2030])
    periodo_req = "(1)" if anno <= 2027 else "(2)"
    
    # Lista paesi pulita
    paesi_lista = sorted(defaults[COL_PAESE].unique())
    paese_sel = st.selectbox("Paese di Origine", paesi_lista)
    
    hs_lista = sorted(bench[HS_B].unique())
    hs_sel = st.selectbox("Codice HS", hs_lista)
    
    volume = st.number_input("Volume (Ton)", min_value=0.0, value=1.0)
    reali = st.number_input("Emissioni Reali (tCO2e/t)", min_value=0.0, format="%.4f", help="Se 0, usa i Default")
    prezzo_ets = st.number_input("Prezzo ETS (€/tCO2)", value=80.0)

# --- LOGICA CALCOLO ---
usare_reali = reali > 0
prefisso = "Column A" if usare_reali else "Column B"
col_bmg = next(c for c in bench.columns if prefisso in c and "BMg" in c)
col_ind = next(c for c in bench.columns if prefisso in c and "indicator" in c)

# 1. DETERMINAZIONE EMISSIONI (Paese vs Fallback Other Countries)
if usare_reali:
    emissioni_finali = reali
    info_origine = "Dato Reale inserito"
else:
    # Identifica colonna anno corretta (es. 2026, 2027, 2028)
    col_anno_def = next(c for c in defaults.columns if str(min(anno, 2028)) in c)
    
    # Cerca riga per il paese scelto
    row_paese = defaults[(defaults[HS_D] == hs_sel) & (defaults[COL_PAESE] == paese_sel)]
    val_default = pulisci_numero(row_paese[col_anno_def].iloc[0]) if not row_paese.empty else np.nan
    
    # LOGICA FALLBACK: Se Armenia (o altro) ha valori vuoti, usa "Other Countries"
    if pd.isna(val_default):
        row_other = defaults[(defaults[HS_D] == hs_sel) & (defaults[COL_PAESE].str.contains("Other", na=False))]
        val_default = pulisci_numero(row_other[col_anno_def].iloc[0]) if not row_other.empty else 0.0
        info_origine = "Default (Other Countries - Fallback)"
        st.warning(f"Dati per {paese_sel} non trovati per l'anno {anno}. Utilizzato valore globale 'Other Countries'.")
    else:
        info_origine = f"Default ({paese_sel})"
    
    emissioni_finali = val_default

# 2. SELEZIONE BENCHMARK E ROTTA
df_hs = bench[bench[HS_B] == hs_sel].copy()

def filter_p(val):
    v = str(val)
    if periodo_req in v: return True
    if "(1)" not in v and "(2)" not in v: return True
    return False

df_valido = df_hs[df_hs[col_ind].apply(filter_p)]

if len(df_valido) > 1:
    st.info("ℹ️ Multiple Production Routes rilevate.")
    rotte = {f"{r[col_ind]} - Val: {r[col_bmg]}": r[col_bmg] for _, r in df_valido.iterrows()}
    scelta = st.selectbox("Seleziona Rotta di Produzione", list(rotte.keys()))
    benchmark_val = rotte[scelta]
else:
    benchmark_val = pulisci_numero(df_valido[col_bmg].iloc[0]) if not df_valido.empty else 0.0

# --- RISULTATI ---
st.divider()
c1, c2, c3 = st.columns(3)

# Calcolo economico
fa_perc = 97.5 if anno <= 2026 else (95.0 if anno == 2027 else 92.5)
quota_esente = benchmark_val * (fa_perc / 100)
costo_totale = max(0, emissioni_finali - quota_esente) * volume * prezzo_ets

c1.metric("Emissioni Applicate", f"{emissioni_finali:.4f} tCO2/t", info_origine)
c2.metric("Benchmark Scontato", f"{quota_esente:.4f} tCO2/t", f"Lordo: {benchmark_val:.4f}")
c3.metric("Costo CBAM Totale", f"€ {costo_totale:,.2f}")

with st.expander("Vedi dettagli tecnici"):
    desc_merce = df_hs['CN Description'].iloc[0] if not df_hs.empty else "N/A"
    st.write(f"**Prodotto:** {desc_merce}")
    st.write(f"**Periodo Benchmark:** {periodo_req}")
    st.write(f"**Formula:** `({emissioni_finali:.4f} - {quota_esente:.4f}) * {volume} * {prezzo_ets}`")











