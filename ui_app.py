import streamlit as st
import zipfile
import xml.etree.ElementTree as ET
import pandas as pd
import io

# --- LOGIC FUNCTIONS (The ones we perfected) ---

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
            amppid = (ampp_block.find("{*}AMPPID")).text if ampp_block.find("{*}AMPPID") is not None else None
            for gtin_data in ampp_block.findall(".//{*}GTINDATA"):
                gtin_elem = gtin_data.find("{*}GTIN")
                if gtin_elem is not None and amppid:
                    rows.append({'AMPPID': amppid, 'GTIN': gtin_elem.text})
        return pd.DataFrame(rows)

# --- USER INTERFACE ---

st.set_page_config(page_title="TRUD XML Converter", page_icon="💊")
st.title("💊 TRUD AMPP + GTIN Converter")
st.write("Drag and drop your main TRUD ZIP file below to extract and merge records.")

uploaded_file = st.file_uploader("Choose a ZIP file", type="zip")

if uploaded_file is not None:
    st.success("File uploaded successfully!")
    
    if st.button("🚀 Process and Merge Data"):
        with st.status("Processing data...", expanded=True) as status:
            try:
                # Read the uploaded file into memory
                with zipfile.ZipFile(uploaded_file, 'r') as outer_zip:
                    
                    st.write("Extracting main AMPP data...")
                    df_ampp = get_ampp_data(outer_zip, 'f_ampp2')
                    
                    gtin_zip_list = [f for f in outer_zip.namelist() if 'gtin' in f.lower()]
                    
                    if not gtin_zip_list:
                        st.error("Could not find internal GTIN zip.")
                    else:
                        st.write(f"Opening inner zip: {gtin_zip_list[0]}...")
                        with outer_zip.open(gtin_zip_list[0]) as inner_data:
                            with zipfile.ZipFile(io.BytesIO(inner_data.read())) as inner_zip:
                                st.write("Extracting GTIN mapping...")
                                df_gtin = get_gtin_mapping(inner_zip)

                        # Merge Logic
                        st.write("Merging and Filtering...")
                        final_df = pd.merge(df_ampp, df_gtin, left_on='APPID', right_on='AMPPID', how='left')
                        final_df = final_df.dropna(subset=['GTIN'])
                        if 'AMPPID' in final_df.columns:
                            final_df = final_df.drop(columns=['AMPPID'])

                        # Create the Excel file in memory
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            final_df.to_excel(writer, index=False)
                        processed_data = output.getvalue()

                        status.update(label="Conversion Complete!", state="complete", expanded=False)
                        
                        st.balloons()
                        st.download_button(
                            label="📥 Download Filtered Excel File",
                            data=processed_data,
                            file_name="TRUD_AMPP_GTIN_Export.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )

            except Exception as e:
                st.error(f"An error occurred: {e}")