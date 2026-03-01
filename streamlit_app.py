import streamlit as st
import pandas as pd
import numpy as np
import re

# Configurazione Pagina
st.set_page_config(page_title="Calcolatore CBAM", layout="wide")

# Funzione per pulizia numerica (gestisce virgole e errori Excel)
def clean_numeric(val):
    if pd.isna(val) or val == '' or str(val).strip() == '#VALUE!':
        return np.nan
    if isinstance(val, str):
        val = val.strip().replace(',', '.')
        try:
            return float(val)
        except ValueError:
            return np.nan
    return float(val)

@st.cache_data
def load_data():
    # Caricamento Benchmarks (delimitatore ;)
    bench = pd.read_csv("benchmarks final.csv", sep=";")
    bench['CN code'] = bench['CN code'].ffill().astype(str).str.replace(r'\.0$', '', regex=True)
    bench['CN Description'] = bench['CN Description'].ffill()
    
    for col in ['Column A\nBMg [tCO2e/t]', 'Column B\nBMg [tCO2e/t]']:
        bench[col] = bench[col].apply(clean_numeric)
    
    # Caricamento Defaults (delimitatore ,)
    defaults = pd.read_csv("cbam defaults.xlsx - cbam defaults.csv")
    defaults['Product CN Code'] = defaults['Product CN Code'].astype(str).str.replace(r'\.0$', '', regex=True)
    
    val_cols = ['2026 Default Value (Including mark-up)', 
                '2027 Default Value (Including mark-up)', 
                '2028 Default Value (Including mark-up)']
    for col in val_cols:
        defaults[col] = defaults[col].apply(clean_numeric)
        
    return bench, defaults

# Caricamento dati
try:
    bench_df, def_df = load_data()
except Exception as e:
    st.error(f"Errore nel caricamento dei file: {e}. Assicurati che i file siano presenti nella cartella.")
    st.stop()

st.title("🛡️ Calcolatore Emissioni e Costi CBAM")

# --- Sidebar Input ---
st.sidebar.header("Parametri di Input")
anno = st.sidebar.selectbox("Anno di riferimento", [2026, 2027, 2028, 2029, 2030])
periodo_req = "(1)" if anno <= 2027 else "(2)"

paesi = sorted(def_df['Country'].unique())
paese_origine = st.sidebar.selectbox("Paese di Origine", paesi)

codici_hs = sorted(bench_df['CN code'].unique())
hs_code = st.sidebar.selectbox("Codice HS (CN Code)", codici_hs)

volume = st.sidebar.number_input("Volume importato (Ton)", min_value=0.0, value=1.0, step=0.1)
emissioni_reali = st.sidebar.number_input("Emissioni Reali Dirette (tCO2e/t)", 
                                         min_value=0.0, value=0.0, format="%.4f",
                                         help="Lascia 0 se vuoi usare i valori di default per il paese")

prezzo_ets = st.sidebar.number_input("Prezzo Medio ETS (€/tCO2)", min_value=0.0, value=75.0)

# Default Free Allowance (es. 2026 = 97.5%)
fa_default = 97.5 if anno <= 2026 else (95.0 if anno == 2027 else 92.5)
free_allowance_perc = st.sidebar.number_input("Free Allowance (%)", min_value=0.0, max_value=100.0, value=fa_default)

# --- Logica di Calcolo ---

# 1. Determinazione Emissioni e Benchmark da usare
is_real = emissioni_reali > 0
if is_real:
    emissioni_applicate = emissioni_reali
    col_bench = 'Column A\nBMg [tCO2e/t]'
    col_ind = 'Column A\nProduction route indicator'
    tipo_dato = "Reale (Utente)"
else:
    col_bench = 'Column B\nBMg [tCO2e/t]'
    col_ind = 'Column B\nProduction route indicator'
    tipo_dato = "Default (Database)"
    
    # Ricerca valore di default nel database
    col_anno_def = f"{min(anno, 2028)} Default Value (Including mark-up)"
    row_def = def_df[(def_df['Product CN Code'] == hs_code) & (def_df['Country'] == paese_origine)]
    
    val_def = np.nan
    if not row_def.empty:
        val_def = row_def.iloc[0][col_anno_def]
        
    if pd.isna(val_def):
        # Fallback su "Other Countries" se il dato è vuoto o il paese non esiste
        row_other = def_df[(def_df['Product CN Code'] == hs_code) & (def_df['Country'].str.contains("Other", case=False, na=False))]
        if not row_other.empty:
            val_def = row_other.iloc[0][col_anno_def]
            st.warning(f"Dati non trovati per {paese_origine}. Utilizzato valore di default per 'Other Countries'.")
        else:
            val_def = 0.0
            st.error("Nessun dato di default trovato per questo codice HS.")
    
    emissioni_applicate = val_def

# 2. Selezione Benchmark e Rotta di Produzione
filtro_hs = bench_df[bench_df['CN code'] == hs_code]

# Funzione per filtrare per periodo (1) o (2)
def filter_period(row, col):
    ind = str(row[col])
    if periodo_req in ind: return True
    # Se non c'è indicatore di periodo, si assume valido per entrambi
    if "(1)" not in ind and "(2)" not in ind: return True
    return False

opzioni_bench = filtro_hs[filtro_hs.apply(lambda r: filter_period(r, col_ind), axis=1)]

benchmark_val = 0.0
if len(opzioni_bench) > 1:
    st.info(f"Sono presenti più rotte di produzione per il codice {hs_code}. Seleziona quella corretta:")
    rotte_disponibili = []
    for idx, row in opzioni_bench.iterrows():
        ind = str(row[col_ind])
        # Estrae la lettera della rotta (C, D, E...)
        match = re.search(r'\(([A-Z])\)', ind)
        label = match.group(0) if match else f"Opzione {idx}"
        rotte_disponibili.append((label, row[col_bench]))
    
    rotta_scelta = st.selectbox("Rotta di Produzione (Production Route)", [r[0] for r in rotte_disponibili])
    benchmark_val = next(r[1] for r in rotte_disponibili if r[0] == rotta_scelta)
elif not opzioni_bench.empty:
    benchmark_val = opzioni_bench.iloc[0][col_bench]
else:
    st.error("Benchmark non trovato per questo codice HS.")

# --- Calcoli Finali ---
free_allowance_factor = free_allowance_perc / 100.0
# Formula: (Emissioni - (Benchmark * FA)) * Volume * Prezzo
emissioni_soggette = max(0, emissioni_applicate - (benchmark_val * free_allowance_factor))
costo_totale = emissioni_soggette * volume * prezzo_ets

# --- Visualizzazione Risultati ---
st.divider()
col1, col2, col3 = st.columns(3)
col1.metric("Emissioni Applicate", f"{emissioni_applicate:.4f} tCO2/t", f"Tipo: {tipo_dato}")
col2.metric("Benchmark di Riferimento", f"{benchmark_val:.4f} tCO2/t", f"Periodo: {periodo_req}")
col3.metric("Costo CBAM Totale", f"€ {costo_totale:,.2f}", f"Volume: {volume} Ton")

st.divider()
st.subheader("Dettagli del Prodotto")
desc_prodotto = filtro_hs['CN Description'].iloc[0] if not filtro_hs.empty else "N/A"
st.write(f"**Descrizione:** {desc_prodotto}")

with st.expander("Vedi formula e dettagli tecnici"):
    st.write(f"Formula applicata: `(Emissioni - (Benchmark * Free Allowance)) * Volume * Prezzo ETS` ")
    st.write(f"- Emissioni: {emissioni_applicate:.4f}")
    st.write(f"- Benchmark: {benchmark_val:.4f}")
    st.write(f"- Free Allowance Factor: {free_allowance_factor:.4f}")
    st.write(f"- Prezzo ETS: € {prezzo_ets}")
    st.write(f"- Risultato unitario soggetto a tassazione: {emissioni_soggette:.4f} tCO2/t")



