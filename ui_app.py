import streamlit as st
import zipfile
import xml.etree.ElementTree as ET
import pandas as pd
import io
import re

# 1. Page Config - MUST be absolute first
st.set_page_config(page_title="TRUD Data Toolkit", page_icon="💊", layout="wide")

# --- 2. STABLE PASSWORD GATE ---
def check_password():
    if "auth" not in st.secrets:
        return True
    if st.session_state.get("password_correct"):
        return True

    st.title("🔐 Access Required")
    pwd = st.text_input("Please enter the access password", type="password")
    if st.button("Sign In"):
        if pwd == st.secrets["auth"]["password"]:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("Invalid password")
    return False

# --- 3. PROCESSING LOGIC ---

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
            if sheet in ["AmppType", "VMP", "VTM"] and "ABBREVNM" not in df.columns:
                df["ABBREVNM"] = ""
            if len(df.columns) > 1:
                cols = list(df.columns)
                head = [c for c in ["APPID", "AMPPID", "NM", "ABBREVNM"] if c in cols]
                rest = [c for c in cols if c not in head]
                final_sheets[sheet] = df[head + rest]
        return final_sheets
    except:
        return {}

# --- 4. MAIN APP ---

def main():
    if not check_password():
        st.stop()

    st.title("💊 TRUD Data Toolkit")
    
    with st.sidebar:
        st.caption("v5.8 | Syntax Fix")
        if st.button("Logout / Clear Session"):
            st.session_state.clear()
            st.rerun()

    uploaded_file = st.file_uploader("Upload TRUD ZIP", type="zip")

    if uploaded_file:
        mode = st.radio("**Select Action:**", ["📦 Bulk Export", "🔗 GTIN Mapper"])

        if st.button("🚀 Run Processor", use_container_width=True):
            try:
                with zipfile.ZipFile(uploaded_file, 'r') as outer_zip:
                    all_names = outer_zip.namelist()
                    buf = io.BytesIO()
                    
                    if mode == "📦 Bulk Export":
                        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
                            xml_worklist = []
                            for f in all_names:
                                if f.lower().endswith('.xml'):
                                    xml_worklist.append((f, outer_zip.open(f)))
                                elif f.lower().endswith('.zip'):
                                    with outer_zip.open(f) as zd_inner:
                                        with zipfile.ZipFile(io.BytesIO(zd_inner.read())) as iz_inner:
                                            for iname in iz_inner.namelist():
                                                if iname.endswith('.xml'):
                                                    xml_worklist.append((iname, io.BytesIO(iz_inner.read(iname))))

                            for name, data in xml_worklist:
                                sheets = process_legacy_xml_to_sheets(data, name.lower())
                                if sheets:
                                    xl_buf = io.BytesIO()
                                    with pd.ExcelWriter(xl_buf) as writer:
                                        for s_name, s_df in sheets.items():
                                            s_df.to_excel(writer, index=False, sheet_name=s_name[:31])
                                    clean_fn = re.sub(r'\d+', '', name.split('/')[-1].split('.')[0]) + ".xlsx"
                                    zout.writestr(clean_fn, xl_buf.getvalue())
                        
                        st.session_state['zip_data'] = buf.getvalue()
                        st.session_state['file_name'] = "TRUD_Export.zip"
