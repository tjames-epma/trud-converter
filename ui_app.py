import streamlit as st
import zipfile
import xml.etree.ElementTree as ET
import pandas as pd
import io
import re
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter

# 1. Page Configuration
st.set_page_config(page_title="TRUD XML Converter", page_icon="💊", layout="wide")

# --- 2. PASSWORD GATEKEEPER ---
def check_password():
    if "auth" not in st.secrets:
        st.error("Secrets not configured.")
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
    return st.session_state.get("password_correct", False)

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
            # Extract tags without namespaces
            entry = {child.tag.split('}')[-1]: (child.text if child.text else "") for child in record}
            if "ABBREVNM" not in entry: entry["ABBREVNM"] = ""
            rows.append(entry)
        return pd.DataFrame(rows)

def get_gtin_mapping(zip_obj):
    xml_files = [f for f in zip_obj.namelist() if f.endswith('.xml')]
    if not xml_files: return pd.DataFrame(columns=['JOIN_ID', 'GTIN'])
    with zip_obj.open(xml_files[0]) as f:
        tree = ET.parse(f)
        root = tree.getroot()
        rows = []
        for ampp_block in root.findall(".//{*}AMPP"):
            # Namespace-agnostic search for any ID field
            id_elem = ampp_block.find(".//{*}AMPPID") or ampp_block.find(".//{*}APPID") or ampp_block.find(".//{*}ID")
            row_id = id_elem.text if id_elem is not None else None
            
            for gtin_data in ampp_block.findall(".//{*}GTINDATA"):
                gtin_elem = gtin_data.find(".//{*}GTIN")
                if gtin_elem is not None and row_id:
                    rows.append({'JOIN_ID': str(row_id), 'GTIN': str(gtin_elem.text)})
        
        # Critical Fix: Ensure columns exist even if rows list is empty
        df = pd.DataFrame(rows)
        if df.empty:
            return pd.DataFrame(columns=['JOIN_ID', 'GTIN'])
        return df

# --- 4. MAIN UI ---

st.title("💊 TRUD AMPP + GTIN Processor")
uploaded_file = st.file_uploader("Upload the main TRUD ZIP file", type="zip")

if uploaded_file:
    if st.button("🚀 Process Data", use_container_width=True):
        with st.status("Running...", expanded=True) as status:
            try:
                with zipfile.ZipFile(uploaded_file, 'r') as outer_zip:
                    # 1. Get AMPP Data
                    df_ampp = get_ampp_data(outer_zip, 'f_ampp2')
                    if df_ampp.empty:
                        st.error("Main AMPP file not found in ZIP.")
                        st.stop()

                    # 2. Get GTIN Data
                    gtin_zip_list = [f for f in outer_zip.namelist() if 'gtin' in f.lower()]
                    if not gtin_zip_list:
                        st.error("GTIN zip not found.")
                        st.stop()
                    
                    with outer_zip.open(gtin_zip_list[0]) as inner_data:
                        with zipfile.ZipFile(io.BytesIO(inner_data.read())) as inner_zip:
                            df_gtin = get_gtin_mapping(inner_zip)

                    # 3. Merge Logic (Double-Check)
                    st.write("Joining datasets...")
                    # Force both to string to prevent mismatch
                    df_gtin['JOIN_ID'] = df_gtin['JOIN_ID'].astype(str)
                    
                    # Try APPID first
                    final_df = pd.merge(df_ampp, df_gtin, left_on='APPID', right_on='JOIN_ID', how='left')
                    
                    # If no matches, try AMPPID
                    if final_df['GTIN'].isna().all() and 'AMPPID' in df_ampp.columns:
                        final_df = pd.merge(df_ampp, df_gtin, left_on='AMPPID', right_on='JOIN_ID', how='left')

                    # 4. Export Cleanup
                    export_df = final_df.dropna(subset=['GTIN']).copy()
                    if 'JOIN_ID' in export_df.columns:
                        export_df = export_df.drop(columns=['JOIN_ID'])

                    if export_df.empty:
                        st.warning("No GTIN matches found. Outputting full AMPP list instead.")
                        export_df = df_ampp

                    # 5. Excel Generation
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        export_df.to_excel(writer, index=False, sheet_name='GTIN_Data')
                        worksheet = writer.sheets['GTIN_Data']
                        last_col = get_column_letter(export_df.shape[1])
                        tab = Table(displayName="TRUDTable", ref=f"A1:{last_col}{len(export_df)+1}")
                        tab.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
                        worksheet.add_table(tab)

                    st.download_button(
                        label="📥 Download Excel",
                        data=output.getvalue(),
                        file_name=f"TRUD_Export.xlsx",
                        use_container_width=True
                    )
                    status.update(label="Complete!", state="complete")
                    st.balloons()

            except Exception as e:
                st.error(f"Error: {e}")
