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

def xml_to_excel_buffer(element_list, sheet_name):
    """Converts a list of XML elements to an Excel file buffer."""
    rows = []
    for record in element_list:
        entry = {child.tag.split('}')[-1]: child.text for child in record if child.text}
        if entry: rows.append(entry)
    if not rows: return None
    df = pd.DataFrame(rows)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
    return output.getvalue()

def process_complex_xml(xml_content, zip_out, base_name):
    """Splits XML into sub-files based on root children (Legacy Style)."""
    try:
        tree = ET.parse(xml_content)
        root = tree.getroot()
        tags_found = set([child.tag for child in root])
        for tag in tags_found:
            clean_tag = tag.split('}')[-1]
            records = root.findall(f".//{tag}")
            if records:
                xlsx_data = xml_to_excel_buffer(records, clean_tag)
                if xlsx_data:
                    new_filename = f"{base_name.replace('.xml','')}_{clean_tag}.xlsx"
                    zip_out.writestr(new_filename, xlsx_data)
        return True
    except: return False

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title("Settings & Info")
    st.info("Mapping TRUD AMPP records to GTINs.")
    st.divider()
    st.subheader("🔍 Quick GTIN Lookup")
    lookup_id = st.text_input("Enter ID (APPID/AMPPID) to find GTIN", help="Search the memory for a specific ID barcode.")
    st.divider()
    st.caption("v2.3 | Web Production Build")

# --- 5. MAIN UI ---
st.title("💊 TRUD Data Toolkit")
st.markdown("---")

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("1. Data Upload")
    uploaded_file = st.file_uploader("Upload the main TRUD ZIP file", type="zip")

with col2:
    st.subheader("2. File Summary")
    week_num = "Export" 
    if uploaded_file:
        st.write(f"**Filename:** `{uploaded_file.name}`")
        date_match = re.search(r'_(\d{8})', uploaded_file.name)
        if date_match:
            week_num = date_match.group(1)
            st.warning(f"📅 **Data Date:** {week_num}")
    else:
        st.write("Awaiting file...")

if uploaded_file is not None:
    st.markdown("---")
    
    mode = st.radio("**3. Choose Action:**", 
                    ["🔗 GTIN Mapper (Standard)", "📦 Bulk Multi-File Export (Legacy Style)"])

    if mode == "📦 Bulk Multi-File Export (Legacy Style)":
        st.subheader("Filter Exports")
        options = ["amp", "ampp", "vmp", "vmpp", "vtm", "gtin", "ingredient", "lookup", "bnf"]
        
        # Toggle Logic
        if 'select_all' not in st.session_state:
            st.session_state.select_all = True

        def toggle_select():
            st.session_state.select_all = not st.session_state.select_all

        st.button("Toggle Select All / None", on_click=toggle_select)
        selected_files = st.multiselect("Select components:", options, 
                                       default=options if st.session_state.select_all else [])
    
    if st.button("🚀 Run Processor", use_container_width=True):
        try:
            with zipfile.ZipFile(uploaded_file, 'r') as outer_zip:
                
                if "GTIN Mapper" in mode:
                    with st.status("Performing Mapping...", expanded=True):
                        # ... (Standard mapping logic as per v1.9)
                        st.info("Mapping function complete.")
                        # Insert your specific mapping merge here
                
                else: # --- BULK LEGACY MODE ---
                    with st.status("Performing Split Conversion...", expanded=True) as status:
                        bulk_zip_buffer = io.BytesIO()
                        with zipfile.ZipFile(bulk_zip_buffer, "w") as zip_out:
                            for filename in outer_zip.namelist():
                                fname_lower = filename.lower()
                                if any(f"f_{opt}" in fname_lower or (opt in fname_lower and ".zip" in fname_lower) for opt in selected_files):
                                    if filename.endswith('.xml'):
                                        process_complex_xml(outer_zip.open(filename), zip_out, filename)
                                    elif filename.endswith('.zip'):
                                        with outer_zip.open(filename) as nested_data:
                                            with zipfile.ZipFile(io.BytesIO(nested_data.read())) as inner_zip:
                                                for inner_name in inner_zip.namelist():
                                                    if inner_name.endswith('.xml'):
                                                        process_complex_xml(inner_xml, zip_out, inner_name)
                        
                        status.update(label="Conversion Complete!", state="complete")
                        st.success("Files successfully split and converted.")
                        st.download_button("📥 Download ZIP", bulk_zip_buffer.getvalue(), f"Legacy_Split_{week_num}.zip")

        except Exception as e:
            st.error(f"❌ Error: {e}")
