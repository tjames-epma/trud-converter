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

def legacy_recursive_splitter(xml_content, zip_out, base_name):
    """
    MATCHES SAMPLES: Recursively finds every data container tag.
    Example: Finds BasisOfStrength, ColourInfo, Route, etc.
    """
    try:
        tree = ET.parse(xml_content)
        root = tree.getroot()
        data_map = {}
        
        # We walk through every single element in the XML
        for elem in root.findall(".//*"):
            # Check if this element contains child tags with text values
            # This identifies the 'rows' in your sample files
            child_data = {child.tag.split('}')[-1]: child.text for child in elem if child.text is not None}
            
            if child_data:
                tag_name = elem.tag.split('}')[-1]
                # Clean up names to match samples (removing InfoType and Type)
                clean_name = tag_name.replace('InfoType', '').replace('Type', '')
                
                if clean_name not in data_map:
                    data_map[clean_name] = []
                data_map[clean_name].append(child_data)
        
        files_count = 0
        # Determine prefix (e.g., f_lookup)
        fn_raw = base_name.split('/')[-1].split('\\')[-1].replace('.xml', '')
        parts = fn_raw.split('_')
        prefix = f"{parts[0]}_{parts[1]}" if len(parts) > 1 else parts[0]
        prefix = re.sub(r'\d+$', '', prefix) # Remove the '2' from 'f_lookup2'
        
        for tag, rows in data_map.items():
            # Only export tags that represent actual tables (more than 1 row or multiple columns)
            if len(rows) > 0:
                df = pd.DataFrame(rows).drop_duplicates()
                # Skip the high-level root wrappers (usually have very few columns)
                if len(df.columns) > 1:
                    xlsx_data = xml_to_excel_buffer(df, tag)
                    zip_out.writestr(f"{prefix}_{tag}.xlsx", xlsx_data)
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
        st.caption("v3.9 | Sample Match Build")

# --- 5. MAIN UI ---
st.title("💊 TRUD Data Toolkit")
render_sidebar()

uploaded_file = st.file_uploader("Upload TRUD ZIP", type="zip")

if uploaded_file:
    if "last_uploaded" not in st.session_state or st.session_state.last_uploaded != uploaded_file.name:
        st.session_state.last_uploaded = uploaded_file.name
        if 'zip_data' in st.session_state: del st.session_state['zip_data']
        if 'mapped_df' in st.session_state: del st.session_state['mapped_df']

    date_match = re.search(r'_(\d{8})', uploaded_file.name)
    file_date = date_match.group(1) if date_match else "Processed"

    mode = st.radio("**Select Action:**", ["🔗 GTIN Mapper", "📦 Bulk Multi-File (Legacy)"])

    if mode == "📦 Bulk Multi-File (Legacy)":
        st.subheader("Filter Exports")
        options = ["amp", "ampp", "vmp", "vmpp", "vtm", "gtin
