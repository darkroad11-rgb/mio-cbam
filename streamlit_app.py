import streamlit as st
import pandas as pd
import os

st.set_page_config(page_title="CBAM Calculator", layout="wide")

# Funzione per caricare i dati con gestione errori
def load_data():
    files = {
        "benchmarks": "benchmarks.csv",
        "defaults": "defaults.csv"
    }
    
    # Controlla se i file esistono sul server
    for key, name in files.items():
        if not os.path.exists(name):
            st.error(f"❌ Errore: Il file **{name}** non è stato trovato nella cartella principale di GitHub.")
            st.stop()
            
    try:
        bench = pd.read_csv(files["benchmarks"])
        defaults = pd.read_csv(files["defaults"])
        
        # Pulizia automatica minima per sicurezza
        bench['CN code'] = bench['CN code'].ffill().astype(str).str.split('.').str[0]
        defaults['Product CN Code'] = defaults['Product CN Code'].ffill().astype(str).str.split('.').str[0]
        
        return bench, defaults
    except Exception as e:
        st.error(f"❌ Errore durante la lettura dei file: {e}")
        st.stop()

st.title("🌍 CBAM Calculator Pro")

# Caricamento
bench_df, def_df = load_data()

# --- LOGICA DI CALCOLO ---
def get_cbam_calc(hs_code, country, route, year, volume, ets_price, real_em=None):
    is_real = real_em is not None and real_em > 0
    
    # 1. Emissioni
    if is_real:
        emissions = real_em
    else:
        # Cerca default
        target_col = '2026 Default Value (Including mark-up)' # Default fisso per test, poi si può rendere dinamico
        match = def_df[(def_df['Country'] == country) & (def_df['Product CN Code'] == hs_code)]
        if match.empty:
            match = def_df[(def_df['Country'] == 'Other Countries and Territories') & (def_df['Product CN Code'] == hs_code)]
        emissions = match.iloc[0][target_col] if not match.empty else None

    # 2. Benchmark
    val_col = 'Column A\nBMg [tCO2e/t]' if is_real else 'Column B\nBMg [tCO2e/t]'
    subset = bench_df[bench_df['CN code'] == hs_code]
    benchmark = subset[val_col].dropna().iloc[0] if not subset.empty else None

    # 3. Free Allowance (2026 = 97.5%)
    fa = 0.975 
    
    return emissions, benchmark, fa

# --- INTERFACCIA ---
col1, col2 = st.columns(2)
with col1:
    country = st.selectbox("Paese di Origine", sorted(def_df['Country'].unique()))
    hs_code = st.selectbox("Codice HS", sorted(bench_df['CN code'].unique()))
    volume = st.number_input("Volume (Tonnellate)", value=1.0)

with col2:
    ets = st.number_input("Prezzo ETS (€)", value=80.0)
    use_real = st.checkbox("Ho emissioni reali")
    real_val = st.number_input("Valore emissione reale", value=0.0) if use_real else None

if st.button("Calcola"):
    em, bm, fa = get_cbam_calc(hs_code, country, "default", 2026, volume, ets, real_val)
    if em and bm:
        costo = (em - (bm * fa)) * ets * volume
        st.success(f"Costo stimato: € {max(0.0, costo):,.2f}")
    else:
        st.warning("Dati non trovati per questa selezione.")