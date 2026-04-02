import streamlit as st
import zipfile
import xml.etree.ElementTree as ET
import pandas as pd
import io
import re

# 1. Page Config - Must be absolute first
st.set_page_config(page_title="TRUD Data Toolkit", page_icon="💊", layout="wide")

# --- 2. THE GATEKEEPER ---
if "password_correct" not in st.session_state:
    st.title("🔐 Access Required")
    pwd = st.text_input("Please enter the access password", type="password")
    if st.button("Sign In"):
        if "auth" in st.secrets and pwd == st.secrets["auth"]["password"]:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("Invalid password")
    st.stop()

# --- 3. LOGIC FUNCTIONS ---

def get_legacy_sheet_name(tag, filename_lower):
    tag = tag.split('}')[-1]
    if "f_ampp" in filename_lower:
        mapping = {"AMPP": "AmppType", "PACK_INFO": "PackInfoType", "CONTENT": "ContentType", 
                   "PRESC_INFO": "PrescInfoType", "PRICE_INFO": "PriceInfoType", "REIMB_INFO": "ReimbInfoType"}
        return mapping.get(tag, tag)
    return tag.replace("Type", "")

def process_legacy_xml_to_sheets(xml_content, filename_lower):
    try:
        data_map = {}
        context = ET.iterparse(xml_content, events=("end",))
        for event, elem in context:
            tag_name = elem.tag.split('}')[-1]
            sheet_name = get_legacy_sheet_name(tag_name, filename_lower)
            if len(elem) > 0:
                child_data = {child.tag.split('}')[-1]: (child.text if child.text else "") for child in elem}
                if sheet_name not in data_map:
                    data_map[sheet_name] = []
                data_map[sheet_name].append(child_data)
            elem.clear()

        final_sheets = {}
        for sheet, rows in data_map.items():
            df = pd.DataFrame(rows).drop_duplicates()
            # Mandatory Column Fix
            if sheet in ["AmppType", "VMP", "VTM"] and "ABBREVNM" not in df.columns:
                df["ABBREVNM"] = ""
            
            if len(df.columns) > 1:
                cols = list(df.columns)
                head = [c for c in ["APPID", "AMPPID", "VMPID", "VTMID", "NM", "ABBREVNM"] if c in cols]
                rest = [c for c in cols if c not in head]
                final_sheets[sheet] = df[head + rest]
        return final_sheets
    except:
        return {}

# --- 4. MAIN UI ---

st.title("💊 TRUD Data Toolkit")

with st.sidebar:
    st.subheader("App Controls")
    if st.button("Logout / Reset App"):
        st.session_state.clear()
        st.rerun()
    st.divider()
    st.caption("v6.8 | UI Persistence Build")

uploaded_file = st.file_uploader("📤 Drop TRUD ZIP file here", type="zip")

if uploaded_file:
    st.divider()
    mode = st.radio("**Select Action:**", ["📦 Bulk Export", "🔗 GTIN Mapper"], horizontal=True)

    # Persistent selection logic
    selected_files = []
    if mode == "📦 Bulk Export":
        st.subheader("Filter Components")
        options = ["amp", "ampp", "vmp", "vmpp", "vtm", "gtin", "ingredient", "lookup"]
        selected_files = st.multiselect("Select components to include:", options, default=options)
    
    # Ensure button is visible as long as file is present
    if st.button("🚀 Run Processor", use_container_width=True):
        try:
            with zipfile.ZipFile(uploaded_file, 'r') as outer_zip:
                all_names = outer_zip.namelist()
                buf = io.BytesIO()
                
                if mode == "📦 Bulk Export":
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
                        xml_worklist = []
                        for f in all_names:
                            fn_l = f.lower()
                            if any(f"f_{o}" in fn_l for o in selected_files) and f.endswith('.xml'):
                                xml_worklist.append((f, outer_zip.open(f)))
                            elif fn_l.endswith('.zip') and any(o in fn_l for o in selected_files):
                                with outer_zip.open(f) as zd_inner:
                                    with zipfile.ZipFile(io.BytesIO(zd_inner.read())) as iz_inner:
                                        for iname in iz_inner.namelist():
                                            if iname.endswith('.xml'):
                                                xml_worklist.append((iname, io.BytesIO(iz_inner.read(iname))))

                        total_files = len(xml_worklist)
                        if total_files == 0:
                            st.warning("No files matched your selection.")
                        else:
                            for i, (name, data) in enumerate(xml_worklist):
                                status_text.text(f"Processing {i+1} of {total_files}: {name}")
                                sheets = process_legacy_xml_to_sheets(data, name.lower())
                                if sheets:
                                    xl_buf = io.BytesIO()
                                    with pd.ExcelWriter(xl_buf) as writer:
                                        for s_name, s_df in sheets.items():
                                            s_df.to_excel(writer, index=False, sheet_name=s_name[:31])
                                    clean_fn = re.sub(r'\d+', '', name.split('/')[-1].split('.')[0]).strip('_') + ".xlsx
