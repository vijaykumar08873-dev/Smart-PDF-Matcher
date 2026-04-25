import streamlit as st
import fitz  # PyMuPDF
import zipfile
import io
import re
from PIL import Image, ImageEnhance, ImageOps
from pyzbar.pyzbar import decode
import pytesseract

def find_matching_docket(page, expected_dockets):
    # --- 1. NATIVE PDF TEXT CHECK ---
    native_text = page.get_text("text")
    clean_native = re.sub(r'\D', '', native_text) # Sirf numbers rakhega
    for expected in expected_dockets:
        if expected in native_text or expected in clean_native:
            return expected
            
    # --- Image Setup ---
    pix = page.get_pixmap(dpi=300)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    
    gray_img = ImageOps.grayscale(img)
    enhancer = ImageEnhance.Contrast(gray_img)
    sharp_img = enhancer.enhance(2.0)
    
    # --- 2. ROTATION BARCODE SWEEP (Ye Tedhe pages ka 100% ilaaj hai) ---
    # Tedhe scan ko theek karne ke liye image ko alag-alag angles par ghuma kar scan karenge
    angles_to_try =[0, 5, -5, 10, -10, 15, -15, 20, -20, 90, -90]
    
    for angle in angles_to_try:
        rotated_img = sharp_img.rotate(angle, expand=True, fillcolor=255)
        barcodes = decode(rotated_img)
        
        for obj in barcodes:
            data = obj.data.decode('utf-8').strip()
            clean_data = re.sub(r'\D', '', data) # Barcode se kachra hatana
            
            for expected in expected_dockets:
                if expected in data or expected in clean_data:
                    return expected

    # --- 3. SMART OCR CHECK WITH FUZZY LOGIC ---
    try:
        ocr_text = pytesseract.image_to_string(sharp_img)
        
        # OCR ki common galtiyo ko (O ko 0, l ko 1) strictly theek karna
        fixed_ocr = ocr_text.upper().translate(str.maketrans('OQDIlLSZGB?', '00011152687'))
        pure_digits_ocr = re.sub(r'\D', '', fixed_ocr) # Isme se saare alphabet nikal dena
        
        for expected in expected_dockets:
            # Exact Match in digits
            if expected in pure_digits_ocr:
                return expected
                
            # Fuzzy Match (Agar 2 number OCR ne galat bhi padhe, toh bhi match karega)
            if len(expected) >= 8:
                for i in range(len(pure_digits_ocr) - len(expected) + 1):
                    window = pure_digits_ocr[i:i+len(expected)]
                    errors = sum(1 for a, b in zip(expected, window) if a != b)
                    if errors <= 2: 
                        return expected
    except:
        pass
        
    return None

def process_pdf(uploaded_file, docket_list_text):
    raw_dockets = docket_list_text.replace(",", "\n").split("\n")
    expected_dockets = set()
    for d in raw_dockets:
        # Sirf numbers extract karna row data se
        clean_d = re.sub(r'\D', '', d.strip())
        if clean_d:
            expected_dockets.add(clean_d)
            
    found_dockets = set()
    
    pdf_document = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for page_num in range(len(pdf_document)):
            page = pdf_document.load_page(page_num)
            
            matched_id = find_matching_docket(page, expected_dockets)
            
            if matched_id:
                file_name = f"{matched_id}.pdf"
                found_dockets.add(matched_id)
            else:
                file_name = f"Unscanned_Page_{page_num + 1}.pdf"
                
            # --- SUPER COMPRESSION LOGIC (100 - 120 KB TARGET) ---
            pix_low = page.get_pixmap(dpi=130, colorspace=fitz.csGRAY)
            img_low = Image.frombytes("L",[pix_low.width, pix_low.height], pix_low.samples)
            
            img_byte_arr = io.BytesIO()
            img_low.save(img_byte_arr, format='JPEG', quality=40, optimize=True)
            img_bytes = img_byte_arr.getvalue()
            
            new_pdf = fitz.open()
            new_page = new_pdf.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(new_page.rect, stream=img_bytes)
            
            pdf_bytes = new_pdf.write(garbage=4, deflate=True)
            new_pdf.close()
            # -----------------------------------------------------
            
            zip_file.writestr(file_name, pdf_bytes)
            
    pending_dockets = expected_dockets - found_dockets
            
    return zip_buffer, list(found_dockets), list(pending_dockets)

# --- UI Setup ---
st.set_page_config(page_title="Smart PDF Matcher & Splitter", page_icon="🎯", layout="wide")
st.title("🎯 Smart PDF Matcher & Splitter")
st.write("Apne Dockets ki list (Row Data) daalein aur PDF upload karein. App strictly list se match karega.")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Enter Docket IDs")
    docket_input = st.text_area(
        "Yahan apna Row Data paste karein:", 
        height=200, 
        placeholder="Example:\n7002010582\n7002038210..."
    )

with col2:
    st.subheader("2. Upload Main PDF")
    uploaded_pdf = st.file_uploader("Apna courier PDF upload karein", type=["pdf"])

if st.button("🚀 Match, Compress & Split PDF", use_container_width=True):
    if not docket_input.strip():
        st.error("Kripya pehle Docket IDs ka data box mein paste karein!")
    elif not uploaded_pdf:
        st.error("Kripya Main PDF file upload karein!")
    else:
        with st.spinner("Matching, Splitting & Compressing... Kripya intezaar karein..."):
            try:
                zip_data, found_list, pending_list = process_pdf(uploaded_pdf, docket_input)
                
                st.success("🎉 Process Complete! Aapki ZIP file taiyaar hai.")
                
                st.download_button(
                    label="📥 Download Renamed & Compressed ZIP",
                    data=zip_data.getvalue(),
                    file_name="Matched_Dockets.zip",
                    mime="application/zip",
                    use_container_width=True
                )
                
                st.markdown("---")
                st.header("📊 Result Report (Dhyan Se Dekhein)")
                
                if pending_list:
                    st.error(f"❌ PENDING BOX: Ye {len(pending_list)} Dockets aapki PDF mein NAHI mile")
                    for p in pending_list:
                        st.write(f"👉 **{p}**")
                else:
                    st.success("🎯 ALL CLEAR! Aapki list ke saare dockets PDF mein 100% mil gaye aur rename ho gaye.")
                    
                st.markdown("---")
                st.success(f"✅ MATCHED BOX: Ye {len(found_list)} Dockets successfully rename ho gaye hain")
                with st.expander("Matched Dockets ki list dekhne ke liye yahan click karein"):
                    st.write(", ".join(found_list))
                        
            except Exception as e:
                st.error(f"Kuch error aayi: {e}")
