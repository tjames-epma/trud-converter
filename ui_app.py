import streamlit as st
import zipfile
import xml.etree.ElementTree as ET
import pandas as pd
import io
import re
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter

# 1. Page Configuration
st.set_page_config(page_title="TRUD Data Toolkit", page_icon="💊", layout="wide")

# --- 2. PASSWORD GATEKEEPER ---
def check_password():
    if "auth" not in st.secrets:
        st.sidebar.warning("🔓 Local Mode: No secrets found.")
        return True
    def password_entered():
        if st.session_state["password_input"] == st.secrets["auth"]["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password_input"]
        else:
            st.session_state["password_correct"] = False
    if "password_correct" not in st.session_state:
        st.text_input("Please enter the access password", type="password", on_change=password_entered, key="password_input")
        return False
    return st.session_state.get("password_correct", False)

if not check_password():
    st.stop()

# --- 3. LOGIC FUNCTIONS ---

def get_legacy_sheet_name(tag, filename_lower):
    """Maps XML tags to specific sheet names based on user samples."""
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
    if "f_lookup" in filename_lower:
        return tag.replace("InfoType", "").replace("Type", "")
    if "f_vtm" in filename_lower: return "VTM"
    if "f_ingredient" in filename_lower: return "Ingredient"
    if "f_gtin" in filename_lower: return "GTIN"
    return tag.replace("InfoType", "").replace("Type", "")

def process_legacy_xml_to_sheets(xml_content, filename_lower):
    try:
        tree = ET.parse(xml_content)
        root = tree.getroot()
        data_map = {}
        for elem in root.findall(".//*"):
            # Ensure we capture tags even if text is None to identify the presence of columns
            child_data = {child.tag.split('}')[-1]: (child.text if child.text is not None else "") for child in elem}
            if child_data:
                raw_tag = elem.tag.split('}')[-1]
                sheet_name = get_legacy_sheet_name(raw_tag, filename_lower)
                if sheet_name not in data_map: data_map[sheet_name] = []
                data_map[sheet_name].append(child_data)
        
        final_sheets = {}
        for sheet, rows in data_map.items():
            df = pd.DataFrame(rows)
            
            # Explicitly add ABBREVNM if it's missing from the data records
            if sheet in ["AmppType", "VMP", "VTM"] and "ABBREVNM" not in df.columns:
                df["ABBREVNM"] = ""
            
            df = df.drop_duplicates()
            if len(df.columns) > 1:
                # Keep ID and Name columns at the start for usability
                cols = list(df.columns)
                preferred = [c for c in ["APPID", "AMPPID", "VMPID", "VTMID", "NM", "ABBREVNM"] if c in cols]
                others = [c for c in cols if c not in preferred]
                df = df[preferred + others]
                final_sheets[sheet] = df
        return final_sheets
    except:
        return {}

# --- 4. SIDEBAR LOGIC ---
def render_sidebar():
    with st.sidebar:
        st.title("Settings & Info")
        if 'mapped_df' in st.session_state:
            st.divider()
            st.subheader("🔍 Live Search Preview")
            q = st.text_input("Search Name or ID", key="active_search")
            df = st.session_state['mapped_df']
            id_col = st.session_state['id_col']
            if q:
                filtered = df[df['NM'].astype(str).str.contains(q, case=False, na=False) | 
                              df[id_col].astype(str).str.contains(q, case=False, na=False)]
                st.dataframe(filtered[['NM', 'GTIN', id_col]].head(10), hide_index=True)
            else:
                st.dataframe(df[['NM', 'GTIN', id_col]].head(10), hide_index=True)
        st.divider()
        st.caption("v4.5.1 | ABBREVNM Fix")

# --- 5. MAIN UI ---
st.title("💊 TRUD Data Toolkit")
render_sidebar()

uploaded_file = st.file_uploader("Upload TRUD ZIP", type="zip")

if uploaded_file:
    if "last_uploaded" not in st.session_state or st.session_state.last_uploaded != uploaded_file.name:
        st.session_state.last_uploaded = uploaded_file.name
        if 'zip_data' in st.session_state: del st.session_state['zip_data']
        if 'mapped_df' in st.session_state: del st.session_state
