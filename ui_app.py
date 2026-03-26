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
    return tag.replace("InfoType", "").replace
