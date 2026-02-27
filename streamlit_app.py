import streamlit as st
import pandas as pd

# Configurazione Pagina
st.set_page_config(page_title="CBAM Calculator PRO", layout="wide")

st.title("calc 🌍 CBAM Calculator PRO")
st.subheader("Strumento professionale per il calcolo dei certificati CBAM (2026-2034)")

# --- CARICAMENTO DATI ---
@st.cache_data
def load_data():
    # Carichiamo i tuoi file (assicurati che siano nella stessa cartella del file .py)
    df_bench = pd.read_csv('database_benchmarks_pulito.csv')
    df_def = pd.read_csv('database_defaults_pulito.csv')
    return df_bench, df_def

try:
    df_bench, df_def = load_data()
except:
    st.error("⚠️ Errore: Carica i file CSV (database_benchmarks_pulito.csv e database_defaults_pulito.csv) nella stessa cartella.")
    st.stop()

# --- SIDEBAR: PARAMETRI DI MERCATO ---
st.sidebar.header("Parametri Globali")
prezzo_ets = st.sidebar.number_input("Prezzo Medio ETS (€)", value=81.0)
anno = st.sidebar.selectbox("Anno di riferimento", [2026, 2027, 2028, 2029, 2030, 2034])

# Logica Free Allowance basata sull'anno (D6)
allowance_map = {2026: 0.975, 2027: 0.95, 2028: 0.90, 2029: 0.825, 2030: 0.75, 2034: 0.0}
free_allowance = allowance_map[anno]
st.sidebar.write(f"Free Allowance ({anno}): **{free_allowance*100}%**")

# --- MAIN: INPUT UTENTE ---
col1, col2 = st.columns(2)

with col1:
    st.markdown("### 1. Dettagli Merce")
    hs_search = st.text_input("Inserisci Codice HS (es. 7203 o 72024910)")
    volume = st.number_input("Volume Importato (Tonnellate)", min_value=1.0, value=150.0)
    
    # Ricerca Benchmark (D5)
    bench_match = df_bench[df_bench['CN code'].astype(str).str.contains(hs_search)] if hs_search else pd.DataFrame()
    
    if not bench_match.empty:
        benchmark_val = bench_match.iloc[0]['Benchmark_Value']
        st.success(f"Benchmark D5 trovato: {benchmark_val}")
    else:
        benchmark_val = st.number_input("Benchmark (D5) manuale", value=1.142)

with col2:
    st.markdown("### 2. Emissioni (D4)")
    usa_default = st.checkbox("Non conosco le emissioni (Usa Valori di Default)")
    
    if usa_default:
        paesi = df_def['Country'].unique()
        paese_scelto = st.selectbox("Seleziona Paese di Origine", paesi)
        
        def_match = df_def[(df_def['Country'] == paese_scelto) & (df_def['Product CN Code'].astype(str).str.contains(hs_search[:4]))]
        if not def_match.empty:
            emissioni_d4 = def_match.iloc[0]['Default Value (direct emissions)']
            st.info(f"Default D4 per {paese_scelto}: {emissioni_d4}")
        else:
            emissioni_d4 = 1.325 # Fallback mondiale
            st.warning(f"Usando fallback mondiale: {emissioni_d4}")
    else:
        emissioni_d4 = st.number_input("Inserisci Emissioni Reali (D4)", value=1.5)

# --- CALCOLO (La tua Formula) ---
# Formula: (D4 - (D5 * D6)) * D8
tassabile_per_ton = emissioni_d4 - (benchmark_val * free_allowance)
costo_unitario = max(0.0, tassabile_per_ton * prezzo_ets)
totale = costo_unitario * volume

# --- DISPLAY RISULTATI ---
st.markdown("---")
st.header("Risultato dell'Analisi")
c1, c2, c3 = st.columns(3)

# Formattazione italiana (Punto per migliaia, virgola per decimali)
costo_unitario_ita = f"{costo_unitario:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
totale_ita = f"{totale:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

c1.metric("Costo per Ton", f"{costo_unitario_ita} €")
c2.metric("Costo Totale CBAM", f"{totale_ita} €")
c3.metric("Emissioni Tassabili", f"{tassabile_per_ton:.3f} t/CO2")

st.info(f"**Nota:** Questo calcolo si basa sulla formula standard CBAM (D4 - (D5 * D6)) * D8. Nel {anno} la quota gratuita è del {free_allowance*100}%.")