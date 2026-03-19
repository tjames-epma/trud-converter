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

def xml_to_excel_buffer(df, sheet_name):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
    return output.getvalue()

def split_and_zip_xml_recursive(xml_content, zip_out, base_name):
    """
    MATCHES LEGACY SAMPLES:
    Recursively extracts every data-containing tag into its own file.
    """
    try:
        tree = ET.parse(xml_content)
        root = tree.getroot()
        data_map = {}
        
        # Scans every element in the XML tree
        for elem in root.findall(".//*"):
            # A data record is a tag that has children but those children have no children (leaf nodes)
            if len(elem) > 0 and all(len(child) == 0 for child in elem):
                raw_tag = elem.tag.split('}')[-1]
                
                # Clean up tag names to match samples (removing 'InfoType', 'Type' etc)
                tag_name = raw_tag.replace('InfoType', '').replace('Type', '')
                
                row = {child.tag.split('}')[-1]: child.text for child in elem if child.text is not None}
                if row:
                    if tag_name not in data_map:
                        data_map[tag_name] = []
                    data_map[tag_name].append(row)
        
        files_count = 0
        prefix = base_name.split('/')[-1].split('\\')[-1].replace('.xml', '')
        # Handle the f_prefix2 numbering often found in TRUD
        prefix = re.sub(r'\d+$', '', prefix.split('_')[0] + '_' + prefix.split('_')[1]) if '_' in prefix else prefix
        
        for tag, rows in data_map.items():
            df = pd.DataFrame(rows).drop_duplicates()
            xlsx_data = xml_to_excel_buffer(df, tag)
            # Example: f_lookup_ColourInfo.xlsx
            new_fn = f"{prefix}_{tag}.xlsx"
            zip_out.writestr(new_fn, xlsx_data)
            files_count += 1
        return files_count
    except Exception:
        return 0

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
        st.caption("v3.7 | Legacy Specs Match")

# --- 5. MAIN UI ---
st.title("💊 TRUD Data Toolkit")
render_sidebar()

uploaded_file = st.file_uploader("Upload TRUD ZIP", type="zip")

if uploaded_file:
    if "last_uploaded" not in st.session_state or st.session_state.last_uploaded != uploaded_file.name:
        st.session_state.last_uploaded = uploaded_file.name
        if 'zip_data' in st.session_state: del st.session_state['zip_data']
        if 'mapped
