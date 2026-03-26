import streamlit as st
import zipfile
import xml.etree.ElementTree as ET
import pandas as pd
import io
import re

# RULE 1: set_page_config must be the FIRST Streamlit command.
# Do not place ANY st. commands above this.
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
                    if sheet_name not in data_map:
                        data_map[sheet_name] = []
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
    except Exception as e:
        st.error(f"Error processing {filename_lower}: {e}")
        return {}

# --- 4. WRAPPER FOR MAIN APP ---

def main():
    if not check_password():
        st.stop()

    st.title("💊 TRUD Data Toolkit")
    
    with st.sidebar:
        st.title("Settings")
        if 'mapped_df' in st.session_state:
            st.divider()
            st.subheader("🔍 Quick Search")
            q = st.text_input("Name or ID")
            df = st.session
