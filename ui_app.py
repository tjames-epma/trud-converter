import streamlit as st
import zipfile
import xml.etree.ElementTree as ET
import pandas as pd
import io
import re  # Needed for smart date extraction
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
    st.info("Mapping TRUD AMPP records to GTINs.")
    st.divider()
    st.subheader("🔍 Quick GTIN Lookup")
    lookup_id = st.text_input("Enter APPID/AMPPID to find GTIN", help="Search the memory for a specific ID barcode.")
    st.divider()
    st.caption("v1.5 | Built for EPMA Data Team")

st.title("💊 TRUD AMPP + GTIN Processor")
st.markdown("---")

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("1. Data Upload")
    uploaded_file = st.file_uploader("Upload the main TRUD ZIP file", type="zip")

with col2:
    st.subheader("2. Summary")
    # Initialize week_num with a fallback
    week_num = "Processed" 
    
    if uploaded_file:
        st.write(f"**Filename:** `{uploaded_file.name}`")
        
        # Check for the specific DM+D filename format
        if uploaded_file.name.lower().startswith("nhsbsa_dmd_1"):
            # Regex extracts the 8 digits (YYYYMMDD) that follow an underscore
            date_match = re.search(r'_(\d{8})', uploaded_file.name)
            if date_match:
                week_num = date_match.group(1)
                st.warning(f"📅 **Data Date Identified:** {week_num}")
            else:
                st.info("📂 Valid dm+d format, but date extraction failed.")
        elif 'week' in uploaded_file.name.lower():
            week_num = uploaded_file.name.lower().split('-')[0].replace('week', '')
            st.warning(f"📅 **Data Week Identified:** {week_num}")
    else:
        st.write("Awaiting file...")

if uploaded_file is not None:
    if st.button("🚀 Process Data & Create Table", use_container_width=True):
        with st.status("Processing Layers...", expanded=True) as status:
            try:
                with zipfile.ZipFile(uploaded_file, 'r') as outer_zip:
                    st.write("Reading AMPP file...")
                    df_ampp = get_ampp_data(outer_zip, 'f_ampp2')
                    
                    gtin_zip_list = [f for f in outer_zip.namelist() if 'gtin' in f.lower()]
                    
                    if not gtin_zip_list:
                        st.error("Could not find internal GTIN zip.")
                    else:
                        st.write("Reading GTIN file...")
                        with outer_zip.open(gtin_zip_list[0]) as inner_data:
                            with zipfile.ZipFile(io.BytesIO(inner_data.read())) as inner_zip:
                                df_gtin = get_gtin_mapping(inner_zip)

                        # Merge Logic
                        st.write("Merging records...")
                        final_df = pd.merge(df_ampp, df_gtin, left_on='APPID', right_on='AMPPID', how='left')
                        
                        total_ampps = len(final_df)
                        gtin_matches = final_df['GTIN'].notna().sum()
                        match_rate = gtin_matches / total_ampps if total_ampps > 0 else 0
                        
                        export_df = final_df.dropna(subset=['GTIN']).copy()
                        if 'AMPPID' in export_df.columns:
                            export_df = export_df.drop(columns=['AMPPID'])

                        # Sidebar Metrics
                        with st.sidebar:
                            st.subheader("📊 Data Quality")
                            st.metric("Total AMPPs", f"{total_ampps:,}")
                            st.metric("GTIN Matches", f"{gtin_matches:,}", delta=f"{match_rate:.1%}")
                            st.progress(match_rate, text="Barcode Coverage")
                            
                            if lookup_id:
                                search_res = final_df[final_df['APPID'] == lookup_id]
                                if not search_res.empty and pd.notna(search_res.iloc[0]['GTIN']):
                                    st.success(f"**GTIN:** {search_res.iloc[0]['GTIN']}")
                                else:
                                    st.error("GTIN not found for this ID.")

                        # Excel Table Generation
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            sheet_name = 'GTIN_Data'
                            export_df.to_excel(writer, index=False, sheet_name=sheet_name)
                            worksheet = writer.sheets[sheet_name]
                            num_rows, num_cols = export_df.shape
                            last_col = get_column_letter(num_cols)
                            
                            tab = Table(displayName="TRUD_Data_Table", ref=f"A1:{last_col}{num_rows + 1}")
                            style = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
                            tab.tableStyleInfo = style
                            worksheet.add_table(tab)
                            
                            for i, col in enumerate(export_df.columns):
                                worksheet.column_dimensions[get_column_letter(i+1)].width = 20

                        processed_data = output.getvalue()
                        status.update(label="Conversion Complete!", state="complete", expanded=False)
                        st.balloons()
                        st.download_button(
                            label="📥 Download Power Query Ready Excel",
                            data=processed_data,
                            file_name=f"TRUD_GTIN_Export_{week_num}.xlsx"
                        )
            except Exception as e:
                st.error(f"An error occurred: {e}")
