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
    """Splits one XML into multiple Excel files based on child record tags."""
    try:
        tree = ET.parse(xml_content)
        root = tree.getroot()
        # Get unique tags at the first level
        tags_found = set([child.tag for child in root])
        for tag in tags_found:
            clean_tag = tag.split('}')[-1]
            records = root.findall(f".//{tag}")
            if records:
                xlsx_data = xml_to_excel_buffer(records, clean_tag)
                if xlsx_data:
                    # Strip path and extension for naming
                    fn = base_name.split('/')[-1].replace('.xml', '')
                    new_filename = f"{fn}_{clean_tag}.xlsx"
                    zip_out.writestr(new_filename, xlsx_data)
        return True
    except: return False

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title("Settings & Info")
    lookup_id = st.text_input("🔍 Quick GTIN Lookup (APPID)")
    st.divider()
    st.caption("v2.6 | Deep Scan Build")

# --- 5. MAIN UI ---
st.title("💊 TRUD Data Toolkit")

uploaded_file = st.file_uploader("Upload TRUD ZIP", type="zip")

if uploaded_file:
    # Identify the date from the main zip name
    date_match = re.search(r'_(\d{8})', uploaded_file.name)
    file_date = date_match.group(1) if date_match else "Processed"

    mode = st.radio("**Select Action:**", ["🔗 GTIN Mapper", "📦 Bulk Multi-File (Legacy)"])

    if mode == "📦 Bulk Multi-File (Legacy)":
        st.subheader("Filter Exports")
        options = ["amp", "ampp", "vmp", "vmpp", "vtm", "gtin", "ingredient", "lookup"]
        
        if 'sel_all' not in st.session_state: st.session_state.sel_all = True
        
        # Toggle functionality
        if st.button("Toggle Select All/None"): 
            st.session_state.sel_all = not st.session_state.sel_all
            st.rerun()
            
        selected_files = st.multiselect("Select components to convert:", options, 
                                       default=options if st.session_state.sel_all else [])

    if st.button("🚀 Run Processor", use_container_width=True):
        try:
            with zipfile.ZipFile(uploaded_file, 'r') as outer_zip:
                all_names = outer_zip.namelist()
                
                # --- MODE: GTIN MAPPER ---
                if mode == "🔗 GTIN Mapper":
                    with st.status("Mapping Barcodes...", expanded=True):
                        # Search for f_ampp2 using a flexible pattern
                        ampp_file = [f for f in all_names if 'f_ampp2' in f.lower() and f.endswith('.xml')][0]
                        
                        tree = ET.parse(outer_zip.open(ampp_file))
                        root = tree.getroot()
                        ampp_rows = []
                        for record in root.findall(".//{*}AMPP"):
                            entry = {child.tag.split('}')[-1]: child.text for child in record if child.text}
                            if entry: ampp_rows.append(entry)
                        df_ampp = pd.DataFrame(ampp_rows)
                        
                        id_col = next((c for c in ['AMPPID', 'APPID', 'APID'] if c in df_ampp.columns), None)
                        
                        # Find GTIN Zip
                        gtin_zip_name = [f for f in all_names if 'gtin' in f.lower() and f.endswith('.zip')][0]
                        with outer_zip.open(gtin_zip_name) as inner_data:
                            with zipfile.ZipFile(io.BytesIO(inner_data.read())) as inner_zip:
                                gtin_rows = []
                                gtin_xml = [f for f in inner_zip.namelist() if f.endswith('.xml')][0]
                                with inner_zip.open(gtin_xml) as f:
                                    g_tree = ET.parse(f)
                                    g_root = g_tree.getroot()
                                    for ampp_block in g_root.findall(".//{*}AMPP"):
                                        id_val = None
                                        for id_tag in ["AMPPID", "APPID"]:
                                            found = ampp_block.find(f".//{{*}}{id_tag}")
                                            if found is not None: id_val = found.text; break
                                        for g_data in ampp_block.findall(".//{*}GTINDATA"):
                                            g_elem = g_data.find(".//{*}GTIN")
                                            if g_elem is not None and id_val:
                                                gtin_rows.append({'JOIN_ID': id_val, 'GTIN': g_elem.text})
                                df_gtin = pd.DataFrame(gtin_rows)

                        final_df = pd.merge(df_ampp, df_gtin, left_on=id_col, right_on='JOIN_ID', how='left').dropna(subset=['GTIN'])
                        if 'JOIN_ID' in final_df.columns: final_df = final_df.drop(columns=['JOIN_ID'])

                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            final_df.to_excel(writer, index=False, sheet_name='GTIN_Mapping')
                        
                        st.success(f"Matched {len(final_df):,} barcodes!")
                        st.download_button("📥 Download Mapping", output.getvalue(), f"TRUD_GTIN_{file_date}.xlsx")

                # --- MODE: LEGACY BULK ---
                else:
                    with st.status("Deep Scanning Zip Contents...", expanded=True):
                        bulk_zip_buffer = io.BytesIO()
                        processed_count = 0
                        
                        with zipfile.ZipFile(bulk_zip_buffer, "w") as zip_out:
                            for filename in all_names:
                                fn_lower = filename.lower()
                                
                                # Check for XML match
                                if any(f"f_{opt}" in fn_lower for opt in selected_files) and fn_lower.endswith('.xml'):
                                    st.write(f"📂 Splitting: `{filename}`")
                                    process_complex_xml(outer_zip.open(filename), zip_out, filename)
                                    processed_count += 1
                                
                                # Check for nested ZIP match (e.g., GTIN.zip)
                                elif fn_lower.endswith('.zip') and any(opt in fn_lower for opt in selected_files):
                                    st.write(f"📦 Opening sub-zip: `{filename}`")
                                    with outer_zip.open(filename) as nested_data:
                                        with zipfile.ZipFile(io.BytesIO(nested_data.read())) as inner_zip:
                                            for inner_name in inner_zip.namelist():
                                                if inner_name.endswith('.xml'):
                                                    with inner_zip.open(inner_name) as current_xml:
                                                        process_complex_xml(current_xml, zip_out, inner_name)
                                                        processed_count += 1
                        
                        if processed_count == 0:
                            st.error("No files found matching your selection.")
                        else:
                            st.success(f"Success! Created {processed_count} sub-files.")
                            st.download_button("📥 Download Legacy Zip", bulk_zip_buffer.getvalue(), f"Legacy_Export_{file_date}.zip")

        except Exception as e:
            st.error(f"❌ Error: {e}")
