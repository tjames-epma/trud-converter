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
    st.caption("v6.9.8 | Flat Build")

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
                                with outer.open(f) as zd, zipfile.ZipFile(io.BytesIO(zd.read())) as iz:
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
                            pb.
