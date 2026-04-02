import streamlit as st
import zipfile
import xml.etree.ElementTree as ET
import pandas as pd
import io
import re

# 1. Page Configuration - MUST be first
st.set_page_config(page_title="TRUD Data Toolkit", page_icon="💊", layout="wide")

# --- 2. PASSWORD GATEKEEPER ---
def check_password():
    if "auth" not in st.secrets:
        return True
    if "password_correct" not in st.session_state:
        def password_entered():
            if st.session_state["password_input"] == st.secrets["auth"]["password"]:
                st.session_state["password_correct"] = True
                del st.session_state["password_input"]
            else:
                st.session_state["password_correct"] = False
        st.text_input("Please enter the access password", type="password", on_change=password_entered, key="password_input")
        return False
    return st.session_state.get("password_correct", False)

if not check_password():
    st.stop()

# --- 3. LOGIC FUNCTIONS ---

def get_legacy_sheet_name(tag, filename_lower):
    tag = tag.split('}')[-1]
    if "f_ampp" in filename_lower:
        mapping = {"AMPP": "AmppType", "PACK_INFO": "PackInfoType", "CONTENT": "ContentType", 
                   "CCONTENT": "ContentType", "PRESC_INFO": "PrescInfoType", 
                   "PRICE_INFO": "PriceInfoType", "REIMB_INFO": "ReimbInfoType"}
        return mapping.get(tag, tag)
    if "f_amp" in filename_lower and not "ampp" in filename_lower:
        mapping = {"AMP": "AmpType", "API": "ApiType", "LIC_ROUTE": "LicRouteType", "APP_PROD_INFO": "AppProdInfoType"}
        return mapping.get(tag, tag)
    if "f_vmp" in filename_lower and not "vmpp" in filename_lower:
        mapping = {"VMP": "VMP", "VPI": "VPI", "ONT_DRUG_FORM": "OntDrugForm",
                   "DRUG_FORM": "DrugForm", "DRUG_ROUTE": "DrugRoute", "CONTROL_INFO": "Control"}
        return mapping.get(tag, tag)
    if "f_vmpp" in filename_lower:
        mapping = {"VMPP": "VMPP", "DT_INFO": "DtInfo", "CONTENT": "CContent", "CCONTENT": "CContent"}
        return mapping.get(tag, tag)
    return tag.replace("InfoType", "").replace("Type", "")

def process_xml_streamed(xml_file, filename_lower):
    """Memory-safe XML parsing using iterparse."""
    try:
        data_map = {}
        context = ET.iterparse(xml_file, events=("end",))
        for event, elem in context:
            tag_name = elem.tag.split('}')[-1]
            sheet_name = get_legacy_sheet_name(tag_name, filename_lower)
            if len(elem) > 0:
                child_data = {child.tag.split('}')[-1]: (child.text if child.text is not None else "") for child in elem}
                if child_data:
                    if sheet_name not in data_map: data_map[sheet_name] = []
                    data_map[sheet_name].append(child_data)
            elem.clear() # Clear memory
        
        final_sheets = {}
        for sheet, rows in data_map.items():
            df = pd.DataFrame(rows)
            if sheet in ["AmppType", "VMP", "VTM"] and "ABBREVNM" not in df.columns:
                df["ABBREVNM"] = ""
            df = df.drop_duplicates()
            if len(df.columns) > 1:
                cols = list(df.columns)
                preferred = [c for c in ["APPID", "AMPPID", "VMPID", "VTMID", "NM", "ABBREVNM"] if c in cols]
                others = [c for c in cols if c not in preferred]
                df = df[preferred + others]
                final_sheets[sheet] = df
        return final_sheets
    except: return {}

# --- 4. MAIN UI ---
st.title("💊 TRUD Data Toolkit")

uploaded_file = st.file_uploader("Upload TRUD ZIP", type="zip")

if uploaded_file:
    mode = st.radio("**Select Action:**", ["📦 Bulk Multi-File (Legacy)", "🔗 GTIN Mapper"])

    if st.button("🚀 Run Processor", use_container_width=True):
        try:
            with zipfile.ZipFile(uploaded_file, 'r') as outer_zip:
                all_names = outer_zip.namelist()
                buf = io.BytesIO()
                
                if mode == "📦 Bulk Multi-File (Legacy)":
                    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
                        xml_worklist = []
                        for f in all_names:
                            if f.lower().endswith('.xml'): xml_worklist.append((f, outer_zip.open(f)))
                            elif f.lower().endswith('.zip'):
                                with outer_zip.open(f) as zd:
                                    with zipfile.ZipFile(io.BytesIO(zd.read())) as iz:
                                        for iname in iz.namelist():
                                            if iname.endswith('.xml'): xml_worklist.append((iname, io.BytesIO(iz.read(iname))))
                        
                        for name, data in xml_worklist:
                            sheets = process_xml_streamed(data, name.lower())
                            if sheets:
                                ex_buf = io.BytesIO()
                                with pd.ExcelWriter(ex_buf, engine='openpyxl') as writer:
                                    for s_name, s_df in sheets.items():
                                        s_df.to_excel(writer, index=False, sheet_name=s_name[:31])
                                clean_fn = re.sub(r'\d+', '', name.split('/')[-1].split('.')[0]) + ".xlsx"
                                zout.writestr(clean_fn, ex_buf.getvalue())
                    
                    st.session_state['out_data'] = buf.getvalue()
                    st.session_state['out_name'] = "TRUD_Export.zip"

                else: # GTIN Mapper
                    ampp_f = [f for f in all_names if 'f_ampp2' in f.lower()]
