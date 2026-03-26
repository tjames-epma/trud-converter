import streamlit as st
import zipfile
import xml.etree.ElementTree as ET
import pandas as pd
import io
import re

# 1. Essential Config
st.set_page_config(page_title="TRUD Data Toolkit", page_icon="💊", layout="wide")

# 2. Simplified Auth Logic (Prevents Refresh Loops)
def check_password():
    if "auth" not in st.secrets:
        return True
    if st.session_state.get("password_correct"):
        return True

    st.title("🔐 Access Required")
    pwd = st.text_input("Please enter the access password", type="password")
    if st.button("Sign In"):
        if pwd == st.secrets["auth"]["password"]:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("Invalid password")
    return False

# 3. Memory-Safe Logic
def get_legacy_sheet_name(tag, filename_lower):
    tag = tag.split('}')[-1]
    if "f_ampp" in filename_lower:
        mapping = {"AMPP": "AmppType", "PACK_INFO": "PackInfoType", "CONTENT": "ContentType", 
                   "CCONTENT": "ContentType", "PRESC_INFO": "PrescInfoType", 
                   "PRICE_INFO": "PriceInfoType", "REIMB_INFO": "ReimbInfoType"}
        return mapping.get(tag, tag)
    if "f_amp" in filename_lower and not "ampp" in filename_lower:
        mapping = {"AMP": "AmpType", "API": "ApiType", "LIC_ROUTE": "LicRouteType", "APP_PROD_INFO": "AppProdInfoType"}
        return mapping.get(tag, tag)
    if "f_vmp" in filename_lower and not "vmpp" in filename_lower:
        mapping = {"VMP": "VMP", "VPI": "VPI", "ONT_DRUG_FORM": "OntDrugForm",
                   "DRUG_FORM": "DrugForm", "DRUG_ROUTE": "DrugRoute", "CONTROL_INFO": "Control"}
        return mapping.get(tag, tag)
    if "f_vmpp" in filename_lower:
        mapping = {"VMPP": "VMPP", "DT_INFO": "DtInfo", "CONTENT": "CContent", "CCONTENT": "CContent"}
        return mapping.get(tag, tag)
    if "f_lookup" in filename_lower:
        return tag.replace("InfoType", "").replace("Type", "")
    if "f_vtm" in filename_lower: return "VTM"
    if "f_ingredient" in filename_lower: return "Ingredient"
    if "f_gtin" in filename_lower: return "GTIN"
    return tag.replace("InfoType", "").replace("Type", "")

def process_legacy_xml_to_sheets(xml_file_obj, filename_lower):
    try:
        data_map = {}
        context = ET.iterparse(xml_file_obj, events=("end",))
        for event, elem in context:
            tag_name = elem.tag.split('}')[-1]
            sheet_name = get_legacy_sheet_name(tag_name, filename_lower)
            if len(elem) > 0:
                child_data = {child.tag.split('}')[-1]: (child.text if child.text is not None else "") for child in elem}
                if child_data:
                    if sheet_name not in data_map: data_map[sheet_name] = []
                    data_map[sheet_name].append(child_data)
            elem.clear()
        
        final_sheets = {}
        for sheet, rows in data_map.items():
            df = pd.DataFrame(rows)
            if sheet in ["AmppType", "VMP", "VTM"] and "ABBREVNM" not in df.columns:
                df["ABBREVNM"] = ""
            df = df.drop_duplicates()
            if len(df.columns) > 1:
                cols = list(df.columns)
                preferred = [c for c in ["APPID", "AMPPID", "VMPID", "VTMID", "NM", "ABBREVNM"] if c in cols]
                others = [c for c in cols if c not in preferred]
                df = df[preferred + others]
                final_sheets[sheet] = df
        return final_sheets
    except:
        return {}

# 4. Main App
def main():
    if not check_password():
        return

    st.title("💊 TRUD Data Toolkit")
    
    with st.sidebar:
        st.caption("v5.0 | Stability Build")
        if st.button("Clear Cache & Logout"):
            st.session_state.clear()
            st.rerun()

    uploaded_file = st.file_uploader("Upload TRUD ZIP", type="zip")

    if uploaded_file:
        mode = st.radio("Action", ["📦 Bulk Multi-File", "🔗 GTIN Mapper"])
        
        if st.button("🚀 Process File"):
            with st.spinner("Crunching TRUD data..."):
                try:
                    with zipfile.ZipFile(uploaded_file, 'r') as outer_zip:
                        all_names = outer_zip.namelist()
                        buf = io.BytesIO()
                        
                        if mode == "📦 Bulk Multi-File":
                            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
                                xml_worklist = []
                                for f in all_names:
                                    if f.endswith('.xml'): xml_worklist.append((f, outer_zip.open(f)))
                                    elif f.endswith('.zip'):
                                        with outer_zip.open(f) as zd_inner:
                                            with zipfile.ZipFile(io.BytesIO(zd_inner.read())) as iz_inner:
                                                for iname in iz_inner.namelist():
                                                    if iname.endswith('.xml'):
                                                        xml_worklist.append((iname, io.BytesIO(iz_inner.read(iname))))
                                
                                for xml_name, xml_data in xml_worklist:
                                    sheets = process_legacy_xml_to_sheets(xml_data, xml_name.lower())
                                    if sheets:
                                        ex_buf = io.BytesIO()
                                        with pd.ExcelWriter(ex_buf, engine='openpyxl') as writer:
                                            for s_name, s_df in sheets.items():
                                                s_df.to_excel(writer, index=False, sheet_name=s_name[:31])
                                        
                                        clean_fn = re.sub(r'\d+', '', xml_name.split('/')[-1].split('.')[0]) + ".xlsx"
                                        zout.writestr(clean_fn, ex_buf.getvalue())
                            
                            st.session_state['ready_data'] = buf.getvalue()
                            st.session_state['ready_name'] = "TRUD_Export.zip"

                        else: # GTIN Mapper
                            # ... (Simplified GTIN Mapper logic)
                            pass

                except Exception as e:
                    st.error(f"Error: {e}")

    if 'ready_data' in st.session_state:
        st.success("Processing Complete!")
        st.download_button(
            "📥 Download Result",
            data=st.session_state['ready_data'],
            file_name=st.session_state['ready_name'],
            mime="application/zip",
            use_container_width=True
        )

if __name__ == "__main__":
    main()
