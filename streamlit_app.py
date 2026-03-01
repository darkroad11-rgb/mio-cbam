import streamlit as st
import pandas as pd
import numpy as np
import re

st.set_page_config(page_title="CBAM Calculator Pro", layout="wide")

def clean_val(val):
    if pd.isna(val) or val == '' or str(val).strip() == '#VALUE!':
        return np.nan
    if isinstance(val, str):
        val = val.strip().replace(',', '.')
        try:
            return float(val)
        except:
            return np.nan
    return float(val)

@st.cache_data
def load_all_data():
    # Benchmark: delimitatore ;
    bm = pd.read_csv("benchmarks final.csv", sep=";")
    bm['CN code'] = bm['CN code'].ffill().astype(str).str.replace(r'\.0$', '', regex=True)
    bm['CN Description'] = bm['CN Description'].ffill()
    
    # Defaults: delimitatore ,
    df_def = pd.read_csv("cbam defaults.xlsx - cbam defaults.csv")
    df_def['Product CN Code'] = df_def['Product CN Code'].astype(str).str.replace(r'\.0$', '', regex=True)
    
    # Pulizia colonne numeriche
    for col in [c for c in bm.columns if 'BMg' in c]:
        bm[col] = bm[col].apply(clean_val)
    
    val_cols = ['2026 Default Value (Including mark-up)', 
                '2027 Default Value (Including mark-up)', 
                '2028 Default Value (Including mark-up)']
    for col in val_cols:
        df_def[col] = df_def[col].apply(clean_val)
        
    return bm, df_def

bench_df, def_df = load_all_data()

st.title("📊 Calcolatore CBAM Avanzato")

# --- UI SIDEBAR ---
with st.sidebar:
    st.header("1. Parametri Generali")
    anno = st.slider("Anno di riferimento", 2026, 2030, 2026)
    periodo_key = "(1)" if anno <= 2027 else "(2)"
    
    st.header("2. Dati Prodotto")
    codici_hs = sorted(bench_df['CN code'].unique())
    hs_scelto = st.selectbox("Codice HS (CN Code)", codici_hs)
    
    paesi = sorted(def_df['Country'].unique())
    paese_scelto = st.selectbox("Paese di Origine", paesi)
    
    volume = st.number_input("Volume (Ton)", min_value=0.0, value=1.0)
    
    st.header("3. Emissioni Reali")
    usa_reali = st.checkbox("Ho dati sulle emissioni reali", value=True)
    emissioni_input = 0.0
    if usa_reali:
        emissioni_input = st.number_input("Emissioni Reali (tCO2e/t)", min_value=0.0, format="%.4f")

# --- LOGICA DI CALCOLO ---

# Selezione Benchmark (Colonna A se reali, B se default)
col_val = 'Column A\nBMg [tCO2e/t]' if usa_reali else 'Column B\nBMg [tCO2e/t]'
col_ind = 'Column A\nProduction route indicator' if usa_reali else 'Column B\nProduction route indicator'

rows_hs = bench_df[bench_df['CN code'] == hs_scelto]

# Filtro per Periodo (1) o (2)
def filter_period(val):
    val = str(val)
    if periodo_key in val: return True
    if "(1)" not in val and "(2)" not in val: return True
    return False

rows_periodo = rows_hs[rows_hs[col_ind].apply(filter_period)]

# Gestione Rotte di Produzione
if len(rows_periodo) > 1:
    options = []
    for idx, r in rows_periodo.iterrows():
        ind = str(r[col_ind])
        match = re.search(r'\(([A-Z])\)', ind)
        label = match.group(1) if match else f"Opzione {idx}"
        options.append((label, idx))
    
    scelta_label = st.selectbox("Seleziona Rotta di Produzione (Indicator)", [o[0] for o in options])
    idx_final = [o[1] for o in options if o[0] == scelta_label][0]
    row_bm = rows_periodo.loc[idx_final]
else:
    row_bm = rows_periodo.iloc[0] if not rows_periodo.empty else None

benchmark_val = row_bm[col_val] if row_bm is not None else 0.0

# Gestione Emissioni (Se non reali, cerca nei default)
emissioni_finali = emissioni_input
if not usa_reali:
    col_anno_def = f"{min(anno, 2028)} Default Value (Including mark-up)"
    # Cerca per Paese + HS
    def_row = def_df[(def_df['Product CN Code'] == hs_scelto) & (def_df['Country'] == paese_scelto)]
    
    val_found = np.nan
    if not def_row.empty:
        val_found = def_row.iloc[0][col_anno_def]
    
    # Se vuoto o non trovato, cerca in Other Countries
    if pd.isna(val_found):
        other_row = def_df[(def_df['Product CN Code'] == hs_scelto) & (def_df['Country'].str.contains("Other", na=False))]
        if not other_row.empty:
            val_found = other_row.iloc[0][col_anno_def]
            st.warning(f"Dati non trovati per {paese_scelto}. Usato valore 'Other Countries'.")
        else:
            # Prova a cercare con le prime 4 cifre del codice HS se ancora non trovato
            short_hs = hs_scelto[:4]
            fallback_row = def_df[(def_df['Product CN Code'].str.startswith(short_hs)) & (def_df['Country'].str.contains("Other", na=False))]
            if not fallback_row.empty:
                val_found = fallback_row.iloc[0][col_anno_def]
                st.info(f"Usato valore generico per categoria HS {short_hs}.")

    emissioni_finali = val_found if not pd.isna(val_found) else 0.0

# --- OUTPUT ---
st.divider()
c1, c2, c3 = st.columns(3)

with c1:
    st.metric("Emissioni Applicate", f"{emissioni_finali:.4f} tCO2/t")
    st.caption("Dato " + ("Reale" if usa_reali else "Default"))

with c2:
    st.metric("Benchmark CBAM", f"{benchmark_val:.4f} tCO2/t")
    st.caption(f"Periodo {periodo_key}")

# Calcolo semplificato (Esempio: Prezzo ETS 80€, Free Allowance 97.5% per il 2026)
fa_perc = 97.5 if anno <= 2026 else 95.0 # Valori indicativi
prezzo_ets = 80.0
quota_pagabile = max(0, emissioni_finali - (benchmark_val * fa_perc / 100))
costo_tot = quota_pagabile * volume * prezzo_ets

with c3:
    st.metric("Costo Stimato Certificati", f"€ {costo_tot:,.2f}")

if row_bm is not None:
    st.success(f"Prodotto Identificato: **{row_bm['CN Description']}**")