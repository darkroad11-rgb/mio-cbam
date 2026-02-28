import streamlit as st
import pandas as pd
import numpy as np

# Configurazione Pagina
st.set_page_config(page_title="CBAM Calculator Pro", layout="wide")

st.title("🌍 CBAM Calculator Pro")
st.markdown("### Calcolatore Professionale per Emissioni Incorporate e Certificati CBAM")

# --- CARICAMENTO DATI ---
@st.cache_data
def load_data():
    # Caricamento e pulizia base
    bench = pd.read_csv('benchmarks final.xlsx - Foglio1.csv')
    defaults = pd.read_csv('default final.xlsx - cbam-default-values.csv')
    
    # Pulizia HS Codes
    bench['CN code'] = bench['CN code'].ffill().astype(str).str.split('.').str[0]
    defaults['Product CN Code'] = defaults['Product CN Code'].ffill().astype(str).str.split('.').str[0]
    
    # Conversione numerica
    for col in ['Column A\nBMg [tCO2e/t]', 'Column B\nBMg [tCO2e/t]']:
        bench[col] = pd.to_numeric(bench[col].astype(str).str.replace(',', '.'), errors='coerce')
    
    for col in ['2026 Default Value (Including mark-up)', '2027 Default Value (Including mark-up)', '2028 Default Value (Including mark-up)']:
        defaults[col] = pd.to_numeric(defaults[col].astype(str).str.replace(',', '.'), errors='coerce')
        
    return bench, defaults

bench_df, def_df = load_data()

# --- SIDEBAR PER PARAMETRI GENERALI ---
st.sidebar.header("Parametri di Mercato")
ets_price = st.sidebar.number_input("Prezzo ETS (€/tCO2)", value=80.0, step=1.0)
year = st.sidebar.selectbox("Anno di Riferimento", [2026, 2027, 2028, 2029, 2030])
volume = st.sidebar.number_input("Volume Importato (Tonnellate)", value=1.0, min_value=0.1)

# --- LOGICA DI CALCOLO ---
def get_cbam_calc(hs_code, country, route, real_em=None):
    # Emissioni
    is_real = real_em is not None and real_em > 0
    if is_real:
        emissions = real_em
    else:
        # Cerca default per paese
        target_col = f"{year} Default Value (Including mark-up)" if year <= 2028 else "2028 Default Value (Including mark-up)"
        match = def_df[(def_df['Country'] == country) & (def_df['Product CN Code'] == hs_code)]
        if match.empty:
            match = def_df[(def_df['Country'] == 'Other Countries and Territories') & (def_df['Product CN Code'] == hs_code)]
        emissions = match[target_col].values[0] if not match.empty else None

    # Benchmark
    val_col = 'Column A\nBMg [tCO2e/t]' if is_real else 'Column B\nBMg [tCO2e/t]'
    ind_col = 'Column A\nProduction route indicator' if is_real else 'Column B\nProduction route indicator'
    
    subset = bench_df[bench_df['CN code'] == hs_code]
    benchmark = None
    if not subset.empty:
        # Cerca per rotta specifica o indicatore temporale
        year_ind = '(1)' if year <= 2027 else '(2)'
        match_route = subset[subset[ind_col] == route]
        if not match_route.empty:
            benchmark = match_route[val_col].values[0]
        else:
            match_year = subset[subset[ind_col] == year_ind]
            benchmark = match_year[val_col].values[0] if not match_year.empty else subset[val_col].dropna().iloc[0]

    # Free Allowance
    schedule = {2026: 0.975, 2027: 0.95, 2028: 0.90, 2029: 0.775, 2030: 0.515}
    fa = schedule.get(year, 0)
    
    return emissions, benchmark, fa

# --- INTERFACCIA UTENTE ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("Selezione Merce")
    country_list = sorted(def_df['Country'].unique())
    country = st.selectbox("Paese di Origine", country_list)
    
    hs_list = sorted(bench_df['CN code'].unique())
    hs_code = st.selectbox("Codice HS (NC)", hs_list)
    
    route = st.selectbox("Production Route", ["(1)", "(2)", "(C)", "(D)", "(E)", "(F)", "(G)", "(H)", "(J)"], 
                         help="(1)/(2) sono indicatori temporali, (C-J) sono rotte specifiche per acciaio")

with col2:
    st.subheader("Dati Emissioni")
    use_real = st.toggle("Usa dati reali del fornitore", value=False)
    real_em = None
    if use_real:
        real_em = st.number_input("Emissioni Reali Dichiarate (tCO2/t)", value=0.0)
    
    paid_price = st.number_input("Prezzo del Carbonio già pagato all'estero (€/tCO2)", value=0.0)

# --- RISULTATI ---
if st.button("Calcola Costo CBAM", type="primary"):
    em, bm, fa = get_cbam_calc(hs_code, country, route, real_em if use_real else None)
    
    if em is not None and bm is not None:
        cert_cost_tn = (em - (bm * fa)) * ets_price
        total_due = max(0.0, (cert_cost_tn - paid_price) * volume)
        
        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Emissioni (tCO2/t)", f"{em:.3f}")
        c2.metric("Benchmark (tCO2/t)", f"{bm:.3f}")
        c3.metric("Free Allowance", f"{fa*100:.1f}%")
        c4.metric("TOTALE DA PAGARE", f"€ {total_due:,.2f}")
        
        st.info(f"💡 Per questa importazione di {volume}t, dovrai acquistare certificati per un valore di € {total_due:,.2f}.")
    else:
        st.error("Dati non trovati per questa combinazione di Codice HS e Paese.")

st.sidebar.markdown("---")
st.sidebar.caption("Sviluppato da Lux - CBAM Compliance Solutions")