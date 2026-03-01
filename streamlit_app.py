import streamlit as st
import pandas as pd
import re

# Configurazione
st.set_page_config(page_title="CBAM Pro Calculator", layout="wide")
st.title("🛡️ CBAM Pro - Calcolatore Certificati")

def clean_val(val):
    if pd.isna(val) or str(val).strip().lower() in ["", "n/a", "nan"]:
        return None
    try:
        # Toglie note tra parentesi ed estrae il numero
        s = str(val).split('(')[0].strip()
        return float(s.replace(',', '.'))
    except:
        return None

# Caricamento dati
@st.cache_data
def load_data():
    # Nota: Assicurati di aver caricato questi file su GitHub con questi nomi esatti
    df_bench = pd.read_csv('database_benchmarks_pulito.csv')
    df_def = pd.read_csv('database_defaults_pulito.csv')
    return df_bench, df_def

try:
    df_bench, df_def = load_data()
except Exception as e:
    st.error(f"⚠️ Errore caricamento file: {e}")
    st.stop()

# --- SIDEBAR: SETTAGGI ---
st.sidebar.header("Parametri di Mercato")
anno = st.sidebar.selectbox("Seleziona Anno", [2026, 2027, 2028])
prezzo_ets = st.sidebar.number_input("Prezzo Certificato ETS (€)", value=81.0)

# Mappatura Colonne e Allowance (D6)
# Col H = 2026, Col I = 2027, Col J = 2028 (nella tua tabella L)
map_col = {2026: "2026 Default Value (Including mark-up)", 
           2027: "2027 Default Value (Including mark-up)", 
           2028: "2028 Default Value (Including mark-up)"}
map_allowance = {2026: 0.975, 2027: 0.95, 2028: 0.90}

target_col = map_col[anno]
free_allowance = map_allowance[anno]

# --- MAIN ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Prodotto e Benchmark")
    hs_input = st.text_input("Inserisci Codice HS (es. 7203 o 72024910)", "7203")
    volume = st.number_input("Tonnellate Importate", value=150.0)

    # Ricerca Benchmark (D5) - Cerchiamo il match più lungo possibile
    bench_match = df_bench[df_bench['CN code'].astype(str).str.startswith(hs_input)].head(1)
    if bench_match.empty and len(hs_input) > 4:
         bench_match = df_bench[df_bench['CN code'].astype(str).str.startswith(hs_input[:4])].head(1)
    
    if not bench_match.empty:
        benchmark_val = clean_val(bench_match.iloc[0]['Benchmark_Value'])
        st.success(f"Benchmark (D5) rilevato: **{benchmark_val}**")
    else:
        benchmark_val = st.number_input("Inserisci Benchmark (D5) manuale", value=1.142)

with col2:
    st.subheader("2. Paese e Emissioni")
    usa_default = st.toggle("Usa Valori di Default (D4)", value=True)
    
    if usa_default:
        paesi = sorted(df_def['Country'].unique())
        paese_scelto = st.selectbox("Paese di Origine", paesi, index=paesi.index("China") if "China" in paesi else 0)
        
        # LOGICA RICHIESTA: Cerca Paese -> Se Vuoto -> Cerca Other Countries
        def find_default(p, hs):
            # Prova match esatto o parent (4 cifre)
            hs_short = hs[:4]
            rows = df_def[(df_def['Country'] == p) & (df_def['Product CN Code'].astype(str).str.startswith(hs_short))]
            val = None
            if not rows.empty:
                val = clean_val(rows.iloc[0][target_col])
            
            # Se ancora nullo, usa Other Countries
            if val is None:
                st.warning(f"Dato mancante per {p}. Utilizzo valore 'Other Countries'...")
                rows_other = df_def[(df_def['Country'].str.contains("Other", na=False)) & (df_def['Product CN Code'].astype(str).str.startswith(hs_short))]
                if not rows_other.empty:
                    val = clean_val(rows_other.iloc[0][target_col])
            return val

        emissioni_d4 = find_default(paese_scelto, hs_input)
        if emissioni_d4 is None: emissioni_d4 = 1.325 # Fallback finale
        st.info(f"Default (D4) applicato: **{emissioni_d4}**")
    else:
        emissioni_d4 = st.number_input("Inserisci Emissioni Reali (D4)", value=1.5)

# --- CALCOLO FINALE ---
# Formula: (D4 - (D5 * D6)) * D8
differenziale = emissioni_d4 - (benchmark_val * free_allowance)
costo_ton = max(0.0, differenziale * prezzo_ets)
totale_euro = costo_ton * volume

# --- RISULTATI ---
st.divider()
c1, c2, c3 = st.columns(3)

def f_it(n): return f"{n:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

c1.metric("Costo per Ton", f"{f_it(costo_ton)} €")
c2.metric("TOTALE DA PAGARE", f"{f_it(totale_euro)} €")
c3.metric("Impatto Carbonio", f"{differenziale:.3f} tCO2/t")

st.info(f"💡 Nel **{anno}**, la quota gratuita (Free Allowance) è del **{free_allowance*100}%**. Il calcolo utilizza la colonna del database: *{target_col}*.")


