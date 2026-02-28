import streamlit as st
import pandas as pd
import os

st.set_page_config(page_title="Lux CBAM Calculator", layout="wide")

@st.cache_data
def load_data():
    if not os.path.exists("benchmarks.csv") or not os.path.exists("defaults.csv"):
        st.error("⚠️ File CSV mancanti su GitHub!")
        st.stop()
    
    bench = pd.read_csv("benchmarks.csv")
    defaults = pd.read_csv("defaults.csv")
    
    # PULIZIA "ANTI-ERRORE": Trasformiamo tutto in stringa e togliamo i vuoti
    bench['CN code'] = bench['CN code'].astype(str).str.split('.').str[0].str.strip()
    defaults['Product CN Code'] = defaults['Product CN Code'].astype(str).str.split('.').str[0].str.strip()
    
    # Pulizia nomi Paesi (rimuove i valori non validi che causano l'errore float vs str)
    defaults['Country'] = defaults['Country'].astype(str).str.strip()
    defaults = defaults[defaults['Country'] != 'nan'] # Rimuove i "Not a Number"
    
    return bench, defaults

st.title("🌍 Lux CBAM Calculator")
st.markdown("---")

try:
    bench_df, def_df = load_data()
    
    col1, col2 = st.columns(2)
    with col1:
        # Ora il sorted() funzionerà perché abbiamo trasformato tutto in stringa
        paisa_disponibili = sorted([str(x) for x in def_df['Country'].unique() if x != 'nan'])
        country = st.selectbox("Paese di Origine", paisa_disponibili)
        
        # Filtro codici HS per il paese scelto
        filtro_hs = def_df[def_df['Country'] == country]['Product CN Code'].unique()
        hs_disponibili = sorted([str(x) for x in filtro_hs if x != 'nan'])
        hs_code = st.selectbox("Codice HS", hs_disponibili)
        
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
            # Prendiamo il valore 2026. Se vuoto, cerchiamo di convertirlo
            em = pd.to_numeric(match_def.iloc[0]['2026'], errors='coerce') if not match_def.empty else None
            bm_col = 'BM_Default'

        # 2. Benchmark
        match_bm = bench_df[bench_df['CN code'] == hs_code]
        bm = pd.to_numeric(match_bm.iloc[0][bm_col], errors='coerce') if not match_bm.empty else None

        if em is not None and not pd.isna(em) and bm is not None and not pd.isna(bm):
            fa = 0.975 # Coefficiente 2026
            costo_cert = (em - (bm * fa)) * ets
            totale = (costo_cert * volume) - paid_tax
            
            st.divider()
            st.success(f"### Totale da pagare: € {max(0.0, totale):,.2f}")
            st.info(f"Dettagli calcolo: Emissioni default ({em}) - (Benchmark {bm} x Free Allowance {fa})")
        else:
            st.error("⚠️ Dati incompleti nel database per questa combinazione. Controlla che i valori numerici siano presenti nei CSV.")

except Exception as e:
    st.error(f"❌ Errore tecnico: {e}")