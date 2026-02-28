import streamlit as st
import pandas as pd
import os

st.set_page_config(page_title="Lux CBAM Pro - Debug Mode", layout="wide")

@st.cache_data
def load_data():
    bench = pd.read_csv("benchmarks.csv")
    defaults = pd.read_csv("defaults.csv")
    
    # Pulizia stringhe
    bench['CN code'] = bench['CN code'].astype(str).str.split('.').str[0].str.strip()
    defaults['Product CN Code'] = defaults['Product CN Code'].astype(str).str.split('.').str[0].str.strip()
    defaults['Country'] = defaults['Country'].astype(str).str.strip()
    
    return bench, defaults

st.title("🌍 Lux CBAM Calculator")

try:
    bench_df, def_df = load_data()
    
    # --- SIDEBAR DEBUG ---
    st.sidebar.header("🛠 Strumenti di Controllo")
    debug_mode = st.sidebar.checkbox("Attiva Debug (Vedi dati interni)")

    col1, col2 = st.columns(2)
    with col1:
        countries = sorted([x for x in def_df['Country'].unique() if x != 'nan'])
        country = st.selectbox("Paese di Origine", countries)
        
        hs_codes = sorted(def_df[def_df['Country'] == country]['Product CN Code'].unique())
        if not hs_codes: # Se il paese non ha codici, mostra tutti quelli disponibili
             hs_codes = sorted(def_df['Product CN Code'].unique())
             
        hs_code = st.selectbox("Codice HS", hs_codes)
        volume = st.number_input("Volume (Tonnellate)", value=1.0)

    with col2:
        ets = st.number_input("Prezzo ETS (€)", value=75.0)
        use_real = st.toggle("Usa emissioni reali")
        real_val = st.number_input("Emissione reale", value=0.0) if use_real else None

    if st.button("Esegui Calcolo", type="primary"):
        # --- LOGICA DI RICERCA EMISSIONI ---
        em = None
        source = ""
        
        if use_real:
            em = real_val
            source = "Dato inserito manualmente"
        else:
            # 1. Prova Paese Specifico
            match = def_df[(def_df['Country'] == country) & (def_df['Product CN Code'] == hs_code)]
            em = pd.to_numeric(match.iloc[0]['2026'], errors='coerce') if not match.empty else None
            source = f"Default {country}"
            
            # 2. Fallback su 'Other Countries' se il primo tentativo fallisce o è vuoto
            if pd.isna(em) or em is None:
                match_other = def_df[(def_df['Country'].str.contains("Other", case=False)) & (def_df['Product CN Code'] == hs_code)]
                em = pd.to_numeric(match_other.iloc[0]['2026'], errors='coerce') if not match_other.empty else None
                source = "Default EU (Other Countries)"

        # --- LOGICA DI RICERCA BENCHMARK ---
        bm_col = 'BM_Real' if use_real else 'BM_Default'
        match_bm = bench_df[bench_df['CN code'] == hs_code]
        bm = pd.to_numeric(match_bm.iloc[0][bm_col], errors='coerce') if not match_bm.empty else None

        # --- MOSTRA RISULTATI O ERRORI ---
        if debug_mode:
            st.sidebar.write(f"**Analisi per HS {hs_code}:**")
            st.sidebar.write(f"- Emissione trovata: `{em}` (Sorgente: {source})")
            st.sidebar.write(f"- Benchmark trovato: `{bm}` (Colonna: {bm_col})")

        if pd.notna(em) and pd.notna(bm):
            fa = 0.975
            costo = (em - (bm * fa)) * ets * volume
            st.balloons()
            st.success(f"### Totale da pagare: € {max(0.0, costo):,.2f}")
            st.caption(f"Calcolo basato su: Emissioni ({em}) e Benchmark ({bm})")
        else:
            st.error("❌ Errore di Dati")
            if pd.isna(em): st.warning(f"Manca il valore '2026' in **defaults.csv** per il codice {hs_code} (anche nei valori di default globali).")
            if pd.isna(bm): st.warning(f"Manca il valore nel file **benchmarks.csv** per il codice {hs_code} nella colonna {bm_col}.")

except Exception as e:
    st.error(f"Errore critico: {e}")