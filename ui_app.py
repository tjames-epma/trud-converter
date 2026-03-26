import streamlit as st
import zipfile
import xml.etree.ElementTree as ET
import pandas as pd
import io
import re

# 1. Essential Config - MUST be first
st.set_page_config(page_title="TRUD Data Toolkit", page_icon="💊", layout="wide")

# 2. Stable Auth Logic
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

# 3. Memory-Safe Streaming Logic
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
    if "f_lookup" in filename_lower:
        return tag.replace("InfoType", "").replace("Type", "")
    if "f_vtm" in filename_lower: return "VTM"
    if "f_ingredient" in filename_lower: return "Ingredient"
    if "f_gtin" in filename_lower: return "GTIN"
    return tag.replace("InfoType", "").replace("Type", "")

def process_legacy_xml_to_sheets(xml_file_obj, filename_lower):
    try:
        data_map = {}
        context = ET.iterparse(xml_file_obj, events=("end",))
        for event, elem in context:
            tag_name = elem.tag.split('}')[-1]
            sheet_name = get_legacy_sheet_name(tag_name, filename_lower)
            if len(elem) > 0:
                child_data = {child.tag.split('}')[-1]: (child.text if child.text is not None else "") for child in elem}
                if child_data:
                    if sheet_name not in data_map: data_map[sheet_name] = []
                    data_map[sheet_name].append(child_data)
            elem.clear()
        
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
    except:
        return {}

# 4. Main App Logic
def main():
    if not check_password():
        st.stop()

    st.title("💊 TRUD Data Toolkit")
    
    # --- Sidebar Configuration ---
    with st.sidebar:
        st.header("App Settings")
        mode = st.radio("Tool Mode", ["📦 Bulk Multi-File", "🔗 GTIN Mapper"])
        
        selected_files = []
        if mode == "📦 Bulk Multi-File":
            st.divider()
            st.subheader("Filter Components")
            options = ["amp", "ampp", "vmp", "vmpp", "vtm", "gtin", "ingredient", "lookup"]
            selected_files = st.multiselect("Include in export:", options, default=options)

        st.divider()
        if st.button("Logout / Reset App"):
            st.session_state.clear()
            st.rerun()

    # --- Main UI ---
    uploaded_file = st.file_uploader("Upload TRUD ZIP", type="zip")

    if uploaded_file
