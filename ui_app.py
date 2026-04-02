import streamlit as st
import zipfile
import xml.etree.ElementTree as ET
import pandas as pd
import io
import re

# 1. Page Config
st.set_page_config(page_title="TRUD Data Toolkit", page_icon="💊", layout="wide")

# --- 2. THE GATEKEEPER ---
if "password_correct" not in st.session_state:
    st.title("🔐 Access Required")
    pwd = st.text_input("Please enter password", type="password")
    if st.button("Sign In"):
        if "auth" in st.secrets and pwd == st.secrets["auth"]["password"]:
            st.session_state["password_correct"] = True
            st.rerun()
        else: st.error("Invalid password")
    st.stop()

# --- 3. LOGIC FUNCTIONS ---
def get_legacy_sheet_name(tag, fn):
    tag = tag.split('}')[-1]
    if "f_ampp" in fn:
        m = {"AMPP": "AmppType", "PACK_INFO": "PackInfoType", "CONTENT": "ContentType", 
             "PRESC_INFO": "PrescInfoType", "PRICE_INFO": "PriceInfoType", "REIMB_INFO": "ReimbInfoType"}
        return m.get(tag, tag)
    return tag.replace("Type", "")

def process_xml(xml_content, fn):
    try:
        data_map = {}
        for ev, elem in ET.iterparse(xml_content, events=("end",)):
            tag = elem.tag.split('}')[-1]
            sheet = get_legacy_sheet_name(tag, fn)
            if len(elem) > 0:
                child_data = {c.tag.split('}')[-1]: (c.text or "") for c in elem}
                if sheet not in data_map: data_map[sheet] = []
                data_map[sheet].append(child_data)
            elem.clear()
        final = {}
        for s, rows in data_map.items():
            df = pd.DataFrame(rows).drop_duplicates()
            if s in ["AmppType", "VMP", "VTM"] and "ABBREVNM" not in df.columns: df["ABBREVNM"] = ""
            if len(df.columns) > 1:
                cols = list(df.columns)
                head = [c for c in ["APPID", "AMPPID", "VMPID", "VTMID", "NM", "ABBREVNM"] if c in cols]
                final[s] = df[head + [c for c in cols if c not in head]]
        return final
    except: return {}

# --- 4. MAIN UI ---
st.title("💊 TRUD Data Toolkit")
with st.sidebar:
    if st.button("Reset App"):
        st.session_state.clear()
        st.rerun()
    st.caption("v6.9.9 | GTIN Data Type Fix")

uploaded_file = st.file_uploader("📤 Drop TRUD ZIP here", type="zip")

if uploaded_file:
    mode = st.radio("Action", ["📦 Bulk Export", "🔗 GTIN Mapper"], horizontal=True)
    sel = st.multiselect("Filters", ["amp", "ampp", "vmp", "vmpp", "vtm", "gtin", "lookup"], default=["amp", "ampp", "vmp", "vmpp", "vtm"]) if mode == "📦 Bulk Export" else []

    if st.button("🚀 Run Processor", use_container_width=True):
        try:
            with zipfile.ZipFile(uploaded_file, 'r') as outer:
                names = outer.namelist(); buf = io.BytesIO()
                pb = st.progress(0); txt = st.empty()
                
                if mode == "📦 Bulk Export":
                    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
                        work = []
                        for f in names:
                            if any(f"f_{o}" in f.lower() for o in sel) and f.endswith('.xml'): work.append((f, outer.open(f)))
                            elif f.lower().endswith('.zip') and any(o in f.lower() for o in sel):
                                with outer_zip.open(f) as zd, zipfile.ZipFile(io.BytesIO(zd.read())) as iz:
                                    for i in iz.namelist():
                                        if i.endswith('.xml'): work.append((i, io.BytesIO(iz.read(i))))
                        for i, (n, d) in enumerate(work):
                            txt.text(f"File {i+1}/{len(work)}: {n}")
                            sheets = process_xml(d, n.lower())
                            if sheets:
                                xl_b = io.BytesIO()
                                with pd.ExcelWriter(xl_b) as wr:
                                    for sn, sdf in sheets.items(): sdf.to_excel(wr, index=False, sheet_name=sn[:31])
                                zout.writestr(re.sub(r'\d+', '', n.split('/')[-1].split('.')[0]).strip('_') + ".xlsx", xl_b.getvalue())
                            pb.progress((i + 1) / len(work))
                    st.session_state.zip_data, st.session_state.file_name = buf.getvalue(), "TRUD_Bulk.zip"

                elif mode == "🔗 GTIN Mapper":
                    txt.text("1/3: Reading AMPP..."); ampp_f = [f for f in names if 'f_ampp2' in f.lower()][0]
                    rows = []
                    for ev, el in ET.iterparse(outer.open(ampp_f), events=("end",)):
                        if el.tag.split('}')[-1] == 'AMPP': rows.append({c.tag.split('}')[-1]: (c.text or "") for c in el})
                        el.clear()
                    df_ampp = pd.DataFrame(rows); pb.progress(33)
                    
                    txt.text("2/3: Reading GTIN..."); gtin_z = [f for f in names if 'gtin' in f.lower() and f.endswith('.zip')][0]
                    g_rows = []
                    with outer.open(gtin_z) as zd, zipfile.ZipFile(io.BytesIO(zd.read())) as iz:
                        g_xml = [f for f in iz.namelist() if f.endswith('.xml')][0]
                        for ev, el in ET.iterparse(iz.open(g_xml), events=("end",)):
                            if el.tag.split('}')[-1] in ['AMPP', 'APP']:
                                id_el = el.find(".//{*}AMPPID") or el.find(".//{*}APPID") or el.find(".//{*}ID")
                                if id_el is not None and id_el.text:
                                    for gd in el.findall(".//{*}GTINDATA"):
                                        gtin = gd.find(".//{*}GTIN")
                                        if gtin is not None and gtin.text: g_rows.append({'JOIN_ID': str(id_el.text), 'GTIN': str(gtin.text)})
                            el.clear()
                    df_gtin = pd.DataFrame(g_rows) if g_rows else pd.DataFrame(columns=['JOIN_ID', 'GTIN']); pb.progress(66)
                    
                    txt.text("3/3: Merging..."); id_col = next((c for c in ['AMPPID', 'APPID'] if c in df_ampp.columns), None)
                    if id_col and not df_gtin.empty:
                        # Force string type on both sides to prevent empty merge
                        df_ampp[id_col] = df_ampp[id_col].astype(str)
                        df_gtin['JOIN_ID'] = df_gtin['JOIN_ID'].astype(str)
                        
                        final = pd.merge(df_ampp, df_gtin, left_on=id_col, right_on='JOIN_ID', how='inner')
                        if 'JOIN_ID' in final.columns: final = final.drop(columns=['JOIN_ID'])
                        
                        xl_b = io.BytesIO()
                        with pd.ExcelWriter(xl_b) as wr: final.to_excel(wr, index=False)
                        st.session_state.zip_data, st.session_state.file_name = xl_b.getvalue(), "GTIN_Mapped.xlsx"
                    else:
                        st.warning("No matches found. Check if the ZIP contains the correct dm+d files.")
                    pb.progress(100)
                txt.empty(); pb.empty()
        except Exception as e: st.error(f"❌ Error: {e}")

if 'zip_data' in st.session_state:
    st.divider()
    st.download_button(f"📥 Download {st.session_state.file_name}", st.session_state.zip_data, st.session_state.file_name, use_container_width=True)
