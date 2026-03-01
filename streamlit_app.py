import streamlit as st
import pandas as pd
import numpy as np

# Configurazione Pagina
st.set_page_config(page_title="Calcolatore CBAM", layout="wide")

# Funzione per pulizia numerica
def clean_numeric(val):
    if pd.isna(val) or val == '' or val == '#VALUE!':
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
    # Caricamento Benchmarks
    bench = pd.read_csv("benchmarks final.csv", sep=";")
    bench['CN code'] = bench['CN code'].ffill().astype(str).str.replace('.0', '', regex=False)
    bench['CN Description'] = bench['CN Description'].ffill()
    
    for col in ['Column A\nBMg [tCO2e/t]', 'Column B\nBMg [tCO2e/t]']:
        bench[col] = bench[col].apply(clean_numeric)
    
    # Caricamento Defaults
    defaults = pd.read_csv("cbam defaults.xlsx - cbam defaults.csv")
    defaults['Product CN Code'] = defaults['Product CN Code'].astype(str).str.replace('.0', '', regex=False)
    
    val_cols = ['2026 Default Value (Including mark-up)', 
                '2027 Default Value (Including mark-up)', 
                '2028 Default Value (Including mark-up)']
    for col in val_cols:
        defaults[col] = defaults[col].apply(clean_numeric)
        
    return bench, defaults

bench_df, def_df = load_data()

st.title("🛡️ Calcolatore Emissioni CBAM")

# --- Sidebar Input ---
st.sidebar.header("Parametri di Input")
anno = st.sidebar.selectbox("Anno di riferimento", [2026, 2027, 2028, 2029, 2030])
periodo = "(1)" if anno <= 2027 else "(2)"

paesi = sorted(def_df['Country'].unique())
paese_origine = st.sidebar.selectbox("Paese di Origine", paesi)

codici_hs = sorted(bench_df['CN code'].unique())
hs_code = st.sidebar.selectbox("Codice HS (CN Code)", codici_hs)

volume = st.sidebar.number_input("Volume importato (Ton)", min_value=0.0, value=1.0, step=0.1)
emissioni_reali = st.sidebar.number_input("Emissioni Reali Dirette (tCO2e/t)", min_value=0.0, value=0.0, format="%.4f")

prezzo_ets = st.sidebar.number_input("Prezzo Medio ETS (€/tCO2)", min_value=0.0, value=75.0)
# Default Free Allowance (es. 2026 = 97.5%)
fa_default = 97.5 if anno <= 2026 else (95.0 if anno == 2027 else 92.5)
free_allowance_perc = st.sidebar.number_input("Free Allowance (%)", min_value=0.0, max_value=100.0, value=fa_default)

# --- Logica di Calcolo ---

# 1. Determinazione Emissioni da usare
is_real = emissioni_reali > 0
if is_real:
    emissioni_finali = emissioni_reali
    tipo_dato = "Reale"
    col_bench = 'Column A\nBMg [tCO2e/t]'
    col_ind = 'Column A\nProduction route indicator'
else:
    tipo_dato = "Default"
    col_bench = 'Column B\nBMg [tCO2e/t]'
    col_ind = 'Column B\nProduction route indicator'
    
    # Ricerca valore di default
    default_year_col = f"{min(anno, 2028)} Default Value (Including mark-up)"
    row_def = def_df[(def_df['Product CN Code'] == hs_code) & (def_df['Country'] == paese_origine)]
    
    val_def = np.nan
    if not row_def.empty:
        val_def = row_def.iloc[0][default_year_col]
        
    if pd.isna(val_def):
        # Fallback su "Other Countries"
        row_other = def_df[(def_df['Product CN Code'] == hs_code) & (def_df['Country'].str.contains("Other", na=False))]
        if not row_other.empty:
            val_def = row_other.iloc[0][default_year_col]
            st.info(f"Valore per {paese_origine} non trovato. Utilizzato valore 'Other Countries'.")
    
    emissioni_finali = val_def if not pd.isna(val_def) else 0.0

# 2. Selezione Benchmark e Rotta
filtro_hs = bench_df[bench_df['CN code'] == hs_code]

# Filtriamo per periodo (1) o (2) se presente nell'indicatore
# Nota: se l'indicatore è (F)(1), cerchiamo la stringa "(1)"
def filter_period(row, col):
    ind = str(row[col])
    if periodo in ind: return True
    if "(1)" not in ind and "(2)" not in ind: return True # Se non ha periodo, vale per tutti
    return False

opzioni_bench = filtro_hs[filtro_hs.apply(lambda r: filter_period(r, col_ind), axis=1)]

# Gestione Rotte di Produzione (C, D, E...)
rotta_selezionata = None
if len(opzioni_bench) > 1:
    rotte = []
    for idx, row in opzioni_bench.iterrows():
        ind = str(row[col_ind])
        # Estraiamo la lettera tra parentesi se esiste
        import re
        match = re.search(r'\(([A-Z])\)', ind)
        lettera = match.group(1) if match else f"Opzione {idx}"
        rotte.append(lettera)
    
    rotta_scelta = st.selectbox("Seleziona Rotta di Produzione (Production Route)", rotte)
    # Troviamo la riga corrispondente
    idx_scelta = rotte.index(rotta_scelta)
    benchmark_val = opzioni_bench.iloc[idx_scelta][col_bench]
else:
    benchmark_val = opzioni_bench[col_bench].iloc[0] if not opzioni_bench.empty else 0.0

# --- Calcoli Finali ---
free_allowance_factor = free_allowance_perc / 100.0
# Formula: (Emissioni - (Benchmark * FA)) * Prezzo
tco2_soggette = max(0, emissioni_finali - (benchmark_val * free_allowance_factor))
costo_unitario = tco2_soggette * prezzo_ets
costo_totale = costo_unitario * volume

# --- Visualizzazione Risultati ---
col1, col2, col3 = st.columns(3)
col1.metric("Emissioni Applicate", f"{emissioni_finali:.4f} tCO2/t", f"Tipo: {tipo_dato}")
col2.metric("Benchmark", f"{benchmark_val:.4f} tCO2/t")
col3.metric("Costo Totale Stimato", f"€ {costo_totale:,.2f}")

st.divider()
st.subheader("Dettagli del Calcolo")
det_data = {
    "Descrizione": ["Codice HS", "Paese", "Volume", "Emissioni Incorporate", "Benchmark Applicato", "Free Allowance (%)", "Quota Emissioni Pagabili", "Costo per Ton"],
    "Valore": [hs_code, paese_origine, f"{volume} t", f"{emissioni_finali:.4f}", f"{benchmark_val:.4f}", f"{free_allowance_perc}%", f"{tco2_soggette:.4f}", f"€ {costo_unitario:.2f}"]
}
st.table(pd.DataFrame(det_data))
