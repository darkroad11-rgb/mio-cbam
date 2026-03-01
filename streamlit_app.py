import streamlit as st
import pandas as pd
import numpy as np
import os
import re

# Impostazione layout
st.set_page_config(page_title="CBAM Calculator Suite", layout="wide")

# --- FUNZIONI DI UTILITÀ ---
def pulisci_numero(val):
    """Pulisce i valori numerici dai file CSV (gestisce virgole e errori Excel)"""
    if pd.isna(val) or str(val).strip() in ["", "#VALUE!", "nan"]:
        return np.nan
    if isinstance(val, str):
        val = val.strip().replace(",", ".")
        val = re.sub(r'[^\d.-]', '', val)
        try:
            return float(val)
        except:
            return np.nan
    return float(val)

@st.cache_data
def carica_database():
    """Carica e pulisce i database caricati"""
    f_bench = "benchmarks final.csv"
    f_defaults = "cbam defaults.xlsx - cbam defaults.csv"

    if not os.path.exists(f_bench) or not os.path.exists(f_defaults):
        st.error("⚠️ File CSV non trovati. Assicurati che 'benchmarks final.csv' e 'cbam defaults.xlsx - cbam defaults.csv' siano nella cartella.")
        st.stop()

    # Lettura Benchmarks (separatore ;)
    df_b = pd.read_csv(f_bench, sep=";", engine='python', on_bad_lines='skip')
    df_b.columns = [c.replace("\n", " ").strip() for c in df_b.columns]
    
    # Lettura Defaults (separatore ,)
    df_d = pd.read_csv(f_defaults, sep=",", engine='python', on_bad_lines='skip')
    df_d.columns = [c.strip() for c in df_d.columns]

    # Pulizia codici HS (trasformazione in stringa e ffill per celle unite)
    col_hs_b = [c for c in df_b.columns if "CN code" in c][0]
    df_b[col_hs_b] = df_b[col_hs_b].ffill().astype(str).str.replace(r'\.0$', '', regex=True)
    
    col_hs_d = [c for c in df_d.columns if "CN Code" in c][0]
    df_d[col_hs_d] = df_d[col_hs_d].astype(str).str.replace(r'\.0$', '', regex=True)

    # Pulizia colonne numeriche
    cols_bmg = [c for c in df_b.columns if "BMg" in c]
    for c in cols_bmg:
        df_b[c] = df_b[c].apply(pulisci_numero)

    cols_def = [c for c in df_d.columns if "Default Value" in c]
    for c in cols_def:
        df_d[c] = df_d[c].apply(pulisci_numero)

    return df_b, df_d, col_hs_b, col_hs_d

# --- CARICAMENTO DATI ---
try:
    bench, defaults, HS_B, HS_D = carica_database()
except Exception as e:
    st.error(f"Errore tecnico nel caricamento: {e}")
    st.stop()

# --- INTERFACCIA ---
st.title("📊 Calcolatore Emissioni CBAM")

with st.sidebar:
    st.header("1. Parametri Spedizione")
    anno = st.selectbox("Anno di riferimento", [2026, 2027, 2028, 2029, 2030])
    periodo_req = "(1)" if anno <= 2027 else "(2)"
    
    paese_input = st.selectbox("Paese di Origine", sorted(defaults['Country'].unique()))
    hs_input = st.selectbox("Codice HS Prodotto", sorted(bench[HS_B].unique()))
    
    tonnellate = st.number_input("Volume (Tonnellate)", min_value=0.0, value=1.0, step=0.1)
    emissioni_reali = st.number_input("Emissioni Reali Dirette (tCO2e/t)", 
                                      help="Inserisci 0 se vuoi usare i valori di default",
                                      min_value=0.0, format="%.4f")
    
    st.header("2. Costi e Agevolazioni")
    prezzo_ets = st.number_input("Prezzo Certificato CBAM (€/tCO2)", value=75.0)
    fa_stima = 97.5 if anno <= 2026 else (95.0 if anno == 2027 else 92.5)
    free_allowance = st.slider("Free Allowance (%)", 0.0, 100.0, fa_stima)

# --- LOGICA DI CALCOLO ---
usare_reali = emissioni_reali > 0

# A. Selezione Colonne Benchmark (Colonna A se reali, Colonna B se default)
etichetta_col = "Column A" if usare_reali else "Column B"
col_val = [c for c in bench.columns if etichetta_col in c and "BMg" in c][0]
col_ind = [c for c in bench.columns if etichetta_col in c and "indicator" in c][0]

# B. Filtro Benchmark per HS e Periodo (1) 2026-27 o (2) 2028-30
df_prodotto = bench[bench[HS_B] == hs_input].copy()

def filtro_periodo(val):
    v = str(val)
    if periodo_req in v: return True
    if "(1)" not in v and "(2)" not in v: return True
    return False

df_valido = df_prodotto[df_prodotto[col_ind].apply(filtro_periodo)]

# C. Gestione Production Route (Scelta della lettera C, D, E...)
benchmark_base = 0.0
if len(df_valido) > 1:
    st.info(f"🔎 Più rotte di produzione (Production Routes) trovate per {hs_input}.")
    opzioni = {}
    for _, r in df_valido.iterrows():
        # Crea etichetta per la selectbox (es: "(C) (1)")
        txt = str(r[col_ind]) if pd.notna(r[col_ind]) else "Default"
        opzioni[txt] = r[col_val]
    
    rotta_scelta = st.selectbox("Seleziona la Rotta di Produzione corretta:", list(opzioni.keys()))
    benchmark_base = opzioni[rotta_scelta]
else:
    benchmark_base = df_valido[col_val].iloc[0] if not df_valido.empty else 0.0

# D. Calcolo Emissioni Applicate (Gestione Fallback su Other Countries)
if usare_reali:
    emissioni_calc = emissioni_reali
    tipo_calcolo = "Dato Reale (Colonna A)"
else:
    tipo_calcolo = "Dato Default (Colonna B)"
    # Identifica colonna per anno (2026, 2027, 2028)
    col_anno_def = [c for c in defaults.columns if str(min(anno, 2028)) in c][0]
    
    # Cerca valore per Paese + HS
    riga_def = defaults[(defaults[HS_D] == hs_input) & (defaults['Country'] == paese_input)]
    val_def = pulisci_numero(riga_def[col_anno_def].iloc[0]) if not riga_def.empty else np.nan
    
    # SE VUOTO -> Fallback su 'Other Countries and Territories'
    if pd.isna(val_def):
        riga_alt = defaults[(defaults[HS_D] == hs_input) & (defaults['Country'].str.contains("Other", na=False))]
        val_def = pulisci_numero(riga_alt[col_anno_def].iloc[0]) if not riga_alt.empty else 0.0
        st.warning(f"⚠️ Valore non trovato per {paese_input}. Utilizzato default 'Other Countries'.")
    
    emissioni_calc = val_def

# --- CALCOLO FINALE ---
# Formula: (Emissioni - (Benchmark * Free Allowance %)) * Volume * Prezzo ETS
quota_franca = benchmark_base * (free_allowance / 100)
emissioni_soggette = max(0, emissioni_calc - quota_franca)
costo_totale = emissioni_soggette * tonnellate * prezzo_ets

# --- DISPLAY ---
st.divider()
c1, c2, c3 = st.columns(3)

c1.metric("Emissioni Applicate", f"{emissioni_calc:.4f} tCO2/t", f"Fonte: {tipo_calcolo}")
c2.metric("Benchmark di Riferimento", f"{benchmark_base:.4f} tCO2/t", f"Periodo: {periodo_req}")
c3.metric("Costo Totale Stimato", f"€ {costo_totale:,.2f}", f"Spedizione: {tonnellate}t")

# Tabella Dettaglio
with st.expander("Vedi dettagli tecnici del calcolo"):
    st.write(f"**Descrizione Prodotto:** {df_prodotto['CN Description'].iloc[0] if not df_prodotto.empty else 'N/A'}")
    st.write(f"**Soglia Esente (Benchmark * FA):** {quota_franca:.4f} tCO2/t")
    st.write(f"**Formula:** `({emissioni_calc:.4f} - {quota_franca:.4f}) * {tonnellate} * {prezzo_ets}`")







