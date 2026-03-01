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

# --- FUNZIONE CARICAMENTO DATI ---
@st.cache_data
def load_data():
    files = os.listdir(".")
    f_bench = next((f for f in files if "benchmarks" in f.lower() and f.endswith(".csv")), None)
    f_def = next((f for f in files if "defaults" in f.lower() and f.endswith(".csv")), None)

    if not f_bench or not f_def:
        st.error(f"❌ File CSV non trovati nella cartella. Rilevati: {files}")
        st.stop()

    # Leggi Benchmark (delimitatore ;)
    df_b = pd.read_csv(f_bench, sep=";", engine='python', on_bad_lines='skip')
    df_b.columns = [c.strip().replace('"', '') for c in df_b.columns] 

    # Leggi Defaults (delimitatore ,)
    df_d = pd.read_csv(f_def, sep=",", engine='python', on_bad_lines='skip')
    df_d.columns = [c.strip().replace('"', '') for c in df_d.columns]

    # Normalizzazione Codici HS e ffill per celle unite
    col_hs_b = next(c for c in df_b.columns if "CN code" in c)
    df_b[col_hs_b] = df_b[col_hs_b].ffill().astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    
    col_hs_d = next(c for c in df_d.columns if "CN Code" in c)
    df_d[col_hs_d] = df_d[col_hs_d].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

    # Identificazione dinamica colonna Paese
    col_paese = next((c for c in df_d.columns if "country" in c.lower()), df_d.columns[0])
    
    return df_b, df_d, col_hs_b, col_hs_d, col_paese

# --- ESECUZIONE CARICAMENTO ---
try:
    bench, defaults, HS_B, HS_D, COL_PAESE = load_data()
except Exception as e:
    st.error(f"Errore nell'inizializzazione dei dati: {e}")
    st.stop()

st.title("🛡️ Calcolatore CBAM - Modulo Professionale")

# --- SIDEBAR: INPUT ---
with st.sidebar:
    st.header("1. Configurazione")
    anno = st.selectbox("Anno di riferimento", [2026, 2027, 2028, 2029, 2030])
    periodo_req = "(1)" if anno <= 2027 else "(2)"
    
    paese_origine = st.selectbox("Paese di Origine", sorted(defaults[COL_PAESE].unique()))
    codice_hs = st.selectbox("Codice HS Prodotto", sorted(bench[HS_B].unique()))
    
    volume = st.number_input("Volume Importato (Ton)", min_value=0.0, value=1.0, step=0.1)
    reali_input = st.number_input("Emissioni Reali Dirette (tCO2e/t)", 
                                  min_value=0.0, value=0.0, format="%.4f", 
                                  help="Lascia 0 per usare i Default")

    st.header("2. Mercato ETS")
    prezzo_ets = st.number_input("Prezzo ETS (€/tCO2)", value=80.0)
    fa_stima = 97.5 if anno <= 2026 else (95.0 if anno == 2027 else 92.5)
    free_allowance = st.slider("Free Allowance (%)", 0.0, 100.0, fa_stima)

# --- LOGICA CALCOLO BENCHMARK ---
usare_reali = reali_input > 0
prefisso = "Column A" if usare_reali else "Column B"

col_bmg_bench = next(c for c in bench.columns if prefisso in c and "BMg" in c)
col_ind_bench = next(c for c in bench.columns if prefisso in c and "indicator" in c)

df_hs = bench[bench[HS_B] == codice_hs].copy()

def matches_period(val):
    v = str(val)
    if periodo_req in v: return True
    if "(1)" not in v and "(2)" not in v: return True
    return False

df_valido = df_hs[df_hs[col_ind_bench].apply(matches_period)]

benchmark_finale = 0.0
if len(df_valido) > 1:
    st.info(f"🔎 Seleziona la Rotta di Produzione per il codice {codice_hs}:")
    mappa_rotte = {}
    for _, r in df_valido.iterrows():
        label = str(r[col_ind_bench]) if pd.notna(r[col_ind_bench]) and str(r[col_ind_bench]).strip() != "" else "Standard"
        mappa_rotte[label] = pulisci_numero(r[col_bmg_bench])
    
    scelta_rotta = st.selectbox("Rotta (Production Route)", list(mappa_rotte.keys()))
    benchmark_finale = mappa_rotte[scelta_rotta]
else:
    benchmark_finale = pulisci_numero(df_valido[col_bmg_bench].iloc[0]) if not df_valido.empty else 0.0

# --- LOGICA CALCOLO EMISSIONI (Fallback Countries) ---
if usare_reali:
    emissioni_finali = reali_input
    tipo_e = "Dato Reale fornito"
else:
    # Identifica colonna anno (2026, 2027, 2028)
    col_def_anno = next((c for c in defaults.columns if str(min(anno, 2028)) in c), None)
    
    # Cerca riga specifica per Paese
    row_paese = defaults[(defaults[HS_D] == codice_hs) & (defaults[COL_PAESE] == paese_origine)]
    val_default = pulisci_numero(row_paese[col_def_anno].iloc[0]) if not row_paese.empty else np.nan
    
    # LOGICA FALLBACK: Se il valore è vuoto (NaN), cerca "Other Countries"
    if pd.isna(val_default):
        row_other = defaults[(defaults[HS_D] == codice_hs) & (defaults[COL_PAESE].str.contains("Other", na=False))]
        if not row_other.empty:
            val_default = pulisci_numero(row_other[col_def_anno].iloc[0])
            st.warning(f"⚠️ Dati per {paese_origine} assenti nel database. Utilizzato valore globale 'Other Countries'.")
            tipo_e = "Default (Other Countries)"
        else:
            val_default = 0.0
            tipo_e = "Nessun dato trovato"
    else:
        tipo_e = f"Default ({paese_origine})"
    
    emissioni_finali = val_default

# --- RISULTATI ---
st.divider()
c1, c2, c3 = st.columns(3)

# Calcolo formula CBAM
quota_esente = benchmark_finale * (free_allowance / 100)
eccesso = max(0, emissioni_finali - quota_esente)
costo_totale = eccesso * volume * prezzo_ets

c1.metric("Emissioni Applicate", f"{emissioni_finali:.4f} tCO2/t", tipo_e)
c2.metric("Benchmark (Scontato FA)", f"{quota_esente:.4f} tCO2/t", f"Lordo: {benchmark_finale:.4f}")
c3.metric("Costo CBAM Stimato", f"€ {costo_totale:,.2f}", f"Volume: {volume} t")

with st.expander("Vedi dettagli tecnici"):
    desc_merce = df_hs['CN Description'].iloc[0] if not df_hs.empty else "N/A"
    st.write(f"**Descrizione:** {desc_merce}")
    st.write(f"**Validità Periodo:** {periodo_req}")
    st.write(f"**Formula:** `({emissioni_finali:.4f} - {quota_esente:.4f}) * {volume} * {prezzo_ets}`")









