import streamlit as st
import pandas as pd
import os

# Funzione corretta per caricare i dati
def load_data():
    if not os.path.exists("benchmarks.csv") or not os.path.exists("defaults.csv"):
        st.error("I file CSV non sono presenti su GitHub!")
        st.stop()
    
    # Leggiamo i file
    bench = pd.read_csv("benchmarks.csv")
    defaults = pd.read_csv("defaults.csv")
    
    # Rimuoviamo spazi extra dai nomi delle colonne per evitare errori
    bench.columns = [c.replace('\n', ' ').strip() for c in bench.columns]
    defaults.columns = [c.replace('\n', ' ').strip() for c in defaults.columns]
    
    return bench, defaults

st.title("🌍 CBAM Calculator Pro")
bench_df, def_df = load_data()

# Selezione Input
country = st.selectbox("Paese", sorted(def_df['Country'].unique()))
hs_code = st.selectbox("Codice HS", sorted(bench_df['CN code'].astype(str).unique()))

# Calcolo Semplice
if st.button("Calcola"):
    # Cerchiamo il valore di default nel database
    default_val = def_df[(def_df['Country'] == country) & (def_df['Product CN Code'].astype(str) == hs_code)]
    
    if not default_val.empty:
        # Prendiamo il valore 2026 (colonna 4 o 5 a seconda del file)
        val = default_val.iloc[0, 4] 
        st.success(f"Emissione di default per {hs_code} in {country}: {val} tCO2/t")
    else:
        st.warning("Dati non trovati per questa selezione.")