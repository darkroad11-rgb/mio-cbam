import streamlit as st
import pandas as pd
import numpy as np
import os
import re
import xml.etree.ElementTree as ET
from io import BytesIO

st.set_page_config(page_title="CBAM Pro: Calculator & Export", layout="wide")

# --- FUNZIONI DI PULIZIA E SUPPORTO ---

def pulisci_numero(val):
    if pd.isna(val) or str(val).strip() in ["", "#VALUE!", "nan", "NaN"]:
        return 0.0
    if isinstance(val, str):
        val = val.strip().replace(",", ".")
        val = re.sub(r'[^\d.-]', '', val)
        try: return float(val)
        except: return 0.0
    return float(val)

def estrai_solo_lettera(val):
    if pd.isna(val) or str(val).strip().lower() in ["nan", "val", ""]:
        return "Standard"
    match = re.search(r'\(([A-Z])\)', str(val))
    if match: return match.group(1)
    return str(val)

# --- FUNZIONE GENERAZIONE XML PER REGISTRO UE ---

def genera_xml_cbam(dati):
    """Genera un file XML basato sui requisiti del Registro UE."""
    root = ET.Element("CBAM_Report")
    header = ET.SubElement(root, "Header")
    ET.SubElement(header, "Year").text = str(dati['anno'])
    
    body = ET.SubElement(root, "Goods_Declarations")
    item = ET.SubElement(body, "Good")
    
    # Mappatura campi tecnici
    ET.SubElement(item, "CN_Code").text = dati['hs']
    ET.SubElement(item, "Country_of_Origin").text = dati['paese']
    ET.SubElement(item, "Net_Mass_Tonne").text = f"{dati['volume']:.3f}"
    
    emissions = ET.SubElement(item, "Emissions_Data")
    ET.SubElement(emissions, "Specific_Direct_Emissions").text = f"{dati['emiss_f']:.4f}"
    ET.SubElement(emissions, "Benchmark_Applied").text = f"{dati['bm_val']:.4f}"
    ET.SubElement(emissions, "Type").text = dati['tipo_info']

    # Trasformazione in stringa XML
    tree = ET.ElementTree(root)
    buffer = BytesIO()
    tree.write(buffer, encoding='utf-8', xml_declaration=True)
    return buffer.getvalue()

# --- CARICAMENTO DATI ---

@st.cache_data
def load_data():
    files = os.listdir(".")
    f_bench = next((f for f in files if "bench" in f.lower() and f.endswith(".csv")), None)
    f_def = next((f for f in files if "default" in f.lower() and f.endswith(".csv")), None)

    if not f_bench or not f_def:
        st.error("File CSV non trovati!")
        st.stop()

    df_b = pd.read_csv(f_bench, sep=";", engine='python', on_bad_lines='skip')
    df_d = pd.read_csv(f_def, sep=",", engine='python', on_bad_lines='skip')
    
    df_b.columns = df_b.columns.str.strip().str.replace('\n', ' ')
    df_d.columns = df_d.columns.str.strip().str.replace('\n', ' ')

    col_hs_b = next(c for c in df_b.columns if "CN code" in c)
    df_b[col_hs_b] = df_b[col_hs_b].ffill().astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    col_hs_d = next(c for c in df_d.columns if "CN Code" in c)
    df_d[col_hs_d] = df_d[col_hs_d].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    col_paese = next((c for c in df_d.columns if "country" in c.lower()), df_d.columns[0])

    return df_b, df_d, col_hs_b, col_hs_d, col_paese

try:
    bench, defaults, HS_B, HS_D, COL_PAESE = load_data()
except Exception as e:
    st.error(f"Errore: {e}"); st.stop()

# --- INTERFACCIA ---

st.title("🛡️ CBAM Pro: Calcolo & Export Doganale")

with st.sidebar:
    st.header("1. Input Spedizione")
    anno = st.selectbox("Anno", [2026, 2027, 2028, 2029, 2030])
    periodo_req = "(1)" if anno <= 2027 else "(2)"
    paese_sel = st.selectbox("Origine", sorted(defaults[COL_PAESE].unique()))
    hs_sel = st.selectbox("Codice HS", sorted(bench[HS_B].unique()))
    volume = st.number_input("Tonnellate", min_value=0.0, value=1.0)
    reali = st.number_input("Emissioni Reali", min_value=0.0, format="%.4f")
    prezzo_ets = st.number_input("Prezzo ETS (€)", value=80.0)

# --- LOGICA DI CALCOLO GERARCHICO ---

# 1. Benchmark
usare_reali = reali > 0
pref = "Column A" if usare_reali else "Column B"
col_bmg = next(c for c in bench.columns if pref in c and "BMg" in c)
col_ind = next(c for c in bench.columns if pref in c and "indicator" in c)

df_hs = bench[bench[HS_B] == hs_sel]
df_valido = df_hs[df_hs[col_ind].apply(lambda x: periodo_req in str(x) or ("(1)" not in str(x) and "(2)" not in str(x)))]

benchmark_val = 0.0
if len(df_valido) > 1:
    mappa_rotte = {estrai_solo_lettera(r[col_ind]): pulisci_numero(r[col_bmg]) for _, r in df_valido.iterrows()}
    scelta_r = st.selectbox("Seleziona Rotta di Produzione:", list(mappa_rotte.keys()))
    benchmark_val = mappa_rotte[scelta_r]
else:
    benchmark_val = pulisci_numero(df_valido[col_bmg].iloc[0]) if not df_valido.empty else 0.0

# 2. Emissioni Incorporate (Match 8-6-4 cifre)
emiss_f = 0.0; tipo_info = ""
col_yr = next(c for c in defaults.columns if str(min(anno, 2028)) in c)

if usare_reali:
    emiss_f = reali; tipo_info = "Dato Reale"
else:
    for lung in [8, 6, 4]:
        pref_hs = hs_sel[:lung]
        subset = defaults[defaults[HS_D].str.startswith(pref_hs)]
        row_p = subset[subset[COL_PAESE] == paese_sel]
        val = pulisci_numero(row_p[col_yr].iloc[0]) if not row_p.empty else np.nan
        if pd.isna(val):
            row_o = subset[subset[COL_PAESE].str.contains("Other", case=False, na=False)]
            val = pulisci_numero(row_o[col_yr].iloc[0]) if not row_o.empty else np.nan
        if not pd.isna(val):
            emiss_f = val; tipo_info = f"Default - Match {lung} cifre"; break

# --- CALCOLO COSTO ---
fa_perc = 97.5 if anno <= 2026 else (95.0 if anno == 2027 else 92.5)
quota_esente = (benchmark_val or 0.0) * (fa_perc / 100)
costo_tot = max(0, emiss_f - quota_esente) * volume * prezzo_ets

# --- DISPLAY E EXPORT ---
st.divider()
c1, c2, c3 = st.columns(3)
c1.metric("Emissioni incorporate", f"{emiss_f:.4f}", tipo_info)
c2.metric("Soglia Esente", f"{quota_esente:.4f}", f"FA: {fa_perc}%")
c3.metric("Debito CBAM", f"€ {costo_tot:,.2f}")

st.divider()
st.subheader("📦 Export per la Dogana")

# Preparazione dati per XML
dati_per_xml = {
    'anno': anno, 'hs': hs_sel, 'paese': paese_sel,
    'volume': volume, 'emiss_f': emiss_f, 'bm_val': benchmark_val,
    'tipo_info': tipo_info
}

xml_data = genera_xml_cbam(dati_per_xml)

st.write("Scarica il file XML pronto per l'upload sul Registro UE (Transitional Registry).")
st.download_button(
    label="💾 Scarica XML per Registro UE",
    data=xml_data,
    file_name=f"CBAM_Report_{hs_sel}_{paese_sel}.xml",
    mime="application/xml",
    help="Risparmia tempo caricando direttamente questo file nel portale doganale."
)



















