import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="CBAM Professional Tool", layout="wide")
st.title("🌍 CBAM Expert System - Versione Finale")

# --- FUNZIONI TECNICHE ---
def clean_num(val):
    if pd.isna(val) or str(val).strip() == "": return None
    try:
        s = str(val).replace(',', '.')
        match = re.search(r"(\d+\.\d+|\d+)", s)
        return float(match.group(1)) if match else None
    except: return None

@st.cache_data
def load_all_data():
    # Carica i file caricati su GitHub
    df_b = pd.read_csv('benchmarks_final.csv').ffill() # ffill riempie i codici HS vuoti
    df_d = pd.read_csv('defaults_final.csv')
    return df_b, df_d

# --- LOGICA RICERCA BENCHMARK (D5) ---
def get_d5_logic(hs, year, is_default, route_code, df):
    # Suffix: (1) per 2026-27, (2) per 2028-30
    suffix = "(1)" if year <= 2027 else "(2)"
    
    # Determina le colonne in base a Reali (A) o Default (B)
    if not is_default:
        col_bm = "Column A\nBMg [tCO2e/t]"
        col_rt = "Column A\nProduction route indicator"
    else:
        col_bm = "Column B\nBMg [tCO2e/t]"
        col_rt = "Column B\nProduction route indicator"

    # Ricerca per HS (match esatto o a scendere)
    temp_hs = str(hs).strip()
    while len(temp_hs) >= 4:
        match = df[df['CN code'].astype(str).str.startswith(temp_hs)]
        if not match.empty:
            # Filtro 1: Rotta di Produzione (C-J)
            if route_code:
                match = match[match[col_rt].astype(str).str.contains(f"\\({route_code}\\)", na=False)]
            
            # Filtro 2: Anno (1) o (2)
            final_match = match[match[col_bm].astype(str).str.contains(f"\\{suffix}", na=False)]
            
            if not final_match.empty:
                return clean_num(final_match.iloc[0][col_bm])
            elif not match.empty:
                return clean_num(match.iloc[0][col_bm]) # Fallback se non c'è il suffisso
        temp_hs = temp_hs[:-1]
    return 1.142

# --- INTERFACCIA ---
try:
    df_bench, df_def = load_all_data()
except Exception as e:
    st.error(f"⚠️ Errore caricamento file CSV: {e}. Assicurati di averli caricati su GitHub con i nomi corretti.")
    st.stop()

st.sidebar.header("Impostazioni")
anno = st.sidebar.selectbox("Anno", [2026, 2027, 2028, 2029, 2030])
prezzo_ets = st.sidebar.number_input("Prezzo ETS (€)", value=75.0)

rotte = {
    "Standard": None,
    "(C) Carbon Steel - BF/BOF": "C",
    "(D) Carbon Steel - DRI/EAF": "D",
    "(E) Carbon Steel - Scrap/EAF": "E",
    "(F) Low alloy Steel - BF/BOF": "F",
    "(G) Low alloy Steel - DRI/EAF": "G",
    "(H) Low alloy Steel - Scrap/EAF": "H",
    "(J) High alloy Steel - EAF": "J"
}

c1, c2 = st.columns(2)
with c1:
    st.subheader("1. Prodotto")
    hs_in = st.text_input("Codice HS", "72024910")
    vol = st.number_input("Quantità (Ton)", value=1.0)
    rotta_label = st.selectbox("Rotta di Produzione", list(rotte.keys()))
    rotta_sel = rotte[rotta_label]

with c2:
    st.subheader("2. Emissioni")
    metodo = st.radio("Metodo Calcolo", ["Default UE", "Dati Reali Fornitore"])
    is_def_mode = (metodo == "Default UE")
    
    if is_def_mode:
        p_list = sorted(df_def['Country'].unique())
        paese = st.selectbox("Paese Origine", p_list, index=p_list.index("Other Countries and Territories"))
        
        # Colonna Default per anno
        col_d4 = "2026 Default Value (Including mark-up)" if anno <= 2026 else "2027 Default Value (Including mark-up)" if anno == 2027 else "2028 Default Value (Including mark-up)"
        
        # Ricerca D4 con Fallback Other Countries
        d4_row = df_def[(df_def['Country'] == paese) & (df_def['Product CN Code'].astype(str).str.startswith(hs_in[:4]))]
        if d4_row.empty or pd.isna(d4_row.iloc[0][col_d4]):
            d4_row = df_def[(df_def['Country'].str.contains("Other")) & (df_def['Product CN Code'].astype(str).str.startswith(hs_in[:4]))]
        
        d4_val = clean_num(d4_row.iloc[0][col_d4]) if not d4_row.empty else 3.157
        st.info(f"D4 applicato: **{d4_val}**")
    else:
        d4_val = st.number_input("Emissioni Reali (D4)", value=3.157)

# --- CALCOLO ---
d5_val = get_d5_logic(hs_in, anno, is_def_mode, rotta_sel, df_bench)
d6_val = 0.975 # Free allowance standard

costo_unitario = (d4_val - (d5_val * d6_val)) * prezzo_ets
totale_pagare = max(0.0, costo_unitario * vol)

st.divider()
r1, r2, r3 = st.columns(3)
def fi(n): return f"{n:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

r1.metric("Benchmark D5", f"{d5_val}")
r2.metric("Costo / Ton", f"{fi(costo_unitario)} €")
r3.metric("TOTALE CBAM", f"{fi(totale_pagare)} €")

st.caption(f"Logica: Anno {anno} | Rotta: {rotta_label} | Colonna Benchmark: {'B' if is_def_mode else 'A'}")