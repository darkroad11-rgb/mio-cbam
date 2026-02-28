import streamlit as st
import pandas as pd

st.set_page_config(page_title="Lux CBAM Pro", layout="wide")

# Forza il caricamento senza errori di tipo
@st.cache_data
def load_data():
    b = pd.read_csv("benchmarks.csv", dtype={'CN code': str, 'Route': str})
    d = pd.read_csv("defaults.csv", dtype={'Product CN Code': str, 'Country': str})
    return b, d

st.title("🌍 Lux CBAM Calculator")

try:
    bench_df, def_df = load_data()

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("1. Selezione Merce")
        paese = st.selectbox("Paese di Origine", sorted(def_df['Country'].unique()))
        
        # Filtro codici HS
        hs_list = sorted(def_df[def_df['Country'] == paese]['Product CN Code'].unique())
        codice_hs = st.selectbox("Codice HS", hs_list)
        
        # Filtro Rotte
        rotte_disponibili = bench_df[bench_df['CN code'] == codice_hs]['Route'].unique()
        rotta = st.selectbox("Rotta / Periodo (-1=26/27, -2=28/30)", rotte_disponibili)
        
        ton = st.number_input("Tonnellate Importate", value=1.0)

    with col2:
        st.subheader("2. Parametri e Calcolo")
        anno = st.selectbox("Anno", [2026, 2027, 2028])
        prezzo_ets = st.number_input("Prezzo ETS (€)", value=80.0)
        
        reali = st.toggle("Usa emissioni reali fornitore")
        val_reale = st.number_input("Emissione reale (tCO2/t)", value=0.0) if reali else 0.0

    if st.button("CALCOLA TOTALE", type="primary", use_container_width=True):
        # LOGICA EMISSIONE
        if reali and val_reale > 0:
            E = val_reale
            col_bm = "BM_Real"
        else:
            riga_def = def_df[(def_df['Country'] == paese) & (def_df['Product CN Code'] == codice_hs)]
            E = pd.to_numeric(riga_def[str(anno)].values[0], errors='coerce')
            col_bm = "BM_Default"

        # LOGICA BENCHMARK
        riga_bm = bench_df[(bench_df['CN code'] == codice_hs) & (bench_df['Route'] == rotta)]
        B = pd.to_numeric(riga_bm[col_bm].values[0], errors='coerce')

        # FREE ALLOWANCE
        FA = {2026: 0.975, 2027: 0.95, 2028: 0.90}.get(anno)

        if pd.notna(E) and pd.notna(B):
            # FORMULA
            costo_un = (E - (B * FA)) * prezzo_ets
            totale = max(0.0, costo_un * ton)

            st.divider()
            st.metric("TOTALE DA PAGARE", f"€ {totale:,.2f}")
            
            with st.expander("Vedi i passaggi del calcolo"):
                st.write(f"- Emissione (E): {E}")
                st.write(f"- Benchmark (B): {B}")
                st.write(f"- Free Allowance (FA): {FA}")
                st.write(f"**Formula:** ({E} - ({B} * {FA})) * {prezzo_ets} * {ton}")
        else:
            st.error("Dati mancanti nel CSV per questa combinazione. Controlla i file.")

except Exception as e:
    st.error(f"Errore: {e}")
        
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
