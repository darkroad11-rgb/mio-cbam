import streamlit as st
import pandas as pd
import numpy as np
import os
import re

st.set_page_config(page_title="CBAM Pro Calculator", layout="wide")

# --- FUNZIONI DI PULIZIA ---

def pulisci_numero(val):
    """Trasforma stringhe sporche in numeri, gestendo #VALUE! e celle vuote."""
    if pd.isna(val) or str(val).strip() in ["", "#VALUE!", "nan", "NaN"]:
        return np.nan
    if isinstance(val, str):
        val = val.strip().replace(",", ".")
        val = re.sub(r'[^\d.-]', '', val)
        try: return float(val)
        except: return np.nan
    return float(val)

def estrai_solo_lettera(val):
    """Mostra solo la lettera della rotta (C, D, E)."""
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
        st.error(f"❌ File non rilevati! Assicurati di caricarli nella cartella.")
        st.stop()

    # Rilevamento separatore
    with open(f_def, 'r', encoding='utf-8', errors='ignore') as f:
        line = f.readline()
    sep_def = ';' if ';' in line else ','

    df_b = pd.read_csv(f_bench, sep=";", engine='python', on_bad_lines='skip')
    df_d = pd.read_csv(f_def, sep=sep_def, engine='python', on_bad_lines='skip')

    # Pulizia totale nomi colonne
    df_b.columns = df_b.columns.str.strip().str.replace('\n', ' ')
    df_d.columns = df_d.columns.str.strip().str.replace('\n', ' ')

    # Pulizia codici HS (fondamentale per il match)
    col_hs_b = next(c for c in df_b.columns if "CN code" in c)
    df_b[col_hs_b] = df_b[col_hs_b].ffill().astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    
    col_hs_d = next(c for c in df_d.columns if "CN Code" in c)
    df_d[col_hs_d] = df_d[col_hs_d].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

    # Identificazione Paese
    col_paese = next((c for c in df_d.columns if "country" in c.lower()), df_d.columns[0])

    return df_b, df_d, col_hs_b, col_hs_d, col_paese

# --- CARICAMENTO ---
try:
    bench, defaults, HS_B, HS_D, COL_PAESE = load_data()
except Exception as e:
    st.error(f"Errore nel caricamento: {e}")
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

# Selezione Benchmark (Colonna A/B)
usare_reali = reali_input > 0
pref = "Column A" if usare_reali else "Column B"
col_bmg_bench = next(c for c in bench.columns if pref in c and "BMg" in c)
col_ind_bench = next(c for c in bench.columns if pref in c and "indicator" in c)

df_hs = bench[bench[HS_B] == hs_sel].copy()
df_valido = df_hs[df_hs[col_ind_bench].apply(lambda x: periodo_req in str(x) or ("(1)" not in str(x) and "(2)" not in str(x)))]

# 1. SCELTA ROTTA (Solo Lettere)
benchmark_val = 0.0
if len(df_valido) > 1:
    mappa_rotte = {}
    for _, r in df_valido.iterrows():
        label = estrai_solo_lettera(r[col_ind_bench])
        mappa_rotte[label] = pulisci_numero(r[col_bmg_bench])
    
    scelta = st.selectbox("Seleziona Rotta di Produzione:", list(mappa_rotte.keys()))
    benchmark_val = mappa_rotte[scelta]
else:
    benchmark_val = pulisci_numero(df_valido[col_bmg_bench].iloc[0]) if not df_valido.empty else 0.0

# 2. EMISSIONI (LOGICA FALLBACK ROBUSTA)
if usare_reali:
    emiss_finali = reali_input
    tipo_info = "Dato Reale"
else:
    col_yr = next(c for c in defaults.columns if str(min(anno, 2028)) in c)
    
    # Ricerca per Paese specifico
    row_p = defaults[(defaults[HS_D] == hs_sel) & (defaults[COL_PAESE] == paese_sel)]
    
    # Estraiamo il valore e puliamolo
    val_p = np.nan
    if not row_p.empty:
        val_p = pulisci_numero(row_p[col_yr].iloc[0])

    # Se il valore è NaN (vuoto), cerchiamo "Other Countries"
    if pd.isna(val_p):
        # Cerchiamo la riga che contiene "Other" nel nome del paese per lo stesso HS
        row_o = defaults[(defaults[HS_D] == hs_sel) & (defaults[COL_PAESE].str.contains("Other", case=False, na=False))]
        
        if not row_o.empty:
            emiss_finali = pulisci_numero(row_o[col_yr].iloc[0])
            tipo_info = "Default (Fallback: Other Countries)"
            st.warning(f"⚠️ Dati specifici per {paese_sel} assenti. Utilizzato valore globale 'Other Countries'.")
        else:
            emiss_finali = 0.0
            tipo_info = "Dato non trovato"
            st.error(f"❌ Errore: Nessun valore trovato nemmeno in 'Other Countries' per HS {hs_sel}.")
    else:
        emiss_finali = val_p
        tipo_info = f"Default ({paese_sel})"

# --- RISULTATI ---
st.divider()
c1, c2, c3 = st.columns(3)

# Calcolo economico
fa_perc = 97.5 if anno <= 2026 else (95.0 if anno == 2027 else 92.5)
benchmark_val = benchmark_val if not pd.isna(benchmark_val) else 0.0
quota_esente = benchmark_val * (fa_perc / 100)
costo_totale = max(0, (emiss_finali or 0.0) - quota_esente) * volume * prezzo_ets

c1.metric("Emissioni Applicate", f"{emiss_finali:.4f} tCO2/t", tipo_info)
c2.metric("Benchmark Scontato", f"{quota_esente:.4f} tCO2/t", f"Lordo: {benchmark_val:.4f}")
c3.metric("Costo CBAM Totale", f"€ {costo_totale:,.2f}")

with st.expander("Vedi dettagli calcolo"):
    st.write(f"**HS Code:** {hs_sel} | **Paese:** {paese_sel}")
    st.write(f"**Formula:** `({emiss_finali:.4f} - {quota_esente:.4f}) * {volume} * {prezzo_ets}`")


















