import streamlit as st
import pandas as pd
import numpy as np
import os
import re

st.set_page_config(page_title="CBAM Professional Calculator", layout="wide")

# --- FUNZIONI DI SUPPORTO ---

def pulisci_numero(val):
    """Converte stringhe con virgole o errori Excel in numeri validi."""
    if pd.isna(val) or str(val).strip() in ["", "#VALUE!", "nan", "NaN"]:
        return np.nan
    if isinstance(val, str):
        val = val.strip().replace(",", ".")
        # Rimuove eventuali caratteri non numerici residui
        val = re.sub(r'[^\d.-]', '', val)
        try:
            return float(val)
        except:
            return np.nan
    return float(val)

@st.cache_data
def load_data():
    """Cerca i file CSV nella cartella e li carica."""
    files = os.listdir(".")
    f_bench = next((f for f in files if "benchmarks" in f.lower() and f.endswith(".csv")), None)
    f_def = next((f for f in files if "defaults" in f.lower() and f.endswith(".csv")), None)

    if not f_bench or not f_def:
        st.error(f"❌ File non trovati! Assicurati di avere i file CSV nella cartella. Rilevati: {files}")
        st.stop()

    # Caricamento Benchmarks (Semicolon)
    df_b = pd.read_csv(f_bench, sep=";", engine='python', on_bad_lines='skip')
    df_b.columns = [c.replace("\n", " ").strip() for c in df_b.columns]
    
    # Caricamento Defaults (Comma)
    df_d = pd.read_csv(f_def, sep=",", engine='python', on_bad_lines='skip')
    df_d.columns = [c.strip() for c in df_d.columns]

    # Pulizia codici HS (gestione celle unite Excel)
    col_hs_b = next(c for c in df_b.columns if "CN code" in c)
    df_b[col_hs_b] = df_b[col_hs_b].ffill().astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    
    col_hs_d = next(c for c in df_d.columns if "CN Code" in c)
    df_d[col_hs_d] = df_d[col_hs_d].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

    return df_b, df_d, col_hs_b, col_hs_d

# --- AVVIO APPLICAZIONE ---

try:
    bench, defaults, HS_B, HS_D = load_data()
except Exception as e:
    st.error(f"Errore critico all'avvio: {e}")
    st.stop()

st.title("🛡️ CBAM Professional Calculator")

# --- SIDEBAR: INPUT UTENTE ---
with st.sidebar:
    st.header("1. Parametri di Calcolo")
    anno = st.selectbox("Anno di riferimento", [2026, 2027, 2028, 2029, 2030])
    periodo_req = "(1)" if anno <= 2027 else "(2)"
    
    paese_origine = st.selectbox("Paese di Origine", sorted(defaults['Country'].unique()))
    codice_hs = st.selectbox("Codice HS Prodotto", sorted(bench[HS_B].unique()))
    
    tonnellate = st.number_input("Volume Importato (Ton)", min_value=0.0, value=1.0, step=0.1)
    reali_input = st.number_input("Emissioni Reali Dirette (tCO2e/t)", 
                                  min_value=0.0, value=0.0, format="%.4f", 
                                  help="Lascia 0 per usare i valori di default")

    st.header("2. Mercato ETS")
    prezzo_ets = st.number_input("Prezzo ETS Medio (€/tCO2)", value=80.0)
    # Calcolo Free Allowance stima
    fa_stima = 97.5 if anno <= 2026 else (95.0 if anno == 2027 else 92.5)
    free_allowance = st.slider("Free Allowance (%)", 0.0, 100.0, fa_stima)

# --- LOGICA DI CALCOLO ---

# Selezione Colonna A (Dati Reali) o B (Default)
usare_reali = reali_input > 0
prefisso = "Column A" if usare_reali else "Column B"

# Identificazione colonne BMg e Indicator per la colonna scelta
col_bmg = next(c for c in bench.columns if prefisso in c and "BMg" in c)
col_ind = next(c for c in bench.columns if prefisso in c and "indicator" in c)

# Filtro Benchmark per HS e Periodo (1) 2026-27 o (2) 2028-30
df_prodotto = bench[bench[HS_B] == codice_hs].copy()

def matches_period(val):
    v = str(val)
    if periodo_req in v: return True
    if "(1)" not in v and "(2)" not in v: return True
    return False

df_valido = df_prodotto[df_prodotto[col_ind].apply(matches_period)]

# Gestione Rotte di Produzione (Scelta C, D, E...)
benchmark_applicato = 0.0
if len(df_valido) > 1:
    st.warning(f"Rotte di produzione multiple rilevate per {codice_hs}")
    mappa_rotte = {}
    for _, r in df_valido.iterrows():
        label = str(r[col_ind]) if pd.notna(r[col_ind]) and str(r[col_ind]).strip() != "" else "Default"
        mappa_rotte[label] = pulisci_numero(r[col_bmg])
    
    scelta_rotta = st.selectbox("Seleziona la Rotta di Produzione (Production Route):", list(mappa_rotte.keys()))
    benchmark_applicato = mappa_rotte[scelta_rotta]
else:
    benchmark_applicato = pulisci_numero(df_valido[col_bmg].iloc[0]) if not df_valido.empty else 0.0

# Calcolo Emissioni Applicate (Default con Fallback)
if usare_reali:
    emissioni_finali = reali_input
    desc_tipo = "Dato Reale fornito"
else:
    # Cerca colonna anno corretta (limite 2028 nei file forniti)
    anno_col = next(c for c in defaults.columns if str(min(anno, 2028)) in c)
    
    # Cerca per Paese + HS
    row_def = defaults[(defaults[HS_D] == codice_hs) & (defaults['Country'] == paese_origine)]
    val_def = pulisci_numero(row_def[anno_col].iloc[0]) if not row_def.empty else np.nan
    
    # Fallback su 'Other Countries' se il valore è vuoto (NaN)
    if pd.isna(val_def):
        row_other = defaults[(defaults[HS_D] == codice_hs) & (defaults['Country'].str.contains("Other", na=False))]
        val_def = pulisci_numero(row_other[anno_col].iloc[0]) if not row_other.empty else 0.0
        desc_tipo = "Default (Other Countries)"
        st.info("Emissioni specifiche non trovate. Utilizzato valore 'Other Countries'.")
    else:
        desc_tipo = f"Default ({paese_origine})"
    
    emissioni_finali = val_def

# --- RISULTATI FINALI ---
st.divider()
c1, c2, c3 = st.columns(3)

# Formula: (Emissioni - (Benchmark * FA%)) * Volume * Prezzo
quota_esente = benchmark_applicato * (free_allowance / 100)
differenza = max(0, emissioni_finali - quota_esente)
costo_totale = differenza * tonnellate * prezzo_ets

c1.metric("Emissioni Applicate", f"{emissioni_finali:.4f} tCO2/t", desc_tipo)
c2.metric("Benchmark (Scontato)", f"{quota_esente:.4f} tCO2/t", f"Lordo: {benchmark_applicato:.4f}")
c3.metric("Costo Totale Stimato", f"€ {costo_totale:,.2f}", f"Su {tonnellate} t")

with st.expander("Vedi dettagli tecnici"):
    desc_merce = df_prodotto['CN Description'].iloc[0] if not df_prodotto.empty else "N/A"
    st.write(f"**Descrizione:** {desc_merce}")
    st.write(f"**Validità Periodo:** {periodo_req}")
    st.write(f"**Calcolo unitario:** `({emissioni_finali:.4f} - {quota_esente:.4f}) = {differenza:.4f} tCO2/t`")




