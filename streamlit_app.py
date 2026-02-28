import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="CBAM Expert System", layout="wide")
st.title("🌍 CBAM Expert System - Analisi Tecnica")

# --- FUNZIONI DI PULIZIA ---
def clean_num(val):
    if pd.isna(val) or str(val).strip() == "": return None
    try:
        s = str(val).replace(',', '.')
        match = re.search(r"(\d+\.\d+|\d+)", s)
        return float(match.group(1)) if match else None
    except: return None

@st.cache_data
def load_data():
    # Carica i CSV - ffill() è fondamentale per riempire i codici HS vuoti nelle righe delle rotte
    df_b = pd.read_csv('benchmarks_final.csv').ffill()
    df_d = pd.read_csv('defaults_final.csv')
    return df_b, df_d

# --- LOGICA BENCHMARK D5 (A/B, 1/2, C-J) ---
def get_d5(hs, year, is_default, route, df):
    # Suffix: (1) 2026-27, (2) 2028-30
    suffix = "(1)" if year <= 2027 else "(2)"
    
    # Selezione Colonna A (Reali) o B (Default)
    if not is_default:
        col_bm = "Column A\nBMg [tCO2e/t]"
        col_ind = "Column A\nProduction route indicator"
    else:
        col_bm = "Column B\nBMg [tCO2e/t]"
        col_ind = "Column B\nProduction route indicator"

    temp_hs = str(hs).strip()
    while len(temp_hs) >= 4:
        # Filtro per HS
        matches = df[df['CN code'].astype(str).str.startswith(temp_hs)]
        if not matches.empty:
            # Filtro per Rotta di Produzione (C-J)
            if route:
                matches = matches[matches[col_ind].astype(str).str.contains(f"\\({route}\\)", na=False)]
            
            # Filtro per Periodo (1) o (2)
            period_match = matches[matches[col_bm].astype(str).str.contains(f"\\{suffix}", na=False)]
            
            if not period_match.empty:
                return clean_num(period_match.iloc[0][col_bm])
            elif not matches.empty:
                return clean_num(matches.iloc[0][col_bm])
        temp_hs = temp_hs[:-1]
    return 1.142

# --- INTERFACCIA ---
try:
    df_bench, df_def = load_data()
except Exception as e:
    st.error(f"⚠️ Errore: {e}. Controlla i nomi dei file su GitHub.")
    st.stop()

st.sidebar.header("Parametri")
anno = st.sidebar.selectbox("Anno", [2026, 2027, 2028, 2029, 2030])
prezzo_ets = st.sidebar.number_input("Prezzo ETS (€)", value=75.0)
pagato_estero = st.sidebar.number_input("Prezzo Carbonio pagato all'estero (€)", value=0.0)

rotte_dict = {
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
    rotta_label = st.selectbox("Rotta di Produzione", list(rotte_dict.keys()))
    rotta_code = rotte_dict[rotta_label]

with c2:
    st.subheader("2. Emissioni")
    metodo = st.radio("Metodo", ["Default UE", "Dati Reali"])
    is_def = (metodo == "Default UE")
    
    if is_def:
        paesi = sorted(df_def['Country'].unique())
        paese = st.selectbox("Origine", paesi, index=paesi.index("Other Countries and Territories"))
        
        # Selezione colonna H, I o L (2026, 2027, 2028)
        col_d4 = f"{min(2028, anno)} Default Value (Including mark-up)"
        
        # Ricerca D4 con fallback preciso
        d4_row = df_def[(df_def['Country'] == paese) & (df_def['Product CN Code'].astype(str).str.startswith(hs_in[:4]))]
        if d4_row.empty or pd.isna(d4_row.iloc[0][col_d4]):
            d4_row = df_def[(df_def['Country'].str.contains("Other")) & (df_def['Product CN Code'].astype(str).str.startswith(hs_in[:4]))]
        
        d4_val = clean_num(d4_row.iloc[0][col_d4]) if not d4_row.empty else 3.157
        st.info(f"D4 applicato: **{d4_val}**")
    else:
        d4_val = st.number_input("D4 Reale", value=3.157)

# --- CALCOLO ---
d5_val = get_d5(hs_in, anno, is_def, rotta_code, df_bench)
d6_val = 0.975 # Allowance (D6)

costo_tn = ((d4_val - (d5_val * d6_val)) * prezzo_ets) - pagato_estero
totale = max(0.0, costo_tn * vol)

st.divider()
res1, res2, res3 = st.columns(3)
def fmt(n): return f"{n:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

res1.metric("Benchmark D5", f"{d5_val}")
res2.metric("Costo / Ton", f"{fmt(costo_tn)} €")
res3.metric("TOTALE CBAM", f"{fmt(totale)} €")

st.caption(f"Logica: Anno {anno} | Suffix: {'(1)' if anno <= 2027 else '(2)'} | Colonna: {'B' if is_def else 'A'}")