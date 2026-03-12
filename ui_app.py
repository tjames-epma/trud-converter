import streamlit as st
import zipfile
import xml.etree.ElementTree as ET
import pandas as pd
import io
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter

# 1. MUST BE FIRST: Page Configuration
st.set_page_config(page_title="TRUD XML Converter", page_icon="💊", layout="wide")

# --- 2. PASSWORD GATEKEEPER ---
def check_password():
    if "auth" not in st.secrets:
        st.error("Secrets not configured. Please add [auth] section to Streamlit Secrets.")
        return False

    def password_entered():
        if st.session_state["password_input"] == st.secrets["auth"]["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password_input"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Please enter the access password", type="password", on_change=password_entered, key="password_input")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Please enter the access password", type="password", on_change=password_entered, key="password_input")
        st.error("😕 Password incorrect")
        return False
    else:
        return True

if not check_password():
    st.stop()

# --- 3. LOGIC FUNCTIONS ---

def get_ampp_data(zip_obj, file_pattern):
    matches = [f for f in zip_obj.namelist() if file_pattern in f.lower() and f.endswith('.xml')]
    if not matches: return pd.DataFrame()
    with zip_obj.open(matches[0]) as f:
        tree = ET.parse(f)
        root = tree.getroot()
        rows = []
        for record in root.findall(".//{*}AMPP"):
            entry = {child.tag.split('}')[-1]: child.text for child in record if child.text}
            rows.append(entry)
        return pd.DataFrame(rows)

def get_gtin_mapping(zip_obj):
    xml_files = [f for f in zip_obj.namelist() if f.endswith('.xml')]
    if not xml_files: return pd.DataFrame()
    with zip_obj.open(xml_files[0]) as f:
        tree = ET.parse(f)
        root = tree.getroot()
        rows = []
        for ampp_block in root.findall(".//{*}AMPP"):
            amppid_elem = ampp_block.find("{*}AMPPID")
            amppid = amppid_elem.text if amppid_elem is not None else None
            for gtin_data in ampp_block.findall(".//{*}GTINDATA"):
                gtin_elem = gtin_data.find("{*}GTIN")
                if gtin_elem is not None and amppid:
                    rows.append({'AMPPID': amppid, 'GTIN': gtin_elem.text})
        return pd.DataFrame(rows)

# --- 4. USER INTERFACE ---

with st.sidebar:
    st.title("Settings & Info")
    st.info("Mapping TRUD AMPP records (NM) to GTINs.")
    st.divider()
    st.subheader("🔍 Quick Drug Search")
    lookup_query = st.text_input("Search Drug Name (NM)", help="Type part of a name and press Enter after processing.")
    st.divider()
    st.caption("v1.4.4 | Built for EPMA Data Team")

st.title
