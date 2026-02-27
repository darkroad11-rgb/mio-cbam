import streamlit as st
import pandas as pd
import re

# Configurazione Pagina
st.set_page_config(page_title="CBAM Calculator PRO", layout="wide")

st.title("🌍 CBAM Calculator PRO")
st.subheader("Calcolo basato su Regolamento UE 2023/956")

# Funzione per pulire i numeri (gestisce virgole e parentesi)
def clean_val(val):
    if pd.isna(val) or val == "" or str(val).strip().lower() == "n/a":
        return None
    try:
        # Estrae solo il numero, gestendo la virgola italiana
        match = re.search(r"(\d+,\d+|\d+\.\d+|\d+)", str(val))
        if match:
            return float(match.group(1).replace(',', '.'))
    except:
        return None
    return None

# --- CARICAMENTO DATI ---
@st.cache_data
def load_data():
    # Carichiamo i tuoi file CSV puliti o originali
    df_bench = pd.read_csv('database_benchmarks_pulito.csv')
    df_def = pd.read_csv('database_defaults_pulito.csv')
    return df_bench, df_def

try:
    df_bench, df_def = load_data()
except:
    st.error("⚠️ Carica i file CSV sul tuo GitHub per far funzionare il calcolatore.")
    st.stop()

# --- SIDEBAR: PARAMETRI DI MERCATO ---
st.sidebar.header("Parametri Globali")
prezzo_ets = st.sidebar.number_input("Prezzo Medio ETS (€)", value=81.0)
anno = st.sidebar.selectbox("Anno di riferimento", [2026, 2027, 2028, 2029, 2030])

# Mapping Free Allowance (D6)
allowance_map = {2026: 0.975, 2027: 0.95, 2028: 0.90, 2029: 0.825, 2030: 0.75}
free_allowance = allowance_map[anno]

# Selezione Colonna Default in base all'anno
col_year = {
    2026: "2026 Default Value (Including mark-up)",
    2027: "2027 Default Value (Including mark-up)",
    2028: "2028 Default Value (Including mark-up)",
    2029: "2028 Default Value (Including mark-up)", # Fallback 2028+
    2030: "2028 Default Value (Including mark-up)"
}
default_col_name = col_year[anno]

# --- MAIN: INPUT ---
col1, col2 = st.columns(2)

with col1:
    st.markdown("### 1. Prodotto e Benchmark (D5)")
    hs_search = st.text_input("Inserisci Codice HS (es. 7203)", value="7203")
    volume = st.number_input("Volume (Tonnellate)", value=150.0)
    
    # Ricerca Benchmark (D5)
    bench_match = df_bench[df_bench['CN code'].astype(str).str.startswith(hs_search[:4])]
    if not bench_match.empty:
        benchmark_val = clean_val(bench_match.iloc[0]['Benchmark_Value'])
        st.success(f"Benchmark D5 trovato: {benchmark_val}")
    else:
        benchmark_val = st.number_input("Inserisci Benchmark (D5) manualmente", value=1.142)

with col2:
    st.markdown("### 2. Emissioni (D4)")
    usa_default = st.checkbox("Usa Valori di Default (se non hai dati reali)")
    
    if usa_default:
        paesi = sorted(df_def['Country'].unique())
        paese_scelto = st.selectbox("Paese di Origine", paesi)
        
        # Logica di ricerca Default (D4)
        # Filtro per Paese e HS
        def_row = df_def[(df_def['Country'] == paese_scelto) & (df_def['Product CN Code'].astype(str).str.startswith(hs_search[:4]))]
        
        # Se vuoto o valore nullo, cerca in "Other Countries and Territories"
        val_d4 = None
        if not def_row.empty:
            val_d4 = clean_val(def_row.iloc[0][default_col_name])
        
        if val_d4 is None:
            st.warning("Valore non trovato per questo paese. Ricerca nei valori globali...")
            fallback_row = df_def[(df_def['Country'].str.contains("Other", na=False)) & (df_def['Product CN Code'].astype(str).str.startswith(hs_search[:4]))]
            if not fallback_row.empty:
                val_d4 = clean_val(fallback_row.iloc[0][default_col_name])
        
        emissioni_d4 = val_d4 if val_d4 is not None else 1.325
        st.info(f"D4 applicato ({anno}): {emissioni_d4}")
    else:
        emissioni_d4 = st.number_input("Inserisci Emissioni Reali (D4)", value=1.5)

# --- CALCOLO (Tua Formula Corretta) ---
# Formula: (D4 - (D5 * D6)) * D8
tassabile_per_ton = emissioni_d4 - (benchmark_val * free_allowance)
costo_unitario = max(0.0, tassabile_per_ton * prezzo_ets)
totale_pagare = costo_unitario * volume

# --- RISULTATI ---
st.markdown("---")
st.header("Analisi Economica CBAM")
r1, r2, r3 = st.columns(3)

# Formattazione italiana
def format_ita(n):
    return f"{n:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

r1.metric("Costo / Ton", f"{format_ita(costo_unitario)} €")
r2.metric("TOTALE DA PAGARE", f"{format_ita(totale_pagare)} €")
r3.metric("Free Allowance", f"{free_allowance*100}%")

st.caption(f"Calcolo basato sulla colonna: {default_col_name} per il settore HS {hs_search[:4]}")