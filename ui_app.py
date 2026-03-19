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
    MATCHES LEGACY SAMPLES: Recursively extracts every data-containing tag.
    Affects ONLY Bulk Legacy Mode.
    """
    try:
        tree = ET.parse(xml_content)
        root = tree.getroot()
        data_map = {}
        
        for elem in root.findall(".//*"):
            # Identify a record container: has children, but children are values (no further children)
            if len(elem) > 0 and all(len(child) == 0 for child in elem):
                raw_tag = elem.tag.split('}')[-1]
                # Clean tag names (e.g., ColourInfoType -> ColourInfo)
                tag_name = raw_tag.replace('InfoType', '').replace('Type', '')
                
                row = {child.tag.split('}')[-1]: child.text for child in elem if child.text is not None}
                if row:
                    if tag_name not in data_map:
                        data_map[tag_name] = []
                    data_map[tag_name].append(row)
        
        files_count = 0
        fn = base_name.split('/')[-1].split('\\')[-1].replace('.xml', '')
        # f_lookup2_123 -> f_lookup
        prefix = re.sub(r'\d+$', '', fn.split('_')[0] + '_' + fn.split('_')[1]) if '_' in fn else fn
        
        for tag, rows in data_map.items():
            if rows:
                df = pd.DataFrame(rows).drop_duplicates()
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
        st.caption("v3.8 | Legacy Export Refined")

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
        options = ["amp", "ampp", "vmp", "vmpp", "vtm", "gtin", "ingredient", "lookup"]
        if 'sel_all' not in st.session_state: st.session_state.sel_all = True
        
        def toggle_select():
            st.session_state.sel_all = not st.session_state.sel_all

        st.button("Toggle Select All/None", on_click=toggle_select)
        selected_files = st.multiselect("Select components:", options, default=options if st.session_state.sel_all else [])

    if st.button("🚀 Run Processor", use_container_width=True):
        try:
            with zipfile.ZipFile(uploaded_file, 'r') as outer_zip:
                all_names = outer_zip.namelist()
                
                if mode == "🔗 GTIN Mapper":
                    with st.status("Mapping...", expanded=True):
                        # GTIN Mapper: Targeted Search (Unchanged)
                        ampp_file = [f for f in all_names if 'f_ampp2' in f.lower() and f.endswith('.xml')][0]
                        ampp_tree = ET.parse(outer_zip.open(ampp_file))
                        ampp_rows = [{c.tag.split('}')[-1]: c.text for c in record} for record in ampp_tree.getroot().findall(".//{*}AMPP")]
                        df_ampp = pd.DataFrame(ampp_rows)
                        id_col = next((c for c in ['AMPPID', 'APPID', 'APID'] if c in df_ampp.columns), None)
                        
                        gtin_zip_path = [f for f in all_names if 'gtin' in f.lower() and f.endswith('.zip')][0]
                        with outer_zip.open(gtin_zip_path) as zd:
                            with zipfile.ZipFile(io.BytesIO(zd.read())) as iz:
                                g_xml = [f for f in iz.namelist() if f.endswith('.xml')][0]
                                g_root = ET.parse(iz.open(g_xml)).getroot()
                                g_rows = []
                                for b in g_root.findall(".//{*}AMPP"):
                                    id_v = b.find(".//{*}AMPPID").text if b.find(".//{*}AMPPID") is not None else b.find(".//{*}APP
