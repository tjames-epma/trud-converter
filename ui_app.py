import streamlit as st
import zipfile
import xml.etree.ElementTree as ET
import pandas as pd
import io
import re
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

def xml_to_df_deep(xml_content):
    """Deep search parser to handle namespaces and various XML levels."""
    try:
        tree = ET.parse(xml_content)
        root = tree.getroot()
        rows = []
        for record in root.findall(".//{*}AMPP"):
            entry = {child.tag.split('}')[-1]: child.text for child in record if child.text}
            if entry:
                rows.append(entry)
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()

def get_gtin_mapping_deep(zip_obj):
    """Robust GTIN extractor that scans for multiple ID types (AMPPID/APPID)."""
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

# --- 4. USER INTERFACE ---

with st.sidebar:
    st.title("Settings & Info")
    st.info("Mapping TRUD AMPP records to GTINs.")
    st.divider()
    st.subheader("🔍 Quick GTIN Lookup")
    lookup_id = st.text_input("Enter ID (APPID/AMPPID) to find GTIN")
    st.divider()
    st.caption("v1.9 | Web Production Build")

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
            st.warning(f"📅 **Data Date identified:** {week_num}")
    else:
        st.write("Awaiting file...")

if uploaded_file is not None:
    st.markdown("---")
    
    mode = st.radio(
        "**3. Choose Action:**", 
        ["🔗 GTIN Mapper (Power Query Ready)", "📦 Bulk Convert All XMLs to XLSX"],
        help="Select 'Mapper' to create the barcode-to-drug link, or 'Bulk' to extract all XML files as individual Excels."
    )

    if st.button("🚀 Process Data", use_container_width=True):
        try:
            with zipfile.ZipFile(uploaded_file, 'r') as outer_zip:
                
                if "GTIN Mapper" in mode:
                    with st.status("Performing Deep Scan & Merge...", expanded=True) as status:
                        # 1. Process AMPP
                        ampp_file = [f for f in outer_zip.namelist() if 'f_ampp2' in f.lower()][0]
                        with outer_zip.open(ampp_file) as f:
                            df_ampp = xml_to_df_deep(f)
                        
                        id_col = next((c for c in ['AMPPID', 'APPID', 'APID'] if c in df_ampp.columns), None)
                        
                        # 2. Process GTIN
                        gtin_zip_name = [f for f in outer_zip.namelist() if 'gtin' in f.lower()][0]
                        with outer_zip.open(gtin_zip_name) as inner_data:
                            with zipfile.ZipFile(io.BytesIO(inner_data.read())) as inner_zip:
                                df_gtin = get_gtin_mapping_deep(inner_zip)

                        # 3. Merge & Format
                        final_df = pd.merge(df_ampp, df_gtin, left_on=id_col, right_on='JOIN_ID', how='left').dropna(subset=['GTIN'])
                        if 'JOIN_ID' in final_df.columns:
                            final_df = final_df.drop(columns=['JOIN_ID'])

                        # --- NEW: SIDEBAR PREVIEW ---
                        with st.sidebar:
                            st.divider()
                            st.subheader("👀 Data Preview (Top 5)")
                            # Show NM (Name) and GTIN for verification
                            preview_cols = [c for c in ['NM', 'GTIN', id_col] if c in final_df.columns]
                            st.dataframe(final_df[preview_cols].head(5), hide_index=True)
                            st.metric("Total Matches", f"{len(final_df):,}")

                        # Excel Save
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            final_df.to_excel(writer, index=False, sheet_name='GTIN_Data')
                            worksheet = writer.sheets['GTIN_Data']
                            num_rows, num_cols = final_df.shape
                            last_col = get_column_letter(num_cols)
                            tab = Table(displayName="TRUD_Mapping", ref=f"A1:{last_col}{num_rows + 1}")
                            tab.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
                            worksheet.add_table(tab)
                        
                        status.update(label="Mapping Complete!", state="complete")
                        st.balloons()
                        st.download_button("📥 Download Mapping", output.getvalue(), f"TRUD_GTIN_{week_num}.xlsx")

                else:
                    with st.status("Converting all XML files...", expanded=True) as status:
                        bulk_output = io.BytesIO()
                        with zipfile.ZipFile(bulk_output, "w") as zip_out:
                            for name in outer_zip.namelist():
                                if name.endswith('.xml'):
                                    with outer_zip.open(name) as xml_f:
                                        df = xml_to_df_deep(xml_f)
                                        if not df.empty:
                                            buf = io.BytesIO()
                                            df.to_excel(buf, index=False)
                                            zip_out.writestr(name.replace('.xml', '.xlsx'), buf.getvalue())
                        
                        status.update(label="Bulk Conversion Complete!", state="complete")
                        st.success("All valid XML records have been converted.")
                        st.download_button("📥 Download ZIP of Excels", bulk_output.getvalue(), f"Bulk_Export_{week_num}.zip")
        
        except Exception as e:
            st.error(f"❌ Error during processing: {e}")
