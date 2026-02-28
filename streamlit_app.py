import streamlit as st
import pandas as pd
import os

st.set_page_config(page_title="Lux CBAM Calculator", layout="wide")

@st.cache_data
def load_data():
    # Carica i nuovi file puliti
    bench = pd.read_csv("benchmarks.csv")
    defaults = pd.read_csv("defaults.csv")
    
    # Assicuriamoci che i codici HS siano stringhe pulite
    bench['CN code'] = bench['CN code'].astype(str).str.split('.').str[0]
    defaults['Product CN Code'] = defaults['Product CN Code'].astype(str).str.split('.').str[0]
    return bench, defaults

st.title("🌍 Lux CBAM Calculator")
st.markdown("---")

try:
    bench_df, def_df = load_data()
    
    col1, col2 = st.columns(2)
    with col1:
        country = st.selectbox("Paese di Origine", sorted(def_df['Country'].unique()))
        hs_list = sorted(def_df[def_df['Country'] == country]['Product CN Code'].unique())
        hs_code = st.selectbox("Codice HS", hs_list)
        volume = st.number_input("Volume (Tonnellate)", value=1.0, min_value=0.0)

    with col2:
        ets = st.number_input("Prezzo ETS (€)", value=75.0)
        use_real = st.checkbox("Usa emissioni reali del fornitore")
        real_val = st.number_input("Valore emissione reale", value=0.0) if use_real else None
        paid_tax = st.number_input("Costo già pagato all'estero (€)", value=0.0)

    if st.button("Calcola CBAM", type="primary"):
        # 1. Emissioni
        if use_real:
            em = real_val
            bm_col = 'BM_Real'
        else:
            match_def = def_df[(def_df['Country'] == country) & (def_df['Product CN Code'] == hs_code)]
            em = match_def.iloc[0]['2026'] if not match_def.empty else None
            bm_col = 'BM_Default'

        # 2. Benchmark
        match_bm = bench_df[bench_df['CN code'] == hs_code]
        bm = match_bm.iloc[0][bm_col] if not match_bm.empty else None

        if em is not None and bm is not None:
            fa = 0.975 # 2026
            costo_cert = (em - (bm * fa)) * ets
            totale = (costo_cert * volume) - paid_tax
            st.success(f"### Totale da pagare: € {max(0.0, totale):,.2f}")
            st.write(f"Dettagli: Emissioni {em} | Benchmark {bm}")
        else:
            st.error("Dati non trovati nel database per questa selezione.")

except Exception as e:
    st.error(f"Errore nel caricamento dei dati: {e}")