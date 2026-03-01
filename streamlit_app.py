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
        try: return float(val)
        except: return np.nan
    return float(val)

# --- LETTURA ROBUSTA CSV ---
def robust_read(file_path):
    """Rileva automaticamente se il separatore è , o ; e pulisce le colonne."""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        first_line = f.readline()
    separatore = ';' if ';' in first_line else ','
    df = pd.read_csv(file_path, sep=separatore, engine='python', on_bad_lines='skip')
    # Pulizia nomi colonne da spazi, virgolette e invii a capo
    df.columns = [c.strip().replace('"', '').replace('\n', ' ') for c in df.columns]
    return df

@st.cache_data
def load_data():
    files = os.listdir(".")
    # Cerca i file contenenti parole chiave (case-insensitive)
    f_bench = next((f for f in files if "bench" in f.lower() and f.endswith(".csv")), None)
    f_def = next((f for f in files if "default" in f.lower() and f.endswith(".csv")), None)

    if not f_bench or not f_def:
        st.error(f"❌ File CSV non trovati! Assicurati di caricarli nella cartella. Rilevati: {files}")
        st.stop()

    df_b = robust_read(f_bench)
    df_d = robust_read(f_def)

    # Identificazione colonne HS Code
    col_hs_b = next(c for c in df_b.columns if "CN code" in c)
    df_b[col_hs_b] = df_b[col_hs_b].ffill().astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    
    col_hs_d = next(c for c in df_d.columns if "CN Code" in c)
    df_d[col_hs_d] = df_d[col_hs_d].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

    # Identificazione dinamica colonna Paese
    col_paese = next((c for c in df_d.columns if "country" in c.lower()), df_d.columns[0])

    return df_b, df_d, col_hs_b, col_hs_d, col_paese

# --- ESECUZIONE ---
try:
    bench, defaults, HS_B, HS_D, COL_PAESE = load_data()
except Exception as e:
    st.error(f"Errore inizializzazione: {e}")
    st.stop()

st.title("🛡️ Calcolatore CBAM")

with st.sidebar:
    st.header("1. Parametri")
    anno = st.selectbox("Anno di riferimento", [2026, 2027, 2028, 2029, 2030])
    periodo_req = "(1)" if anno <= 2027 else "(2)"
    
    # Ora la selectbox mostrerà solo i nomi dei paesi puliti
    paese_sel = st.selectbox("Paese di Origine", sorted(defaults[COL_PAESE].unique()))
    hs_sel = st.selectbox("Codice HS Prodotto", sorted(bench[HS_B].unique()))
    
    volume = st.number_input("Volume (Ton)", min_value=0.0, value=1.0)
    reali_input = st.number_input("Emissioni Reali (tCO2e/t)", min_value=0.0, format="%.4f", help="Lascia 0 per i Default")
    prezzo_ets = st.number_input("Prezzo ETS (€/tCO2)", value=80.0)

# --- LOGICA CORE ---

# A. BENCHMARK (Logica Colonna A/B e Rotte C,D,E)
usare_reali = reali_input > 0
pref = "Column A" if usare_reali else "Column B"
c_bmg = next(c for c in bench.columns if pref in c and "BMg" in c)
c_ind = next(c for c in bench.columns if pref in c and "indicator" in c)

df_hs = bench[bench[HS_B] == hs_sel].copy()
# Filtro periodo (1) o (2)
df_valido = df_hs[df_hs[c_ind].apply(lambda x: periodo_req in str(x) or ("(1)" not in str(x) and "(2)" not in str(x)))]

if len(df_valido) > 1:
    rotte = {f"{r[c_ind]} - Val: {r[c_bmg]}": pulisci_numero(r[c_bmg]) for _, r in df_valido.iterrows()}
    scelta = st.selectbox("Seleziona Rotta di Produzione (Indicator)", list(rotte.keys()))
    benchmark_val = rotte[scelta]
else:
    benchmark_val = pulisci_numero(df_valido[c_bmg].iloc[0]) if not df_valido.empty else 0.0

# B. EMISSIONI (Fallback automatico per Armenia e altri)
if usare_reali:
    emiss_finali = reali_input
    tipo_info = "Dato Reale"
else:
    # Identifica colonna anno (2026, 2027, 2028)
    col_yr = next(c for c in defaults.columns if str(min(anno, 2028)) in c)
    
    # Cerca valore paese specifico
    row_p = defaults[(defaults[HS_D] == hs_sel) & (defaults[COL_PAESE] == paese_sel)]
    val_p = pulisci_numero(row_p[col_yr].iloc[0]) if not row_p.empty else np.nan
    
    # Se il valore è vuoto (come per l'Armenia), usa Other Countries
    if pd.isna(val_p) or val_p == 0:
        row_o = defaults[(defaults[HS_D] == hs_sel) & (defaults[COL_PAESE].str.contains("Other", na=False))]
        emiss_finali = pulisci_numero(row_o[col_yr].iloc[0]) if not row_o.empty else 0.0
        tipo_info = "Default (Other Countries)"
        st.warning(f"Dati per {paese_sel} assenti. Utilizzato valore globale.")
    else:
        emiss_finali = val_p
        tipo_info = f"Default ({paese_sel})"

# --- RISULTATI ---
st.divider()
c1, c2, c3 = st.columns(3)

fa_perc = 97.5 if anno <= 2026 else (95.0 if anno == 2027 else 92.5)
quota_esente = benchmark_val * (fa_perc / 100)
costo_tot = max(0, emiss_finali - quota_esente) * volume * prezzo_ets

c1.metric("Emissioni Applicate", f"{emiss_finali:.4f} tCO2/t", tipo_info)
c2.metric("Benchmark Scontato", f"{quota_esente:.4f} tCO2/t", f"Lordo: {benchmark_val:.4f}")
c3.metric("Costo CBAM Totale", f"€ {costo_tot:,.2f}", f"Volume: {volume} t")













