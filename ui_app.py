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

def xml_to_df_deep(xml_content):
    """Robust parser for various XML structures."""
    try:
        tree = ET.parse(xml_content)
        root = tree.getroot()
        rows = []
        for record in root.findall(".//{*}AMPP"):
            entry = {child.tag.split('}')[-1]: child.text for child in record if child.text}
            if entry: rows.append(entry)
        return pd.DataFrame(rows)
    except: return pd.DataFrame()

def get_gtin_mapping_deep(zip_obj):
    """Extracts GTIN mappings regardless of internal folder structure."""
    xml_files = [f for f in zip_obj.namelist() if f.endswith('.xml')]
    if not xml_files: return pd.DataFrame()
    with zip_obj.open(xml_files[0]) as f:
        tree = ET.parse(f)
        root = tree.getroot()
        rows = []
        for ampp_block in root.findall(".//{*}AMPP"):
            id_val = None
            for id_tag in ["AMPPID", "APPID", "APID"]:
                found = ampp_block.find(f".//{{*}}{id_tag}")
                if found is not None:
                    id_val = found.text
                    break
            for gtin_data in ampp_block.findall(".//{*}GTINDATA"):
                gtin_elem = gtin_data.find(".//{*}GTIN")
                if gtin_elem is not None and id_val:
                    rows.append({'JOIN_ID': id_val, 'GTIN': gtin_elem.text})
        return pd.DataFrame(rows)

def xml_to_excel_buffer(element_list, sheet_name):
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
    st.info("TRUD Mapping & Legacy Converter")
    st.divider()
    lookup_id = st.text_input("🔍 Quick GTIN Lookup (APPID)")
    st.divider()
    st.caption("v2.4 | Web Production Build")

# --- 5. MAIN UI ---
st.title("💊 TRUD Data Toolkit")

uploaded_file = st.file_uploader("Upload TRUD ZIP", type="zip")

if uploaded_file:
    date_match = re.search(r'_(\d{8})', uploaded_file.name)
    week_num = date_match.group(1) if date_match else "Export"

    mode = st.radio("**Select Action:**", ["🔗 GTIN Mapper", "📦 Bulk Multi-File (Legacy)"])

    if mode == "📦 Bulk Multi-File (Legacy)":
        options = ["amp", "ampp", "vmp", "vmpp", "vtm", "gtin", "ingredient", "lookup", "bnf"]
        if 'sel_all' not in st.session_state: st.session_state.sel_all = True
        if st.button("Toggle Select All/None"): st.session_state.sel_all = not st.session_state.sel_all
        selected_files = st.multiselect("Select components:", options, default=options if st.session_state.sel_all else [])

    if st.button("🚀 Run Processor", use_container_width=True):
        try:
            with zipfile.ZipFile(uploaded_file, 'r') as outer_zip:
                
                # --- MODE: GTIN MAPPER ---
                if mode == "🔗 GTIN Mapper":
                    with st.status("Mapping Data...", expanded=True):
                        # 1. AMPP
                        ampp_file = [f for f in outer_zip.namelist() if 'f_ampp2' in f.lower()][0]
                        df_ampp = xml_to_df_deep(outer_zip.open(ampp_file))
                        id_col = next((c for c in ['AMPPID', 'APPID', 'APID'] if c in df_ampp.columns), None)
                        
                        # 2. GTIN
                        gtin_zip_name = [f for f in outer_zip.namelist() if 'gtin' in f.lower()][0]
                        with outer_zip.open(gtin_zip_name) as inner_data:
                            with zipfile.ZipFile(io.BytesIO(inner_data.read())) as inner_zip:
                                df_gtin = get_gtin_mapping_deep(inner_zip)

                        # 3. Merge
                        final_df = pd.merge(df_ampp, df_gtin, left_on=id_col, right_on='JOIN_ID', how='left').dropna(subset=['GTIN'])
                        if 'JOIN_ID' in final_df.columns: final_df = final_df.drop(columns=['JOIN_ID'])

                        # 4. Export
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            final_df.to_excel(writer, index=False, sheet_name='GTIN_Data')
                            worksheet = writer.sheets['GTIN_Data']
                            num_rows, num_cols = final_df.shape
                            last_col = get_column_letter(num_cols)
                            tab = Table(displayName="TRUD_Mapping", ref=f"A1:{last_col}{num_rows + 1}")
                            tab.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
                            worksheet.add_table(tab)
                        
                        # Show results
                        st.success(f"Matched {len(final_df):,} barcodes!")
                        st.download_button("📥 Download Mapping Excel", output.getvalue(), f"TRUD_GTIN_{week_num}.xlsx")
                        
                        with st.sidebar:
                            st.divider()
                            st.subheader("👀 Preview")
                            preview_cols = [c for c in ['NM', 'GTIN', id_col] if c in final_df.columns]
                            st.dataframe(final_df[preview_cols].head(10), hide_index=True)

                # --- MODE: LEGACY BULK ---
                else:
                    with st.status("Splitting Files...", expanded=True):
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
                                                        # FIX: Using 'inner_xml' was a typo, now using the actual handle
                                                        with inner_zip.open(inner_name) as current_inner_xml:
                                                            process_complex_xml(current_inner_xml, zip_out, inner_name)
                        
                        st.success("Conversion Complete!")
                        st.download_button("📥 Download Legacy ZIP", bulk_zip_buffer.getvalue(), f"Legacy_Split_{week_num}.zip")

        except Exception as e:
            st.error(f"❌ Error: {e}")
