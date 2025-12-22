import os
import re
import numpy as np
import pandas as pd
import altair as alt
import streamlit as st
import google.generativeai as genai

MAX_AI_QUOTA = 5

# 1. Hàm load danh sách sinh viên từ Excel (Chạy 1 lần duy nhất để tiết kiệm RAM)
@st.cache_resource
def load_valid_students():
    try:
        # 1. Lấy đường dẫn của file code hiện tại (app.py)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 2. Tạo đường dẫn tuyệt đối đến file Excel
        # Nó sẽ nối: "D:\MyApps\..." + "dssv.xlsx" -> Không bao giờ trượt!
        file_path = os.path.join(current_dir, "dssv.xlsx")
        
        # 3. Đọc file
        df = pd.read_excel(file_path, dtype=str)
        valid_ids = df['MSSV'].str.strip().tolist()
        return valid_ids
        
    except Exception as e:
        # In đường dẫn ra để debug nếu vẫn lỗi
        st.error(f"⚠️ Lỗi đọc file tại: {os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dssv.xlsx')}")
        st.error(f"Chi tiết lỗi: {e}")
        return []

# 2. Hàm quản lý đếm lượt dùng (Database tạm trên RAM server)
@st.cache_resource
def get_usage_tracker():
    # Cấu trúc: {'MSSV_A': 0, 'MSSV_B': 2}
    return {}

def verify_and_check_quota(student_id, max_limit=3):
    """
    Hàm này trả về 3 trạng thái:
    - "INVALID": MSSV không có trong file Excel
    - "LIMIT_REACHED": Có trong file nhưng hết lượt
    - "OK": Hợp lệ và còn lượt (sẽ tự động trừ 1 lượt)
    """
    # Load danh sách hợp lệ
    valid_list = load_valid_students()
    
    # Chuẩn hóa input (chữ thường/hoa, xóa khoảng trắng)
    clean_id = str(student_id).strip()
    
    # A. Kiểm tra có trong danh sách không
    if clean_id not in valid_list:
        return "INVALID", 0
    
    # B. Kiểm tra hạn mức
    tracker = get_usage_tracker()
    
    # Nếu chưa dùng lần nào thì tạo mới = 0
    if clean_id not in tracker:
        tracker[clean_id] = 0
        
    current_usage = tracker[clean_id]
    
    if current_usage >= max_limit:
        return "LIMIT_REACHED", current_usage
    
    # C. Nếu OK thì tăng đếm và cho phép
    # Lưu ý: Chỉ gọi hàm này khi CHẮC CHẮN thực hiện lệnh AI
    return "OK", current_usage

def consume_quota(student_id):
    """Gọi hàm này sau khi AI chạy thành công để trừ lượt"""
    clean_id = str(student_id).strip()
    tracker = get_usage_tracker()
    if clean_id in tracker:
        tracker[clean_id] += 1
    else:
        tracker[clean_id] = 1

# ==============================================================================
# 0) PAGE CONFIG
# ==============================================================================
st.set_page_config(
    page_title="Finance Lab",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="🏦",
)

# ==============================================================================
# 1) STYLE (UI + MOBILE RESPONSIVE)
# ==============================================================================
def init_style():
    st.markdown(
        """
<style>
/* -----------------------------
   Global
------------------------------*/
:root{
  --blue:#0d47a1;
  --blue2:#1565c0;
  --green:#28a745;
  --green2:#218838;
  --orange:#ff9800;
  --red:#ff2b2b;
  --text:#333;
}
.block-container { padding-top: 1.2rem; padding-bottom: 2.0rem; }
h1, h2, h3, h4 { letter-spacing: 0.2px; }
small, .stCaption { color: #666 !important; }

/* ===== Buttons (CHUẨN) ===== */

/* PRIMARY: đỏ/cam (AI + nút đang chọn) */
div[data-testid="stButton"] > button[kind="primary"]{
  background-color: #ff2b2b !important;
  color: #fff !important;
  border: none !important;
  border-radius: 10px !important;
  font-weight: 800 !important;
  box-shadow: 0 2px 6px rgba(255,43,43,.35) !important;
  font-family: "Segoe UI Emoji","Noto Color Emoji","Apple Color Emoji","Android Emoji",sans-serif !important;
}
div[data-testid="stButton"] > button[kind="primary"]:hover{
  background-color: #d32f2f !important;
  box-shadow: 0 6px 14px rgba(255,43,43,.45) !important;
}

/* ========================================================= */
/* 1. STYLE MẶC ĐỊNH TOÀN APP (Nút Tính toán, Phân tích...)  */
/* ========================================================= */

/* Secondary mặc định => MÀU XANH (Giống cũ) */
div[data-testid="stButton"] > button[kind="secondary"] {
    background-color: #28a745 !important;
    color: #fff !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 700 !important;
    box-shadow: 0 2px 4px rgba(0,0,0,.18) !important;
}

/* Hover của nút xanh */
div[data-testid="stButton"] > button[kind="secondary"]:hover {
    background-color: #218838 !important; /* Xanh đậm hơn */
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 12px rgba(0,0,0,.18) !important;
    color: #fff !important;
}

/* ========================================================= */
/* 2. NGOẠI LỆ: RIÊNG CÁC NÚT TRONG EXPANDER (Gợi ý kịch bản) */
/* ========================================================= */

/* Tìm thẻ stExpander chứa nút secondary => Ép thành TRONG SUỐT */
div[data-testid="stExpander"] div[data-testid="stButton"] > button[kind="secondary"] {
    background-color: #f8f9fa !important; /* <--- ĐỔI Ở ĐÂY (Xám siêu nhạt chuẩn UI) */
    color: #333 !important;
    border: 1px solid #d1d5db !important; /* Đổi viền sang xám lợt hơn chút cho tiệp màu */
    box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important; /* Thêm tí bóng nhẹ cho đẹp */
}

/* Hover của nút trong suốt => Hiện màu cam nhạt gợi ý */
div[data-testid="stExpander"] div[data-testid="stButton"] > button[kind="secondary"]:hover {
    background-color: #fff3e0 !important;
    border-color: #ff9800 !important;
    color: #e65100 !important;
    transform: none !important; /* Không nảy lên để đỡ rối mắt */
}

/* -----------------------------
   Cards / Boxes
------------------------------*/
.role-card {
    background-color: #e3f2fd;
    border-left: 6px solid var(--blue2);
    padding: 18px 18px;
    border-radius: 12px;
    margin-bottom: 18px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.08);
}
.role-title {
    color: var(--blue2);
    font-weight: 800;
    font-size: 18px;
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    gap: 8px;
}
.mission-text { color: #424242; font-style: italic; font-size: 15px; line-height: 1.55; }

.header-style {
    font-size: 26px;
    font-weight: 900;
    color: var(--blue);
    border-bottom: 2px solid #eee;
    padding-bottom: 10px;
    margin-bottom: 18px;
}

.result-box {
    background-color: #f1f8e9;
    padding: 14px 14px;
    border-radius: 10px;
    border: 1px solid #c5e1a5;
    color: #33691e;
    font-weight: 800;
}
.step-box {
    background-color: #fafafa;
    color: var(--text);
    padding: 14px 14px;
    border-radius: 10px;
    border: 1px dashed #bdbdbd;
    margin-bottom: 10px;
}
.explanation-box {
    background-color: #fff8e1;
    padding: 14px 14px;
    border-radius: 10px;
    border-left: 5px solid #ffb300;
    margin-top: 10px;
}
.ai-box {
    background-color: #fff3e0;
    padding: 18px;
    border-radius: 14px;
    border-left: 6px solid var(--orange);
    margin-top: 16px;
    box-shadow: 0 4px 8px rgba(0,0,0,0.05);
    color: var(--text) !important;
}
.ai-box h4 { color: #e65100 !important; font-weight: 900; margin: 0 0 8px 0; }
.ai-box p, .ai-box li { color: var(--text) !important; }

/* -----------------------------
   Sidebar cosmetics
------------------------------*/
section[data-testid="stSidebar"] { border-right: 1px solid #eee; }
section[data-testid="stSidebar"] .block-container { padding-top: 1rem; }

/* -----------------------------
   Mobile responsiveness
   (Stack columns, reduce paddings, fix overflow)
------------------------------*/
@media (max-width: 768px){
  .block-container { padding-left: 0.9rem; padding-right: 0.9rem; }
  .header-style { font-size: 22px; }
  .role-title { font-size: 16px; }
  .mission-text { font-size: 14px; }

  /* Stack Streamlit columns */
  div[data-testid="stHorizontalBlock"]{
      flex-direction: column !important;
      align-items: stretch !important;
      gap: 0.75rem !important;
  }
  div[data-testid="column"]{
      width: 100% !important;
      flex: 1 1 100% !important;
  }

  /* Make tables and charts scroll nicely */
  .stDataFrame, .stTable { overflow-x: auto; }
}

/* Footer */
.copyright {
    font-size: 12px;
    color: #888;
    text-align: center;
    margin-top: 36px;
}
</style>
        """,
        unsafe_allow_html=True,
    )


init_style()

# ==============================================================================
# 2) GEMINI CONFIG + HELPERS
# ==============================================================================
def get_api_key():
    api_key = None
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        api_key = os.getenv("GEMINI_API_KEY")
    return api_key


API_KEY = get_api_key()
if API_KEY:
    genai.configure(api_key=API_KEY)


def _force_vietnamese(text: str) -> str:
    """
    Gemini đôi khi trả về tiếng Anh. Ta ép lại nhẹ bằng:
    - Nếu có nhiều từ/phrase tiếng Anh phổ biến -> nhắc người dùng "AI trả lời VN"
    - Và cố gắng làm sạch vài heading/labels thường gặp.
    (Không dịch máy để tránh phụ thuộc API dịch; chủ yếu là ép prompt + cleanup nhẹ.)
    """
    if not text:
        return ""

    # Cleanup các nhãn hay xuất hiện
    replacements = {
        "Risk": "Rủi ro",
        "Recommendation": "Khuyến nghị",
        "Conclusion": "Kết luận",
        "Decision": "Quyết định",
        "GO": "GO (Vào lệnh)",
        "NO-GO": "NO-GO (Hủy)",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)

    # Nếu vẫn có nhiều tiếng Anh (heuristic đơn giản)
    en_hits = len(re.findall(r"\b(the|and|or|but|because|therefore|however|recommend|risk|should)\b", text.lower()))
    if en_hits >= 3:
        text = (
            "⚠️ (AI đôi lúc trả lời lẫn tiếng Anh) Dưới đây là nội dung đã được yêu cầu trả lời **tiếng Việt**:\n\n"
            + text
        )
    return text


def ask_gemini_advisor(role: str, context_data: str, task: str) -> str:
    """
    AI Advisor dùng chung.
    - Ép trả lời tiếng Việt.
    - Ngắn gọn 3–4 câu, tập trung rủi ro & khuyến nghị.
    """
    if not API_KEY:
        return "⚠️ Chưa cấu hình GEMINI_API_KEY. Vui lòng nhập key ở Sidebar hoặc môi trường."

    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        prompt = f"""
Bạn là: {role}.

Dữ liệu đầu vào:
{context_data}

Yêu cầu:
{task}

Ràng buộc bắt buộc:
- Trả lời hoàn toàn bằng TIẾNG VIỆT.
- Không dùng câu tiếng Anh, không chèn thuật ngữ tiếng Anh trừ ký hiệu chuẩn (NPV, IRR, WACC, UCP 600, BID/ASK).
- Văn phong: ngắn gọn, súc tích (khoảng 4-5 câu), đi thẳng vào rủi ro và khuyến nghị chuyên môn.
"""
        response = model.generate_content(prompt)
        return _force_vietnamese(getattr(response, "text", "") or "")
    except Exception as e:
        msg = str(e)
        if "429" in msg:
            return "⚠️ AI đang bận (quá tải). Vui lòng thử lại sau."
        if "404" in msg:
            return "⚠️ Lỗi Model: Tài khoản chưa hỗ trợ gemini-2.0-flash."
        return f"⚠️ Lỗi kết nối: {msg}"


def ask_gemini_macro(debt_increase, shock_percent, new_rate):
    """Giữ riêng cho Macro (bạn yêu cầu giữ như cũ), nhưng cũng ép tiếng Việt."""
    if not API_KEY:
        return "⚠️ Chưa cấu hình GEMINI_API_KEY. Vui lòng nhập key ở Sidebar hoặc môi trường."

    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        prompt = f"""
Đóng vai một Cố vấn Kinh tế cấp cao của Chính phủ.

Tình huống hiện tại:
- Đồng nội tệ vừa mất giá: {shock_percent}%
- Tỷ giá mới: {new_rate:,.0f} VND/USD
- Gánh nặng nợ công quốc gia vừa tăng thêm {debt_increase:,.0f} Tỷ VND do chênh lệch tỷ giá.

Yêu cầu:
- Viết báo cáo ngắn gọn (khoảng 4 gạch đầu dòng lớn) cảnh báo 4 tác động thực tế đến đời sống người dân và doanh nghiệp.
- Trả lời hoàn toàn bằng TIẾNG VIỆT (không dùng câu tiếng Anh).
- Văn phong trang trọng, cảnh báo rủi ro, chuyên nghiệp. Không lạm dụng Markdown đậm/nhạt.
"""
        response = model.generate_content(prompt)
        return _force_vietnamese(getattr(response, "text", "") or "")
    except Exception as e:
        return f"⚠️ Lỗi kết nối AI: {str(e)}"


# ==============================================================================
# 3) HEADER
# ==============================================================================
st.title("🏦 INTERNATIONAL FINANCE LAB")
st.caption("Hệ thống Mô phỏng Nghiệp vụ Tài chính Quốc tế với Trợ lý AI Gemini")

# ==============================================================================
# 4) SIDEBAR NAV + API KEY INPUT (OPTIONAL)
# ==============================================================================
with st.sidebar:

    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=50)
    st.markdown("### 🎓 Cổng Lab")      

    # 1. Nhập liệu
    # Dùng key='login_mssv' để Streamlit tự nhớ giá trị trong ô input
    input_mssv = st.text_input("Nhập MSSV kích hoạt AI:", key="login_mssv").strip()
    
    # 2. Xử lý logic xác thực
    valid_list = load_valid_students() # Hàm load Excel (đã có ở trên)
    
    # Mặc định là chưa đăng nhập
    st.session_state['CURRENT_USER'] = None 
    
    if input_mssv:
        # Kiểm tra xem có trong danh sách lớp không
        if input_mssv in valid_list:
            # A. Đăng nhập thành công -> Lưu vào Session State (QUAN TRỌNG)
            st.session_state['CURRENT_USER'] = input_mssv
            
            st.success(f"Xin chào: {input_mssv}")
            
            # [QUAN TRỌNG] Tạo một cái hộp rỗng và gán vào biến 'quota_placeholder'
            quota_placeholder = st.empty()
            # B. Hiển thị số lượt đã dùng ngay tại đây cho SV thấy
            tracker = get_usage_tracker()
            current_used = tracker.get(input_mssv, 0)
            
            # Đổi màu hiển thị cho sinh động
            if current_used < MAX_AI_QUOTA:
                quota_placeholder.caption(f"✅ Đã dùng: **{current_used}/{MAX_AI_QUOTA}** lượt gọi AI.")
            else:
                quota_placeholder.error(f"⛔ Đã dùng hết: **{current_used}/{MAX_AI_QUOTA}** lượt gọi AI.")
                
        else:
            # C. Nhập sai
            st.error("⛔ Danh sách lớp không có MSSV này! Bạn vẫn thực hành bình thường nhưng không được dùng AI.")
    else:
        st.info("Vui lòng nhập MSSV để được kích hoạt AI tư vấn.")
   
    # (Tuỳ chọn) nhập API key nhanh nếu chưa có
    # if not API_KEY:
    #     with st.expander("🔑 Nhập GEMINI_API_KEY (tuỳ chọn)", expanded=False):
    #         key_in = st.text_input("GEMINI_API_KEY", type="password", help="Nếu bạn chạy local và chưa set secrets/env.")
    #         if key_in:
    #             os.environ["GEMINI_API_KEY"] = key_in
    #             API_KEY = key_in
    #             genai.configure(api_key=API_KEY)
    #             st.success("Đã nạp API Key cho phiên chạy hiện tại.")
    st.markdown("---")
    st.header("🏢 SƠ ĐỒ TỔ CHỨC")
    st.write("Di chuyển đến:")

    room = st.radio(
        "Phòng nghiệp vụ:",
        [
            "1. Sàn Kinh doanh Ngoại hối (Dealing Room)",
            "2. Phòng Quản trị Rủi ro (Risk Management)",
            "3. Phòng Thanh toán Quốc tế (Trade Finance)",
            "4. Phòng Đầu tư Quốc tế (Investment Dept)",
            "5. Ban Chiến lược Vĩ mô (Macro Strategy)",
        ],
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.info("💡 Sau khi tính toán, hãy xem **Giải thích** hoặc gọi **Chuyên gia AI** để được tư vấn chuyên sâu.")
    st.markdown("---")
    st.caption("© 2026 - Nguyễn Minh Hải", help="Finance Lab – International Finance Simulation") 
    
    # st.markdown("---")
    # # --- PHẦN UI HƯỚNG DẪN CÀI ĐẶT ---
    # # Bạn có thể đặt đoạn này ở Sidebar hoặc cuối trang
    # with st.expander("📲 **Bấm vào đây để cài App lên điện thoại**", expanded=False):
    #     st.write("Chọn iOS hoặc Android và làm theo 2 bước sau:")
        
    #     # Tạo 2 tab hướng dẫn cho iPhone và Android
    #     tab_ios, tab_android = st.tabs(["🍏 iPhone (iOS)", "🤖 Android"])
        
    #     with tab_ios:
    #         st.markdown("""
    #         **Bước 1:** Bấm vào nút **Chia sẻ** (Share) trên thanh menu dưới cùng của Safari.  
    #         *(Biểu tượng hình vuông có mũi tên đi lên)* <div style="text-align: center; margin: 10px 0;">
    #             <span style="font-size: 30px;">↥</span> 
    #         </div>

    #         **Bước 2:** Kéo xuống và chọn dòng **"Thêm vào MH chính"** (Add to Home Screen).
            
    #         <div style="text-align: center; margin: 10px 0;">
    #             <span style="font-size: 30px;">➕</span>
    #         </div>
    #         """, unsafe_allow_html=True)
            
    #     with tab_android:
    #         st.markdown("""
    #         **Bước 1:** Bấm vào nút **Menu** (3 chấm dọc) ở góc trên bên phải Chrome.
            
    #         <div style="text-align: center; margin: 10px 0;">
    #             <span style="font-size: 30px;">⋮</span>
    #         </div>

    #         **Bước 2:** Chọn **"Cài đặt ứng dụng"** hoặc **"Thêm vào màn hình chính"**.
            
    #         <div style="text-align: center; margin: 10px 0;">
    #             <span style="font-size: 30px;">📲</span>
    #         </div>
    #         """, unsafe_allow_html=True)

    #     st.info("💡 **Mẹo:** Sau khi cài xong, App sẽ hiện icon trên màn hình chính và chạy toàn màn hình (không còn thanh địa chỉ web), giúp trải nghiệm mượt mà hơn!")


def footer():
    st.markdown(
        """
<div class="copyright">
© 2026 Designed by Nguyễn Minh Hải
</div>
        """,
        unsafe_allow_html=True,
    )


# ==============================================================================
# PHÒNG 1: DEALING ROOM
# ==============================================================================
def room_1_dealing():
    st.markdown('<p class="header-style">💱 Sàn Kinh doanh Ngoại hối (Dealing Room)</p>', unsafe_allow_html=True)
    st.markdown(
        """
<div class="role-card">
  <div class="role-title">👤 Vai diễn: Chuyên viên Kinh doanh Tiền tệ (FX Trader)</div>
  <div class="mission-text">"Nhiệm vụ: Niêm yết tỷ giá chéo (Cross-rate) và thực hiện kinh doanh chênh lệch giá (Arbitrage) khi phát hiện thị trường mất cân bằng."</div>
</div>
        """,
        unsafe_allow_html=True,
    )

    tab1, tab2 = st.tabs(["🔢 Niêm yết Tỷ giá Chéo", "⚡ Săn Arbitrage (Tam giác)"])

    # -------------------------
    # TAB 1: Cross-rate
    # -------------------------
    with tab1:
        st.subheader("🏦 Bảng điện tử Tỷ giá liên ngân hàng")
        st.caption("Nhập tỷ giá thị trường quốc tế và nội địa để tính tỷ giá chéo (EUR/VND).")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 🇺🇸 Thị trường 1: USD/VND")
            usd_bid = st.number_input("BID (NH Mua USD):", value=25350.0, step=10.0, format="%.0f", key="r1_usd_bid")
            usd_ask = st.number_input("ASK (NH Bán USD):", value=25450.0, step=10.0, format="%.0f", key="r1_usd_ask")
        with c2:
            st.markdown("##### 🇪🇺 Thị trường 2: EUR/USD")
            eur_bid = st.number_input("BID (NH Mua EUR):", value=1.0820, step=0.0001, format="%.4f", key="r1_eur_bid")
            eur_ask = st.number_input("ASK (NH Bán EUR):", value=1.0850, step=0.0001, format="%.4f", key="r1_eur_ask")

        st.markdown("---")

        if st.button("🚀 TÍNH TOÁN & NIÊM YẾT", key="btn_cross_rate", use_container_width=True):
            cross_bid = eur_bid * usd_bid
            cross_ask = eur_ask * usd_ask
            spread = cross_ask - cross_bid

            st.success(f"✅ TỶ GIÁ NIÊM YẾT (EUR/VND): {cross_bid:,.0f} - {cross_ask:,.0f}")
            st.info(f"📊 Spread (Chênh lệch Mua-Bán): {spread:,.0f} VND/EUR")

            with st.expander("🎓 GÓC HỌC TẬP: GIẢI MÃ CÔNG THỨC & SỐ LIỆU", expanded=False):
                st.markdown("#### 1. Công thức Toán học")
                st.latex(r"\text{EUR/VND}_{Bid} = \text{EUR/USD}_{Bid} \times \text{USD/VND}_{Bid}")
                st.latex(r"\text{EUR/VND}_{Ask} = \text{EUR/USD}_{Ask} \times \text{USD/VND}_{Ask}")

                st.divider()

                st.markdown("#### 2. Áp dụng số liệu bạn vừa nhập")
                st.write("Hệ thống đã thực hiện phép tính cụ thể như sau:")

                st.markdown(
                    f"""
**a) Tính Tỷ giá Mua (BID):**
$$
{eur_bid:.4f} \\times {usd_bid:,.0f} = \\mathbf{{{cross_bid:,.0f}}}
$$

**b) Tính Tỷ giá Bán (ASK):**
$$
{eur_ask:.4f} \\times {usd_ask:,.0f} = \\mathbf{{{cross_ask:,.0f}}}
$$

**c) Tính Spread:**
$$
{cross_ask:,.0f} - {cross_bid:,.0f} = \\mathbf{{{spread:,.0f}}}
$$
"""
                )

                st.divider()

                st.markdown("#### 3. Tại sao lại nhân `Bid × Bid`?")
                st.info(
                    """
Để Ngân hàng Việt Nam **mua EUR** từ khách hàng (trả VND), họ đi “đường vòng” qua USD:
1) **Bước 1:** Bán EUR lấy USD trên thị trường quốc tế → dùng **EUR/USD Bid** (giá đối tác mua EUR).
2) **Bước 2:** Bán USD lấy VND tại Việt Nam → dùng **USD/VND Bid** (giá thị trường mua USD).

👉 Kết luận: **Cross Bid = Bid × Bid**. Tương tự **Cross Ask = Ask × Ask**.
"""
                )

    # -------------------------
    # TAB 2: Triangular arbitrage
    # -------------------------
    with tab2:
        st.subheader("⚡ Săn Arbitrage (Kinh doanh chênh lệch giá)")
        st.caption("Mô phỏng arbitrage tam giác giữa 3 báo giá. Hệ thống tự chọn chiều giao dịch tối ưu.")

        # 1) Inputs
        capital = st.number_input("Vốn kinh doanh (USD):", value=1_000_000.0, step=10_000.0, format="%.0f", key="r1_capital")

        st.markdown("---")
        k1, k2, k3 = st.columns(3)
        with k1:
            bank_a = st.number_input("Bank A (USD/VND):", value=25_000.0, help="Giá bán USD lấy VND", key="r1_bank_a")
        with k2:
            bank_b = st.number_input("Bank B (EUR/USD):", value=1.1000, help="Giá bán EUR lấy USD", key="r1_bank_b")
        with k3:
            bank_c = st.number_input("Bank C (EUR/VND):", value=28_000.0, help="Giá bán EUR lấy VND", key="r1_bank_c")

        # Core compute (always compute to feed AI)
        fair_rate_c = bank_a * bank_b

        # Path 1: USD -> EUR -> VND -> USD
        path1_eur = capital / bank_b
        path1_vnd = path1_eur * bank_c
        path1_usd_final = path1_vnd / bank_a
        profit1 = path1_usd_final - capital

        # Path 2: USD -> VND -> EUR -> USD
        path2_vnd = capital * bank_a
        path2_eur = path2_vnd / bank_c
        path2_usd_final = path2_eur * bank_b
        profit2 = path2_usd_final - capital

        if profit1 > profit2 and profit1 > 0:
            best_direction = "Mua EUR (Bank B) ➔ Bán tại Bank C ➔ Đổi về Bank A"
            best_profit = profit1
        elif profit2 >= profit1 and profit2 > 0:
            best_direction = "Đổi VND (Bank A) ➔ Mua EUR (Bank C) ➔ Bán tại Bank B"
            best_profit = profit2
        else:
            best_direction = "Không có cơ hội (Thị trường cân bằng hoặc lỗ)"
            best_profit = 0.0

        st.markdown("---")

        if st.button("🚀 KÍCH HOẠT THUẬT TOÁN ARBITRAGE", key="btn_arbitrage", use_container_width=True):
            st.markdown("### 📝 Nhật ký giao dịch tối ưu:")

            # tránh nhiễu do làm tròn
            if profit1 > 1.0:
                st.success("✅ PHÁT HIỆN CƠ HỘI: Mua EUR (Bank B) ➔ Bán tại Bank C ➔ Đổi về Bank A")
                st.markdown(
                    f"""
<div class="step-box">
1. <b>Dùng USD mua EUR (tại Bank B):</b><br>
{capital:,.0f} / {bank_b} = <b>{path1_eur:,.2f} EUR</b><br><br>
2. <b>Bán EUR đổi lấy VND (tại Bank C):</b><br>
{path1_eur:,.2f} × {bank_c:,.0f} = <b>{path1_vnd:,.0f} VND</b> (Giá EUR ở C đang cao)<br><br>
3. <b>Đổi VND về lại USD (tại Bank A):</b><br>
{path1_vnd:,.0f} / {bank_a:,.0f} = <b>{path1_usd_final:,.2f} USD</b>
</div>
""",
                    unsafe_allow_html=True,
                )
                st.markdown(f'<div class="result-box">🎉 LỢI NHUẬN: +{profit1:,.2f} USD</div>', unsafe_allow_html=True)
                st.info(f"💡 Gợi ý cân bằng: chỉnh **Bank C** về **{fair_rate_c:,.0f}** (= {bank_a:,.0f} × {bank_b}).")

            elif profit2 > 1.0:
                st.success("✅ PHÁT HIỆN CƠ HỘI: Đổi VND (Bank A) ➔ Mua EUR (Bank C) ➔ Bán tại Bank B")
                st.markdown(
                    f"""
<div class="step-box">
1. <b>Đổi USD sang VND (tại Bank A):</b><br>
{capital:,.0f} × {bank_a:,.0f} = <b>{path2_vnd:,.0f} VND</b><br><br>
2. <b>Dùng VND mua EUR (tại Bank C):</b><br>
{path2_vnd:,.0f} / {bank_c:,.0f} = <b>{path2_eur:,.2f} EUR</b> (Giá EUR ở C đang rẻ)<br><br>
3. <b>Bán EUR đổi về USD (tại Bank B):</b><br>
{path2_eur:,.2f} × {bank_b} = <b>{path2_usd_final:,.2f} USD</b>
</div>
""",
                    unsafe_allow_html=True,
                )
                st.markdown(f'<div class="result-box">🎉 LỢI NHUẬN: +{profit2:,.2f} USD</div>', unsafe_allow_html=True)
                st.info(f"💡 Gợi ý cân bằng: chỉnh **Bank C** về **{fair_rate_c:,.0f}** (= {bank_a:,.0f} × {bank_b}).")

            else:
                st.balloons()
                st.warning("⚖️ Thị trường cân bằng (No Arbitrage). Cả 2 chiều giao dịch đều không sinh lời.")
                st.success(f"👏 Bạn đang ở vùng cân bằng: {bank_c:,.0f} ≈ {fair_rate_c:,.0f} (= {bank_a:,.0f} × {bank_b})")

            with st.expander("🎓 BẢN CHẤT: Tại sao có tiền lời?"):
                st.markdown(
                    """
**Nguyên lý:** Arbitrage tam giác (Triangular Arbitrage).

Máy tính so sánh 2 con đường:
- **Vòng 1:** USD ➔ EUR (Bank B) ➔ VND (Bank C) ➔ USD (Bank A)
- **Vòng 2:** USD ➔ VND (Bank A) ➔ EUR (Bank C) ➔ USD (Bank B)

Nếu chênh lệch đủ lớn, đi một vòng sẽ “đẻ” ra lợi nhuận.
"""
                )

        # Minh họa (cố định, tránh lệch)
        with st.container(border=True):
            st.markdown("##### 🔄 Minh họa dòng tiền kiếm lời:")
            st.graphviz_chart(
                """
digraph {
    rankdir=LR;
    node [fontname="Arial", shape=box, style="filled,rounded", fillcolor="#f0f2f6", color="#d1d5db"];
    edge [color="#555555", fontname="Arial", fontsize=10];

    MarketA [label="📉 Thị trường A\\n(Giá Thấp)", fillcolor="#e8f5e9", color="#4caf50", penwidth=2];
    MarketB [label="📈 Thị trường B\\n(Giá Cao)", fillcolor="#ffebee", color="#f44336", penwidth=2];
    Wallet [label="💰 TÚI TIỀN\\n(Lợi nhuận)", shape=ellipse, fillcolor="#fff9c4", color="#fbc02d", style=filled];

    MarketA -> MarketB [label="1. Mua thấp & Chuyển sang", color="#4caf50", penwidth=2];
    MarketB -> Wallet [label="2. Bán cao & Chốt lời", color="#f44336", penwidth=2];
}
""",
                use_container_width=True,
            )
            st.info("💡 Dễ hiểu: mua ở nơi rẻ hơn và bán ngay ở nơi đắt hơn, trước khi giá kịp điều chỉnh.")

        # AI
        st.markdown("---")
        if st.button("AI Advisor – FX Arbitrage", type="primary", icon="🤖", key="btn_ai_risk"):
            # BƯỚC 1: KIỂM TRA ĐĂNG NHẬP (Lấy từ Session State)
            # Lấy ID từ session ra, nếu không có thì trả về None
            user_id = st.session_state.get('CURRENT_USER') 

            if not user_id:
                st.error("🔒 Bạn chưa đăng nhập đúng MSSV ở thanh bên trái!")
                st.toast("Vui lòng nhập MSSV để tiếp tục!", icon="🔒")
                st.stop() # Dừng lại ngay, không chạy tiếp

            # BƯỚC 2: KIỂM TRA HẠN MỨC (QUOTA)
            tracker = get_usage_tracker()
            current_used = tracker.get(user_id, 0)
            
            if current_used >= MAX_AI_QUOTA:
                st.warning(f"⚠️ Sinh viên {user_id} đã hết lượt dùng AI ({MAX_AI_QUOTA}/{MAX_AI_QUOTA}).")
                st.stop()

            # 3. Chuẩn bị dữ liệu
            context = f"""
            Tình huống: Arbitrage Tam giác.
            - Vốn: {capital:,.0f} USD
            - Tỷ giá: A={bank_a}, B={bank_b}, C={bank_c}
            - Kết quả: {best_direction}
            - Lợi nhuận: {best_profit:,.2f} USD
            """
            
            task = "Phân tích rủi ro khớp lệnh, chi phí vốn và đưa ra quyết định GO/NO-GO."

            # 4. Gọi AI và Xử lý lỗi
            with st.spinner(f"AI đang phân tích... (Lượt gọi AI thứ {current_used + 1}/{MAX_AI_QUOTA})"):
                try:
                    advise_result = ask_gemini_advisor("Senior FX Trader", context, task)

                    # KIỂM TRA: Nếu kết quả trả về bắt đầu bằng ⚠️ nghĩa là có lỗi
                    if advise_result.startswith("⚠️"):
                        st.error(advise_result) # Hiện lỗi cho GV/SV biết
                        st.info("Lượt này chưa bị trừ do lỗi hệ thống.")
                    else:
                        # 1. Trừ quota trong Database/File
                        consume_quota(user_id)
                        
                        # 2. CẬP NHẬT SIDEBAR NGAY LẬP TỨC (Không cần Rerun)
                        # Lấy số mới để hiển thị
                        new_usage = current_used + 1
                        
                        # Bắn nội dung mới vào cái hộp "quota_placeholder" đang nằm bên Sidebar
                        # Lưu ý: Bạn cần đảm bảo biến 'quota_placeholder' truy cập được từ đây
                        quota_placeholder.info(f"Đã dùng: {new_usage}/{MAX_AI_QUOTA} lượt")
                        
                        # 3. Hiện kết quả AI ra màn hình chính
                        st.markdown(f'<div class="ai-box"><h4>🤖 LỜI KHUYÊN CỦA NHÀ GIAO DỊCH AI</h4>{advise_result}</div>', unsafe_allow_html=True)                        
                except Exception as e:
                    st.error(f"⚠️ Lỗi khi gọi AI: {str(e)}")

    footer()


# ==============================================================================
# PHÒNG 2: RISK MANAGEMENT
# ==============================================================================
def room_2_risk():
    st.markdown('<p class="header-style">🛡️ Phòng Quản trị Rủi ro (Risk Management)</p>', unsafe_allow_html=True)

    st.subheader("1. Hồ sơ Khoản nợ (Debt Profile)")
    c1, c2 = st.columns(2)
    with c1:
        debt_amount = st.number_input("Giá trị khoản phải trả (USD):", value=1_000_000.0, step=10_000.0, format="%.0f", key="r2_debt")
    with c2:
        days_loan_profile = st.number_input("Thời hạn thanh toán (Ngày):", value=90, step=30, key="r2_days_profile")

    st.markdown(
        f"""
<div class="role-card">
  <div class="role-title">👤 Vai diễn: Giám đốc Tài chính (CFO)</div>
  <div class="mission-text">"Nhiệm vụ: Tính toán tỷ giá kỳ hạn hợp lý và lựa chọn công cụ phòng vệ (Forward/Option) tối ưu cho khoản nợ <b>{debt_amount:,.0f} USD</b> đáo hạn sau <b>{days_loan_profile} ngày</b>."</div>
</div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # IRP
    st.subheader("2. Tính Tỷ giá Kỳ hạn (Fair Forward Rate)")
    st.caption("Định giá Forward dựa trên chênh lệch lãi suất VND và USD (IRP).")

    c_input1, c_input2, c_input3, c_input4 = st.columns(4)
    with c_input1:
        spot_irp = st.number_input("Spot Rate (Hiện tại):", value=25_000.0, step=10.0, format="%.0f", key="r2_spot")
    with c_input2:
        r_vnd = st.number_input("Lãi suất VND (%/năm):", value=6.0, step=0.1, key="r2_rvnd")
    with c_input3:
        r_usd = st.number_input("Lãi suất USD (%/năm):", value=3.0, step=0.1, key="r2_rusd")
    with c_input4:
        days_loan = st.number_input("Kỳ hạn (Ngày):", value=90, step=30, key="r2_days_irp")

    numerator = 1 + (r_vnd / 100) * (days_loan / 360)
    denominator = 1 + (r_usd / 100) * (days_loan / 360)
    fwd_cal = spot_irp * (numerator / denominator)
    swap_point = fwd_cal - spot_irp

    st.markdown("---")
    col_res_irp1, col_res_irp2 = st.columns([1, 1.5])

    with col_res_irp1:
        st.markdown("##### 🏁 KẾT QUẢ TÍNH TOÁN")
        st.metric("Tỷ giá Forward (F)", f"{fwd_cal:,.0f} VND", help="Tỷ giá kỳ hạn hợp lý theo IRP")
        st.metric(
            "Điểm kỳ hạn (Swap Point)",
            f"{swap_point:,.0f} VND",
            delta="VND giảm giá (Forward > Spot)" if swap_point > 0 else "VND tăng giá (Forward < Spot)",
            delta_color="inverse",
        )

        if r_vnd > r_usd:
            st.warning(f"📉 Lãi suất VND cao hơn USD ({r_vnd}% > {r_usd}%) ⇒ VND thường bị “trừ điểm” (Forward cao hơn Spot).")
        else:
            st.success("📈 Lãi suất VND thấp hơn USD ⇒ VND thường được “cộng điểm” (Forward thấp hơn Spot).")

    with col_res_irp2:
        with st.expander("🎓 GÓC HỌC TẬP: GIẢI MÃ IRP & CÔNG THỨC", expanded=False):
            st.markdown("#### 1. IRP là gì?")
            st.info(
                """
**IRP (Interest Rate Parity – Ngang giá lãi suất)**:
Chênh lệch lãi suất giữa hai đồng tiền sẽ phản ánh vào chênh lệch giữa **Forward** và **Spot**.

Nói ngắn gọn: **Chênh lệch lãi suất = Chênh lệch tỷ giá kỳ hạn** (trong điều kiện không arbitrage).
"""
            )

            st.markdown("#### 2. Công thức tính Forward")
            st.latex(r"F = S \times \frac{1 + r_{VND} \times \frac{n}{360}}{1 + r_{USD} \times \frac{n}{360}}")
            st.caption("Thay số theo dữ liệu bạn nhập:")
            st.latex(
                f"F = {spot_irp:,.0f} \\times \\frac{{1 + {r_vnd}\\% \\times \\frac{{{days_loan}}}{{360}}}}{{1 + {r_usd}\\% \\times \\frac{{{days_loan}}}{{360}}}} = \\mathbf{{{fwd_cal:,.0f}}}"
            )

            st.divider()

            st.markdown("#### 3. Điểm kỳ hạn (Swap Point)")
            st.latex(f"\\text{{Swap}} = {fwd_cal:,.0f} - {spot_irp:,.0f} = \\mathbf{{{swap_point:,.0f}}}")

            st.divider()

            st.markdown("#### 4. Tại sao có quy luật này?")
            st.write(
                f"""
Theo nguyên lý **No Arbitrage**:
- Nếu lãi VND cao ({r_vnd}%) mà tỷ giá tương lai không giảm, nhà đầu tư sẽ bán USD để nắm VND gửi hưởng chênh lệch.
- Để triệt tiêu “bữa trưa miễn phí”, thị trường thường buộc VND **mất giá trong tương lai** tương ứng phần lãi suất cao hơn.
"""
            )

    st.markdown("---")
    st.subheader("3. So sánh Chiến lược Phòng vệ")

    st.info(
        """
💡 **HƯỚNG DẪN SINH VIÊN (TRY IT):**
- Để **Option thắng Forward**: đặt `Strike + Phí` < `Forward`, đồng thời kéo `Dự báo tỷ giá` lên cao.
- Để **Forward thắng Option**: chỉnh `Forward` thấp hơn tổng chi phí Option.
- Để **Thả nổi thắng**: kéo `Dự báo tỷ giá` xuống thấp hơn cả Forward và Option.
"""
    )

    col_strat1, col_strat2 = st.columns(2)
    with col_strat1:
        st.markdown("#### 🏦 Chốt Deal với Ngân hàng")
        f_rate_input = st.number_input(
            "Giá Forward Bank chào:",
            value=float(f"{fwd_cal:.2f}"),
            help="Thường Bank sẽ chào giá này hoặc cao hơn chút ít.",
            key="r2_fwd_offer",
        )
        st.markdown("**Thông số Quyền chọn (Option):**")
        strike = st.number_input("Strike Price (Giá thực hiện):", value=25_100.0, key="r2_strike")
        premium = st.number_input("Phí Option (VND/USD):", value=100.0, key="r2_premium")

    with col_strat2:
        st.markdown("#### 🔮 Dự báo Thị trường")
        future_spot = st.slider(
            f"Dự báo Spot sau {days_loan} ngày:",
            24_000.0,
            26_000.0,
            25_400.0,
            step=10.0,
            key="r2_future_spot",
        )

        if future_spot > f_rate_input:
            st.warning(
                f"""
🔥 **Cảnh báo:** Spot dự báo ({future_spot:,.0f}) cao hơn Forward ({f_rate_input:,.0f}).

👉 **Nên phòng vệ:** Forward/Option đều giúp né mức giá cao.
"""
            )
        else:
            st.success(
                f"""
❄️ **Thị trường hạ nhiệt:** Spot dự báo ({future_spot:,.0f}) thấp hơn Forward ({f_rate_input:,.0f}).

👉 **Cân nhắc:** Thả nổi hoặc Option (bỏ quyền) có thể lợi hơn Forward.
"""
            )

    # Costs
    cost_open = debt_amount * future_spot
    formula_open = f"{debt_amount:,.0f} × {future_spot:,.0f}"

    cost_fwd = debt_amount * f_rate_input
    formula_fwd = f"{debt_amount:,.0f} × {f_rate_input:,.0f}"

    if future_spot > strike:
        action_text = "Thực hiện quyền"
        price_base = strike
        explanation_opt = "✅Đã được bảo hiểm (Dùng Strike)"
        formula_opt = f"{debt_amount:,.0f} × ({strike:,.0f} + {premium:,.0f})"
    else:
        action_text = "Bỏ quyền (Lapse)"
        price_base = future_spot
        explanation_opt = "📉Mua giá chợ (Rẻ hơn Strike)"
        formula_opt = f"{debt_amount:,.0f} × ({future_spot:,.0f} + {premium:,.0f})"

    effective_opt_rate = price_base + premium
    cost_opt = debt_amount * effective_opt_rate

    
    # --- BƯỚC 1: TẠO DATAFRAME ---
    df_compare = pd.DataFrame(
        {
            "Chiến lược": ["1. Thả nổi (No Hedge)", "2. Kỳ hạn (Forward)", "3. Quyền chọn (Option)"],
            "Trạng thái": ["Chấp nhận rủi ro", "Khóa cứng tỷ giá", explanation_opt],
            "Tỷ giá thực tế": [future_spot, f_rate_input, effective_opt_rate],
            "Tổng chi phí (VND)": [cost_open, cost_fwd, cost_opt],
        }
    )

    # --- BƯỚC 1: ÉP KIỂU SỐ (Để đảm bảo tính toán đúng) ---
    df_compare["Tỷ giá thực tế"] = df_compare["Tỷ giá thực tế"].astype(float)
    df_compare["Tổng chi phí (VND)"] = df_compare["Tổng chi phí (VND)"].astype(float)

    # --- BƯỚC 2: CẤU HÌNH COLUMN CONFIG (Chỉ dùng để chỉnh độ rộng và tiêu đề) ---
    # LƯU Ý: Đã XÓA dòng format="%,.0f" ở đây để tránh xung đột
    column_config_setup = {
        "Chiến lược": st.column_config.TextColumn("Chiến lược", width="medium", pinned=True),
        "Trạng thái": st.column_config.TextColumn("Trạng thái", width="medium"),
        "Tỷ giá thực tế": st.column_config.Column("Tỷ giá", width="small"), # Dùng Column thường
        "Tổng chi phí (VND)": st.column_config.Column("Chi phí (VND)", width="medium"),
    }

    # --- BƯỚC 3: XỬ LÝ STYLE (Tô màu + Format dấu phẩy + Canh phải) ---
    min_cost = df_compare["Tổng chi phí (VND)"].min()

    # Hàm tô màu nền
    def highlight_best(s):
        return ['background-color: #d1e7dd; color: #0f5132; font-weight: bold' if v == min_cost else '' for v in s]

    # TẠO STYLER OBJECT (Chuỗi xử lý liên hoàn)
    styled_df = (
        df_compare.style
        .apply(highlight_best, subset=["Tổng chi phí (VND)"])             # 1. Tô màu dòng tốt nhất
        .format("{:,.0f}", subset=["Tỷ giá thực tế", "Tổng chi phí (VND)"]) # 2. Format dấu phẩy (25000 -> 25,000)
        # 3. QUAN TRỌNG: Ép canh lề phải bằng CSS (Vì sau khi format nó biến thành text)
        .set_properties(subset=["Tỷ giá thực tế", "Tổng chi phí (VND)"], **{'text-align': 'right'})
    )

    st.markdown("##### 📊 So sánh hiệu quả các chiến lược:")

    st.dataframe(
        styled_df, 
        column_config=column_config_setup,
        use_container_width=False, 
        hide_index=True 
    )
    
    # --- BƯỚC 3: KẾT LUẬN & GIẢI THÍCH ---

    best_idx = df_compare["Tổng chi phí (VND)"].idxmin()
    best_strat = df_compare.loc[best_idx, "Chiến lược"]
    st.markdown(f"### 🏆 KẾT LUẬN: Chọn **{best_strat}**")

    if best_idx == 1:
        st.success(
            f"""
**Vì sao chọn Forward?**
- Forward ({f_rate_input:,.0f}) rẻ hơn Spot dự báo ({future_spot:,.0f}).
- Rẻ hơn Option (vì Option phải cộng premium thành {effective_opt_rate:,.0f}).

👉 Hợp doanh nghiệp thích “chốt chi phí” chắc chắn.
"""
        )
    elif best_idx == 2:
        st.success(
            f"""
**Vì sao chọn Option?**
- Tổng chi phí Option đang thấp nhất (đã gồm premium).
- Khi thị trường bùng nổ, Option “chặn trần” bằng Strike ({strike:,.0f}) thay vì mua theo Spot cao.

👉 Option mạnh khi biến động lớn và bạn muốn giữ “quyền chọn cơ hội”.
"""
        )
    else:
        st.warning(
            f"""
**Vì sao chọn Thả nổi?**
- Bạn kỳ vọng tỷ giá giảm ({future_spot:,.0f}) ⇒ chốt Forward/Option lúc này có thể lãng phí.

👉 *Rủi ro cao*: dự báo sai sẽ đội chi phí rất mạnh.
"""
        )

    st.markdown("---")
    # --- PHẦN NÚT BẤM AI ---
    if st.button("AI Advisor – FX Hedging", type="primary", icon="🤖", key="btn_ai_cfo"):
        
        # BƯỚC 1: LẤY USER ID
        user_id = st.session_state.get('CURRENT_USER') 

        # TRƯỜNG HỢP 1: CHƯA ĐĂNG NHẬP
        if not user_id:
            st.error("🔒 Bạn chưa đăng nhập đúng MSSV ở thanh bên trái!")
            st.toast("Vui lòng nhập MSSV để tiếp tục!", icon="🔒")
            # QUAN TRỌNG: Không có st.stop() ở đây.
            # Code sẽ bỏ qua phần 'else' bên dưới và chạy thẳng xuống Mục 4.

        # TRƯỜNG HỢP 2: ĐÃ ĐĂNG NHẬP (Xử lý tiếp Quota và AI trong khối này)
        else:
            # BƯỚC 2: KIỂM TRA HẠN MỨC (QUOTA)
            tracker = get_usage_tracker()
            current_used = tracker.get(user_id, 0)
            
            if current_used >= MAX_AI_QUOTA:
                # Hết lượt -> Báo cảnh báo
                st.warning(f"⚠️ Sinh viên {user_id} đã hết lượt dùng AI ({MAX_AI_QUOTA}/{MAX_AI_QUOTA}).")
            
            else:
                # Còn lượt -> Chạy AI (Toàn bộ logic AI nằm trong này)
                
                # 3. Chuẩn bị dữ liệu
                context = f"""
    Bài toán: Nợ {debt_amount:,.0f} USD.
    Spot hiện tại: {spot_irp:,.0f}; Kỳ hạn: {days_loan} ngày.

    Phương án:
    1) Thả nổi @ {future_spot:,.0f} ⇒ {cost_open:,.0f} VND
    2) Forward @ {f_rate_input:,.0f} ⇒ {cost_fwd:,.0f} VND
    3) Option: Strike {strike:,.0f} + Premium {premium:,.0f} (tỷ giá hiệu dụng {effective_opt_rate:,.0f}) ⇒ {cost_opt:,.0f} VND

    Kết quả máy tính chọn: {best_strat}
    """
                task = "Nhận xét kết quả. Phân tích 'chi phí cơ hội' của Forward và 'giá trị quyền' của Option (trong 3-4 câu)."
                
                with st.spinner(f"AI đang phân tích chiến lược...(Lượt gọi AI thứ {current_used + 1}/{MAX_AI_QUOTA})"):
                    try:
                        advise = ask_gemini_advisor("CFO Expert", context, task)
                        
                        if advise.startswith("⚠️"):
                            st.error(advise)
                            st.info("Lượt này chưa bị trừ do lỗi hệ thống.")
                        else:
                            # 1. Trừ quota
                            consume_quota(user_id)
                            
                            # 2. Cập nhật Sidebar (nếu có placeholder)
                            if 'quota_placeholder' in locals() or 'quota_placeholder' in globals():
                                new_usage = current_used + 1
                                quota_placeholder.info(f"Đã dùng: {new_usage}/{MAX_AI_QUOTA} lượt")
                            
                            # 3. Hiện kết quả
                            st.markdown(f'<div class="ai-box"><h4>🤖 GÓC NHÌN TỪ GIÁM ĐỐC TÀI CHÍNH AI</h4>{advise}</div>', unsafe_allow_html=True)
                        
                    except Exception as e:
                        st.error(f"⚠️ Lỗi khi gọi AI: {str(e)}")

    # =========================================================
    # MỤC 4 (NẰM NGOÀI MỌI KHỐI IF CỦA BUTTON)
    # =========================================================
    # Vì không dùng st.stop() ở trên, nên dù chưa đăng nhập hay lỗi gì
    # Code vẫn trôi xuống đây và hiển thị mục 4 bình thường.
    st.markdown("---")
    st.subheader("4. Tình huống nâng cao: Xử lý khi Lệch dòng tiền (Swap)")
    
    with st.expander("🔄 MỞ RỘNG: Dòng tiền bị trễ hạn, phải làm sao?", expanded=False):
        st.markdown(
            """
            <div class="mission-text">
            🚨 <b>Tình huống:</b> Hợp đồng Forward cũ đã đến ngày đáo hạn, nhưng đối tác báo 
            <b>delay thanh toán thêm 30 ngày</b> nữa. Bạn chưa cần USD ngay lúc này, nhưng ngân hàng bắt buộc tất toán Deal cũ.
            <br>👉 <b>Giải pháp:</b> Dùng <b>FX Swap</b> (Bán Spot tất toán cũ - Mua Forward kỳ hạn mới).
            </div>
            """, unsafe_allow_html=True
        )

        c_swap1, c_swap2 = st.columns(2)
        with c_swap1:
            delay_days = st.number_input("Số ngày delay:", value=30, step=15, key="swap_days")
            # Giả định Spot tại thời điểm đáo hạn Deal cũ
            spot_at_maturity = st.number_input(
                "Spot rate tại ngày đáo hạn Deal cũ:", 
                value=spot_irp, # Lấy tạm giá hiện tại làm ví dụ
                help="Giá thị trường tại thời điểm Deal cũ hết hạn",
                key="swap_spot_mat"
            )
        
        with c_swap2:
            # Tính lại Forward mới cho kỳ hạn delay
            # Công thức đơn giản hóa giả định lãi suất không đổi
            num_swap = 1 + (r_vnd / 100) * (delay_days / 360)
            den_swap = 1 + (r_usd / 100) * (delay_days / 360)
            new_fwd_rate = spot_at_maturity * (num_swap / den_swap)
            
            st.metric("Tỷ giá Forward mới (cho kỳ hạn delay)", f"{new_fwd_rate:,.0f} VND")
            swap_points_new = new_fwd_rate - spot_at_maturity
            st.metric("Điểm Swap (Swap Point)", f"{swap_points_new:,.0f} VND")

        st.markdown("#### 🧮 Hạch toán chi phí Swap (Rollover)")
        
        # 1. Tất toán Deal cũ: Mua Forward giá f_rate_input, giờ bán lại giá Spot thị trường (spot_at_maturity)
        # Nếu Spot < Forward cũ => Lỗ (vì cam kết mua cao, giờ bán ra thấp)
        settlement_pl = (spot_at_maturity - f_rate_input) * debt_amount
        
        # 2. Chi phí giữ trạng thái thêm X ngày (Swap cost)
        # Chênh lệch lãi suất thể hiện qua Swap Point
        swap_cost_total = swap_points_new * debt_amount

        col_cal1, col_cal2 = st.columns(2)
        
        with col_cal1:
            st.markdown("**1. Tất toán Deal cũ (Realized P/L):**")
            st.latex(r"\text{P/L} = (S_{maturity} - F_{old}) \times \text{Volume}")
            st.write(f"= ({spot_at_maturity:,.0f} - {f_rate_input:,.0f}) × {debt_amount:,.0f}")
            if settlement_pl >= 0:
                st.success(f"💰 Lãi từ chênh lệch giá: {settlement_pl:,.0f} VND")
            else:
                st.error(f"💸 Lỗ tất toán vị thế cũ: {settlement_pl:,.0f} VND")
        
        with col_cal2:
            st.markdown("**2. Chi phí Swap (Time Value):**")
            st.latex(r"\text{Cost} = \text{Swap Point} \times \text{Volume}")
            st.write(f"= ({new_fwd_rate:,.0f} - {spot_at_maturity:,.0f}) × {debt_amount:,.0f}")
            
            if swap_points_new > 0:
                 st.warning(f"📉 Bạn phải trả thêm (VND lãi cao hơn USD): {swap_cost_total:,.0f} VND")
            else:
                 st.success(f"📈 Bạn được nhận thêm (Swap Point âm): {abs(swap_cost_total):,.0f} VND")

        total_swap_impact = settlement_pl - swap_cost_total # P/L cũ - Chi phí Swap mới (tùy convention, ở đây để đơn giản ta cộng gộp)
        
        st.info(
            f"""
            💡 **Bài học:** Khi gia hạn nợ bằng Swap, bạn không chỉ quan tâm tỷ giá mới, mà phải xử lý phần chênh lệch (Lãi/Lỗ) của hợp đồng cũ ngay lập tức.
            """
        )

    footer()


# ==============================================================================
# PHÒNG 3: TRADE FINANCE
# ==============================================================================
def room_3_trade():
    st.markdown('<p class="header-style">🚢 Phòng Thanh toán Quốc tế (Trade Finance)</p>', unsafe_allow_html=True)
    st.markdown(
        """
<div class="role-card">
  <div class="role-title">👤 Vai diễn: Chuyên viên Thanh toán Quốc tế</div>
  <div class="mission-text">"Nhiệm vụ: Tư vấn phương thức thanh toán tối ưu chi phí và kiểm tra bộ chứng từ (Checking) theo chuẩn UCP 600."</div>
</div>
        """,
        unsafe_allow_html=True,
    )

    tab_cost, tab_check = st.tabs(["💰 Bài toán Chi phí (T/T, Nhờ thu, L/C)", "📝 Kiểm tra Chứng từ (Checking)"])

    # -------------------------
    # TAB COST
    # -------------------------
    with tab_cost:
        st.subheader("💸 Bài toán Tối ưu Chi phí Thanh toán Quốc tế")
        st.caption("So sánh: Phí ngân hàng & Chi phí vốn (lãi) giữa T/T, Nhờ thu, L/C.")

        with st.expander("📝 BƯỚC 1: NHẬP GIÁ TRỊ HỢP ĐỒNG & LÃI SUẤT", expanded=True):
            c1, c2 = st.columns(2)
            with c1:
                val = st.number_input("Giá trị hợp đồng (USD):", value=100_000.0, step=1_000.0, key="r3_val")
                interest_rate = st.number_input(
                    "Lãi suất vay vốn (%/năm):",
                    value=7.0,
                    step=0.1,
                    help="Dùng để tính chi phí cơ hội/lãi vay trong thời gian chờ thanh toán",
                    key="r3_ir",
                )
            with c2:
                days_tt = st.number_input("Số ngày đọng vốn T/T:", value=5, help="Thời gian tiền đi trên đường", key="r3_days_tt")
                days_col = st.number_input("Số ngày đọng vốn Nhờ thu:", value=15, help="Thời gian gửi chứng từ", key="r3_days_col")
                days_lc = st.number_input("Số ngày đọng vốn L/C:", value=30, help="Thời gian xử lý bộ chứng từ", key="r3_days_lc")

        st.markdown("---")
        st.subheader("🏦 BƯỚC 2: CẤU HÌNH BIỂU PHÍ NGÂN HÀNG")

        col_tt, col_col, col_lc = st.columns(3)

        with col_tt:
            st.markdown("#### 1) T/T (Chuyển tiền)")
            tt_pct = st.number_input("Phí chuyển tiền (%):", value=0.2, step=0.01, format="%.2f", key="r3_tt_pct")
            tt_min = st.number_input("Min (USD) - T/T:", value=10.0, key="r3_tt_min")
            tt_max = st.number_input("Max (USD) - T/T:", value=200.0, key="r3_tt_max")
            tt_other = st.number_input("Điện phí (USD):", value=20.0, key="r3_tt_other")

        with col_col:
            st.markdown("#### 2) Nhờ thu (D/P, D/A)")
            col_pct = st.number_input("Phí nhờ thu (%):", value=0.15, step=0.01, format="%.2f", key="r3_col_pct")
            col_min = st.number_input("Min (USD) - Col:", value=20.0, key="r3_col_min")
            col_max = st.number_input("Max (USD) - Col:", value=250.0, key="r3_col_max")
            col_other = st.number_input("Bưu điện phí (USD):", value=50.0, key="r3_col_other")

        with col_lc:
            st.markdown("#### 3) L/C (Tín dụng thư)")
            lc_open_pct = st.number_input("Phí mở L/C (%):", value=0.3, step=0.01, format="%.2f", key="r3_lc_open")
            lc_pay_pct = st.number_input("Phí thanh toán (%):", value=0.2, step=0.01, format="%.2f", key="r3_lc_pay")
            lc_min = st.number_input("Min (USD) - L/C:", value=50.0, key="r3_lc_min")
            lc_other = st.number_input("Phí khác (USD):", value=100.0, help="Tu chỉnh, bất hợp lệ...", key="r3_lc_other")

        st.markdown("---")

        if st.button("🚀 TÍNH TOÁN & SO SÁNH NGAY", key="btn_tf_cost", use_container_width=True):
            def calculate_fee_min_max(amount, pct, fee_min, fee_max):
                raw_fee = amount * (pct / 100)
                final_fee = max(fee_min, min(raw_fee, fee_max))
                return final_fee, raw_fee

            # T/T
            tt_bank_fee, tt_raw = calculate_fee_min_max(val, tt_pct, tt_min, tt_max)
            tt_total_bank = tt_bank_fee + tt_other
            tt_interest = val * (interest_rate / 100) * (days_tt / 360)
            tt_final = tt_total_bank + tt_interest

            # Collection
            col_bank_fee, col_raw = calculate_fee_min_max(val, col_pct, col_min, col_max)
            col_total_bank = col_bank_fee + col_other
            col_interest = val * (interest_rate / 100) * (days_col / 360)
            col_final = col_total_bank + col_interest

            # L/C
            lc_open_fee = max(lc_min, val * (lc_open_pct / 100))
            lc_pay_fee = val * (lc_pay_pct / 100)
            lc_total_bank = lc_open_fee + lc_pay_fee + lc_other
            lc_interest = val * (interest_rate / 100) * (days_lc / 360)
            lc_final = lc_total_bank + lc_interest

            st.subheader("📊 Kết quả Tổng hợp")
            m1, m2, m3 = st.columns(3)
            best_price = min(tt_final, col_final, lc_final)

            m1.metric("1) Tổng phí T/T", f"${tt_final:,.2f}", delta="Rẻ nhất (rủi ro cao)" if tt_final == best_price else None, delta_color="inverse")
            m2.metric("2) Tổng phí Nhờ thu", f"${col_final:,.2f}", delta=f"+${col_final - tt_final:,.2f} vs T/T", delta_color="off")
            m3.metric("3) Tổng phí L/C", f"${lc_final:,.2f}", delta=f"+${lc_final - tt_final:,.2f} vs T/T", delta_color="off")

            chart_data = pd.DataFrame(
                {
                    "Phương thức": ["T/T", "Nhờ thu", "L/C"],
                    "Phí Ngân hàng": [tt_total_bank, col_total_bank, lc_total_bank],
                    "Chi phí Vốn (Lãi)": [tt_interest, col_interest, lc_interest],
                }
            )
            st.bar_chart(chart_data.set_index("Phương thức"), stack=True, color=["#FF6C6C", "#4B4BFF"])

            st.markdown("### 🧮 Bảng chi tiết lời giải (Step-by-step)")
            st.info("Dưới đây là cách tính chi tiết giúp bạn hiểu rõ nguồn gốc các con số:")

            with st.expander("1️⃣ Chi tiết tính toán: T/T (Chuyển tiền)", expanded=False):
                st.latex(r"Cost_{T/T} = \text{Phí Bank} + \text{Lãi Vốn}")
                st.markdown(
                    f"""
**A) Phí dịch vụ Ngân hàng**
- Sơ bộ: {val:,.0f} × {tt_pct}% = {tt_raw:,.2f}
- Áp dụng Min/Max ({tt_min} – {tt_max}) ⇒ **{tt_bank_fee:,.2f}**
- Cộng điện phí {tt_other:,.2f} ⇒ **Tổng phí bank: {tt_total_bank:,.2f}**

**B) Chi phí vốn (lãi)**
- Công thức: Giá trị × Lãi suất × Ngày/360
- Thế số: {val:,.0f} × {interest_rate}% × ({days_tt}/360) = **{tt_interest:,.2f}**
"""
                )

            with st.expander("2️⃣ Chi tiết tính toán: Nhờ thu (Collection)", expanded=False):
                st.latex(r"Cost_{Col} = \text{Phí Nhờ Thu} + \text{Phí Khác} + \text{Lãi Vốn}")
                st.markdown(
                    f"""
**A) Phí dịch vụ Ngân hàng**
- Sơ bộ: {val:,.0f} × {col_pct}% = {col_raw:,.2f}
- Áp dụng Min/Max ({col_min} – {col_max}) ⇒ **{col_bank_fee:,.2f}**
- Cộng phí khác {col_other:,.2f} ⇒ **Tổng phí bank: {col_total_bank:,.2f}**

**B) Chi phí vốn**
- {val:,.0f} × {interest_rate}% × ({days_col}/360) = **{col_interest:,.2f}**
"""
                )

            with st.expander("3️⃣ Chi tiết tính toán: L/C (Tín dụng thư)", expanded=False):
                st.latex(r"Cost_{LC} = \text{Phí Mở} + \text{Phí T.Toán} + \text{Phí Khác} + \text{Lãi Vốn}")
                st.markdown(
                    f"""
**A) Các loại phí**
- Phí mở: {val:,.0f} × {lc_open_pct}% = {val*(lc_open_pct/100):,.2f} ⇒ áp Min {lc_min} ⇒ **{lc_open_fee:,.2f}**
- Phí thanh toán: {val:,.0f} × {lc_pay_pct}% = **{lc_pay_fee:,.2f}**
- Phí khác: **{lc_other:,.2f}**
⇒ **Tổng phí bank: {lc_total_bank:,.2f}**

**B) Chi phí vốn**
- Do giữ vốn {days_lc} ngày:
- {val:,.0f} × {interest_rate}% × ({days_lc}/360) = **{lc_interest:,.2f}**
"""
                )

            diff_lc = lc_final - tt_final
            diff_col = col_final - tt_final

            st.markdown("---")
            st.success(
                f"""
#### 💡 GÓC NHÌN QUẢN TRỊ (MANAGEMENT INSIGHT)

Chênh lệch chi phí chính là **“phí mua sự an toàn”** cho lô hàng **{val:,.0f} USD**:

**Nếu chọn Nhờ thu (Collection):**
- Trả thêm **{diff_col:,.2f} USD** so với T/T.
- Ngân hàng kiểm soát chứng từ nhưng **không cam kết trả tiền thay** người mua.

**Nếu chọn L/C:**
- Trả thêm **{diff_lc:,.2f} USD** so với T/T.
- Đổi lại, bạn mua **cam kết thanh toán của ngân hàng** ⇒ giảm rủi ro đối tác.

👉 Nếu rủi ro mất trắng là đáng kể, thì **{diff_lc:,.2f} USD** có thể là “phí bảo hiểm” hợp lý.
"""
            )

        footer()

    # -------------------------
    # TAB CHECKING
    # -------------------------
    with tab_check:
        st.subheader("📝 Kiểm tra Chứng từ (Checking) – UCP 600")
        st.caption("Giả lập bộ chứng từ và phát hiện lỗi bất hợp lệ (discrepancy).")

        # init session
        flags = ["s_late_ship", "s_late_pres", "s_over_amt", "s_dirty_bl"]
        for f in flags:
            if f not in st.session_state:
                st.session_state[f] = False

        if "chk_ship" not in st.session_state:
            st.session_state["chk_ship"] = pd.to_datetime("2025-01-15")
        if "chk_exp" not in st.session_state:
            st.session_state["chk_exp"] = pd.to_datetime("2025-02-28")
        if "chk_pres" not in st.session_state:
            st.session_state["chk_pres"] = pd.to_datetime("2025-01-20")
        if "chk_inv" not in st.session_state:
            st.session_state["chk_inv"] = 100_000.0
        if "chk_dirty" not in st.session_state:
            st.session_state["chk_dirty"] = False

        def update_inputs():
            ship = pd.to_datetime("2025-01-15")
            exp = pd.to_datetime("2025-02-28")
            pres = pd.to_datetime("2025-01-20")
            amt = 100_000.0
            is_dirty = False

            if st.session_state["s_late_ship"]:
                ship = pd.to_datetime("2025-03-01")

            if st.session_state["s_late_pres"]:
                pres = ship + pd.Timedelta(days=24)
            else:
                pres = ship + pd.Timedelta(days=5)

            if st.session_state["s_over_amt"]:
                amt = 110_000.0

            if st.session_state["s_dirty_bl"]:
                is_dirty = True

            st.session_state["chk_ship"] = ship
            st.session_state["chk_exp"] = exp
            st.session_state["chk_pres"] = pres
            st.session_state["chk_inv"] = amt
            st.session_state["chk_dirty"] = is_dirty

        def reset_scenarios():
            for f in flags:
                st.session_state[f] = False
            update_inputs()

        def toggle_scenario(key):
            st.session_state[key] = not st.session_state[key]
            update_inputs()

        with st.expander("🎯 GỢI Ý KỊCH BẢN (Cho phép chọn nhiều lỗi cùng lúc)", expanded=True):
            st.write("Bấm để **Bật/Tắt** tình huống lỗi. (Nút đỏ = đang chọn)")

            # st.markdown('<div class="scenario-toggle">', unsafe_allow_html=True)

            sc1, sc2, sc3, sc4, sc5 = st.columns(5)

            with sc1:
                btn_type = "primary" if st.session_state["s_late_ship"] else "secondary"
                if st.button("🚢 Giao trễ", key="btn_late", type=btn_type, use_container_width=True):
                    toggle_scenario("s_late_ship")
                    st.rerun()

            with sc2:
                btn_type = "primary" if st.session_state["s_late_pres"] else "secondary"
                if st.button("🕒 Trình muộn", key="btn_pres", type=btn_type, use_container_width=True):
                    toggle_scenario("s_late_pres")
                    st.rerun()

            with sc3:
                btn_type = "primary" if st.session_state["s_over_amt"] else "secondary"
                if st.button("💸 Vượt tiền", key="btn_amt", type=btn_type, use_container_width=True):
                    toggle_scenario("s_over_amt")
                    st.rerun()

            with sc4:
                btn_type = "primary" if st.session_state["s_dirty_bl"] else "secondary"
                if st.button("📝 B/L bẩn", key="btn_dirty", type=btn_type, use_container_width=True):
                    toggle_scenario("s_dirty_bl")
                    st.rerun()

            with sc5:
                if st.button("🔄 Reset", key="btn_reset", type="secondary", use_container_width=True):
                    reset_scenarios()
                    st.rerun()

            # st.markdown("</div>", unsafe_allow_html=True)  # ✅ ĐÓNG DIV ĐÚNG: nằm trong expander


        st.markdown("---")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### 📅 Yếu tố Thời gian")
            lc_issue_date = st.date_input("Ngày phát hành L/C:", value=pd.to_datetime("2025-01-01"), key="r3_lc_issue")
            ship_date = st.date_input("Ngày giao hàng (On Board Date):", key="chk_ship")
            lc_exp_date = st.date_input("Ngày hết hạn L/C (Expiry Date):", key="chk_exp")
            pres_date = st.date_input("Ngày xuất trình (Presentation Date):", key="chk_pres")

        with c2:
            st.markdown("#### 💰 Yếu tố Tài chính & Hàng hóa")
            lc_amount = st.number_input("Giá trị L/C (USD):", value=100_000.0, step=1_000.0, key="r3_lc_amt")
            tolerance = st.number_input("Dung sai cho phép (+/- %):", value=5.0, step=1.0, key="r3_tol")
            inv_amount = st.number_input("Giá trị Hóa đơn (Invoice):", step=1_000.0, key="chk_inv")

            st.markdown("#### 📝 Tình trạng Vận đơn (B/L)")
            is_dirty_bl = st.checkbox("Trên B/L có ghi chú xấu? (VD: 'Bao bì rách')", key="chk_dirty")

        st.markdown("---")

        if st.button("🔍 SOÁT XÉT CHỨNG TỪ (CHECKING)", type="secondary", use_container_width=True, key="btn_check_docs"):
            errors = []

            # Time checks
            if ship_date > lc_exp_date:
                errors.append(("Late Shipment", "Ngày giao hàng diễn ra SAU ngày hết hạn L/C.", "Điều 14c"))

            if pres_date > lc_exp_date:
                errors.append(("L/C Expired", "Ngày xuất trình diễn ra SAU ngày hết hạn L/C.", "Điều 6d"))

            presentation_period = (pres_date - ship_date).days
            if presentation_period > 21:
                errors.append(("Stale Documents", f"Xuất trình muộn {presentation_period} ngày (tối đa 21 ngày).", "Điều 14c"))

            if presentation_period < 0:
                errors.append(("Impossible Date", "Ngày xuất trình TRƯỚC ngày giao hàng (phi logic).", "Logic"))

            # Amount checks
            max_allowed = lc_amount * (1 + tolerance / 100)
            if inv_amount > max_allowed:
                errors.append(("Overdrawn Credit", f"Hóa đơn ({inv_amount:,.0f}) vượt dung sai ({max_allowed:,.0f}).", "Điều 30b"))

            # B/L checks
            if is_dirty_bl:
                errors.append(("Unclean B/L", "Vận đơn không hoàn hảo (Dirty/Claused B/L) – có thể bị từ chối.", "Điều 27"))

            if not errors:
                st.success("✅ CLEAN DOCUMENTS (BỘ CHỨNG TỪ HỢP LỆ)")
                st.balloons()
                st.info("💡 Kết luận: Ngân hàng phát hành **bắt buộc thanh toán** (Honour).")
            else:
                st.error(f"❌ DISCREPANT DOCUMENTS (PHÁT HIỆN {len(errors)} LỖI)")
                for idx, (err_name, err_desc, ucp_art) in enumerate(errors, 1):
                    st.markdown(
                        f"""
<div style="background-color:#ffeded;color:#333;padding:12px;border-radius:10px;margin-bottom:10px;border-left:6px solid #ff4b4b;">
  <strong>{idx}. Lỗi: {err_name}</strong><br>
  Giải thích: <em>{err_desc}</em><br>
  ⚖️ Căn cứ: <strong>UCP 600 - {ucp_art}</strong>
</div>
                        """,
                        unsafe_allow_html=True,
                    )
                st.warning("👉 Hậu quả: Ngân hàng có quyền **từ chối thanh toán** và thu phí discrepancy (thường 50–100 USD/lỗi).")

        st.markdown("---")
        if st.button("AI Advisor – Trade Checking", type="primary", icon="🤖", key="btn_ai_ucp"):
            curr_errs = []
            if ship_date > lc_exp_date:
                curr_errs.append("Late Shipment")
            if pres_date > lc_exp_date:
                curr_errs.append("L/C Expired")
            if (pres_date - ship_date).days > 21:
                curr_errs.append("Stale Documents")
            if inv_amount > (lc_amount * (1 + tolerance / 100)):
                curr_errs.append("Overdrawn Credit")
            if is_dirty_bl:
                curr_errs.append("Unclean B/L")

            user_id = st.session_state.get('CURRENT_USER') 

            if not user_id:
                st.error("🔒 Bạn chưa đăng nhập đúng MSSV ở thanh bên trái!")
                st.toast("Vui lòng nhập MSSV để tiếp tục!", icon="🔒")
                st.stop() # Dừng lại ngay, không chạy tiếp

                # BƯỚC 2: KIỂM TRA HẠN MỨC (QUOTA)
            tracker = get_usage_tracker()
            current_used = tracker.get(user_id, 0)
                
            if current_used >= MAX_AI_QUOTA:
                st.warning(f"⚠️ Sinh viên {user_id} đã hết lượt dùng AI ({MAX_AI_QUOTA}/{MAX_AI_QUOTA}).")
                st.stop()

            context = f"""
Dữ liệu:
- Ship: {ship_date}
- Exp: {lc_exp_date}
- Pres: {pres_date}
- L/C Amount: {lc_amount:,.0f}
- Tolerance: {tolerance}%
- Invoice: {inv_amount:,.0f}
- Dirty B/L: {is_dirty_bl}

Lỗi phát hiện: {", ".join(curr_errs) if curr_errs else "Không có"}
"""
            task = "Giải thích ngắn gọn các lỗi (nếu có) và 1–2 cách khắc phục thực tế cho doanh nghiệp."
            with st.spinner(f"AI đang tư vấn ... (Lượt gọi AI thứ {current_used + 1}/{MAX_AI_QUOTA})"):
                try:
                    advise = ask_gemini_advisor("Chuyên gia UCP 600", context, task)
                    if advise.startswith("⚠️"):
                        st.error(advise) # Hiện lỗi cho GV/SV biết
                        st.info("Lượt này chưa bị trừ do lỗi hệ thống.")
                    else:
                        # 1. Trừ quota trong Database/File
                        consume_quota(user_id)
                        
                        # 2. CẬP NHẬT SIDEBAR NGAY LẬP TỨC (Không cần Rerun)
                        # Lấy số mới để hiển thị
                        new_usage = current_used + 1
                        
                        # Bắn nội dung mới vào cái hộp "quota_placeholder" đang nằm bên Sidebar
                        # Lưu ý: Bạn cần đảm bảo biến 'quota_placeholder' truy cập được từ đây
                        quota_placeholder.info(f"Đã dùng: {new_usage}/{MAX_AI_QUOTA} lượt")
                        
                        # 3. Hiện kết quả AI ra màn hình chính
                        st.markdown(f'<div class="ai-box"><h4>🤖 LUẬT SƯ AI TƯ VẤN UCP 600</h4>{advise}</div>', unsafe_allow_html=True)
                        
                except Exception as e:
                    st.error(f"⚠️ Lỗi khi gọi AI: {str(e)}")

        footer()


# ==============================================================================
# PHÒNG 4: INVESTMENT
# ==============================================================================
def room_4_invest():
    # Import numpy_financial (optional)
    try:
        import numpy_financial as npf
    except ImportError:
        st.error("⚠️ Thiếu 'numpy_financial'. Cài bằng: `pip install numpy-financial` để tính IRR chuẩn.")
        npf = None

    st.markdown('<p class="header-style">🏭 Phòng Đầu tư Quốc tế (Investment Dept)</p>', unsafe_allow_html=True)
    st.markdown(
        """
<div class="role-card">
  <div class="role-title">👤 Vai diễn: Chuyên viên Phân tích Đầu tư (Investment Analyst)</div>
  <div class="mission-text">"Nhiệm vụ: Thẩm định dự án FDI, tính IRR/NPV và đánh giá rủi ro tỷ giá."</div>
</div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("📝 THÔNG SỐ DỰ ÁN ĐẦU TƯ", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 1) Dòng tiền Dự án (USD)")
            inv = st.number_input("Vốn đầu tư ban đầu (CapEx):", value=1_000_000.0, step=10_000.0, format="%.0f", key="r4_inv")
            cf_yearly = st.number_input("Dòng tiền ròng hằng năm (Operating CF):", value=300_000.0, step=5_000.0, format="%.0f", key="r4_cf")
            salvage_val = st.number_input("Giá trị thanh lý cuối kỳ (Terminal Value):", value=200_000.0, key="r4_salvage")
            years = st.slider("Vòng đời dự án (năm):", 3, 10, 5, key="r4_years")
        with c2:
            st.markdown("##### 2) Thị trường & Vĩ mô")
            fx_spot = st.number_input("Tỷ giá Spot hiện tại (VND/USD):", value=25_000.0, step=10.0, key="r4_fx")
            depre = st.number_input("Mức độ mất giá VND (%/năm):", value=3.0, step=0.1, key="r4_depre")
            wacc = st.number_input("Chi phí vốn (WACC %):", value=12.0, step=0.5, key="r4_wacc")

    st.markdown("---")

    if "run_dcf" not in st.session_state:
        st.session_state.run_dcf = False

    if st.button("📊 CHẠY MÔ HÌNH DCF & PHÂN TÍCH ĐỘ NHẠY", key="btn_run_dcf", use_container_width=True):
        st.session_state.run_dcf = True

    if st.session_state.run_dcf:
        data_cf = []
        cf_stream_vnd_nominal = []
        cumulative_pv = 0.0
        payback_period = None

        # Year 0
        cf0_vnd = -inv * fx_spot
        cumulative_pv += cf0_vnd
        cf_stream_vnd_nominal.append(cf0_vnd)

        data_cf.append(
            {
                "Năm": 0,
                "Tỷ giá (VND/USD)": fx_spot,
                "CF (USD)": -inv,
                "CF Quy đổi (VND)": cf0_vnd,
                "PV (Hiện giá VND)": cf0_vnd,
                "Lũy kế PV": cumulative_pv,
            }
        )

        for i in range(1, years + 1):
            fx_future = fx_spot * ((1 + depre / 100) ** i)
            cf_usd = cf_yearly + (salvage_val if i == years else 0)
            cf_vnd = cf_usd * fx_future
            cf_stream_vnd_nominal.append(cf_vnd)

            pv_vnd = cf_vnd / ((1 + wacc / 100) ** i)

            prev_cumulative = cumulative_pv
            cumulative_pv += pv_vnd

            if payback_period is None and cumulative_pv >= 0:
                # fraction of year to recover
                fraction = abs(prev_cumulative) / pv_vnd if pv_vnd != 0 else 0
                payback_period = (i - 1) + fraction

            data_cf.append(
                {
                    "Năm": i,
                    "Tỷ giá (VND/USD)": fx_future,
                    "CF (USD)": cf_usd,
                    "CF Quy đổi (VND)": cf_vnd,
                    "PV (Hiện giá VND)": pv_vnd,
                    "Lũy kế PV": cumulative_pv,
                }
            )

        npv = cumulative_pv

        # IRR
        irr_value = 0.0
        if npf is not None:
            try:
                irr_value = float(npf.irr(cf_stream_vnd_nominal)) * 100
                if np.isnan(irr_value) or np.isinf(irr_value):
                    irr_value = 0.0
            except Exception:
                irr_value = 0.0

        st.subheader("1. Kết quả Thẩm định")
        m1, m2, m3 = st.columns(3)
        m1.metric("NPV (Giá trị hiện tại ròng)", f"{npv:,.0f} VND", delta="Đáng đầu tư" if npv > 0 else "Lỗ vốn")
        if payback_period is not None:
            m2.metric("Thời gian hoàn vốn (DPP)", f"{payback_period:.2f} năm")
        else:
            m2.metric("Thời gian hoàn vốn (DPP)", "Chưa hoàn vốn", delta_color="inverse")
        m3.metric("IRR (Hoàn vốn nội bộ)", f"{irr_value:.2f}%", delta=f"WACC: {wacc}%", delta_color="normal")

        is_feasible = (npv > 0) and (irr_value > wacc)
        if is_feasible:
            st.success(f"✅ KẾT LUẬN: NÊN ĐẦU TƯ. NPV dương ({npv:,.0f} VND) và IRR ({irr_value:.2f}%) > WACC.")
        else:
            reason = []
            if npv <= 0:
                reason.append("NPV âm")
            if irr_value <= wacc:
                reason.append(f"IRR ({irr_value:.2f}%) ≤ WACC")
            st.error(f"⛔ KẾT LUẬN: KHÔNG NÊN ĐẦU TƯ. Lý do: {', '.join(reason)}.")

        df_chart = pd.DataFrame(data_cf)
        st.bar_chart(df_chart.set_index("Năm")[["PV (Hiện giá VND)"]], color="#4B4BFF")

        with st.expander("🔎 Xem bảng dòng tiền chi tiết (Cashflow Table)"):
            # 1. Tạo DataFrame từ list data_cf
            df_display = pd.DataFrame(data_cf)
            
            # 2. QUAN TRỌNG: Thiết lập cột "Năm" làm Index (Trục cố định)
            # Việc này giúp loại bỏ cột số thứ tự 0,1,2 thừa thãi
            # Và giúp cột "Năm" luôn đứng yên bên trái khi bạn kéo thanh cuộn ngang
            df_display.set_index("Năm", inplace=True)
            
            # 3. Hiển thị bảng
            st.dataframe(
                df_display.style.format("{:,.0f}"), # Format số phân cách hàng nghìn
                use_container_width=True,           # Tràn viền màn hình                
            )

        with st.expander("🎓 GÓC HỌC TẬP: GIẢI MÃ CÔNG THỨC & SỐ LIỆU", expanded=False):
            st.markdown("#### 1) NPV điều chỉnh theo tỷ giá")
            st.markdown("Dòng tiền USD được **quy đổi sang VND theo tỷ giá kỳ vọng** từng năm trước khi chiết khấu.")
            st.latex(
                r"NPV = -I_0 \times S_0 + \sum_{t=1}^{n} \frac{(CF_{t,USD} + TV_n)\times S_t}{(1+\text{WACC})^t}"
            )
            st.markdown(
                f"""
                Trong đó:
                - $I_0$ = Vốn đầu tư ban đầu ({inv:,.0f} USD).
                - $CF_{{t,USD}}$ = Dòng tiền hoạt động ({cf_yearly:,.0f} USD).
                - $TV_n$ = Giá trị thanh lý tài sản chỉ ở năm cuối ({salvage_val:,.0f} USD)
                - $S_t$ = Tỷ giá dự báo năm t, tính bằng $S_0(1+{depre}\\%)^t$
                - WACC = Chi phí vốn bình quân ({wacc}\\%)
                """
            )

            st.divider()

            st.markdown("#### 2) Thời gian hoàn vốn chiết khấu (DPP)")
            st.latex(r"DPP = Y_{negative} + \frac{|PV_{Cumulative}|}{PV_{NextYear}}")
            if payback_period:
                y_neg_idx = int(payback_period)
                try:
                    val_missing = abs(data_cf[y_neg_idx]["Lũy kế PV"])
                    val_next = data_cf[y_neg_idx + 1]["PV (Hiện giá VND)"]
                    
                    st.markdown("👇 **Áp dụng số liệu dự án:**")
                    st.latex(f"DPP = {y_neg_idx} + \\frac{{|{val_missing:,.0f}|}}{{{val_next:,.0f}}} = \\mathbf{{{payback_period:.2f} \\text{{ Năm}}}}")
                    
                    st.info(f"""
                    💡 **Diễn giải:** * Sau **{y_neg_idx} năm**, dự án vẫn còn lỗ lũy kế **{val_missing:,.0f} VND**. 
                    * Sang năm thứ **{y_neg_idx + 1}**, dự án kiếm được **{val_next:,.0f} VND**, đủ để bù phần lỗ đó.
                    """)
                except Exception:
                    st.warning("Đã hoàn vốn nhưng không hiển thị được chi tiết phép tính.")
            else:
                st.info("Dự án chưa hoàn vốn nên không thể áp dụng công thức chi tiết.")

            st.divider()

            st.markdown("#### 3) Suất sinh lời nội bộ (IRR)")
            st.markdown("IRR là mức lãi suất làm cho **NPV = 0**.")
            st.latex(r"\sum_{t=0}^{n}\frac{CF_{t,VND}}{(1+IRR)^t}=0")
            st.markdown(f"Trong bài này: IRR = **{irr_value:.2f}%** so với WACC = **{wacc}%**.")

        st.subheader("2. Phân tích Độ nhạy (Sensitivity Analysis)")
        st.markdown("Kiểm tra NPV khi **WACC** và **mức mất giá VND** thay đổi. Trong thực tế, Tỷ giá và WACC là hai biến số khó dự đoán nhất. Ma trận bên dưới (Sensitivity Matrix) giúp trả lời câu hỏi: Nếu Tỷ giá biến động xấu hơn dự kiến (ví dụ mất giá 5% thay vì 3%), dự án có còn lãi không?")


        wacc_range = [wacc - 2, wacc - 1, wacc, wacc + 1, wacc + 2]
        depre_range = [depre - 2, depre - 1, depre, depre + 1, depre + 2]

        sensitivity_data = []
        for w in wacc_range:
            row = []
            for d in depre_range:
                sim_npv = -inv * fx_spot
                for t in range(1, years + 1):
                    sim_fx = fx_spot * ((1 + d / 100) ** t)
                    sim_cf_usd = cf_yearly + (salvage_val if t == years else 0)
                    sim_npv += (sim_cf_usd * sim_fx) / ((1 + w / 100) ** t)
                row.append(sim_npv)
            sensitivity_data.append(row)

        df_sens = pd.DataFrame(
            sensitivity_data,
            index=[f"WACC {w:.1f}%" for w in wacc_range],
            columns=[f"Mất giá {d:.1f}%" for d in depre_range],
        )

        def color_negative_red(val):
            color = "#ffcccc" if val < 0 else "#ccffcc"
            return f"background-color: {color}; color: black"

        st.dataframe(df_sens.style.applymap(color_negative_red).format("{:,.0f}"))

        st.markdown("---")
        if st.button("AI Advisor – FDI Analysis", type="primary", icon="🤖", key="btn_ai_invest"):
            user_id = st.session_state.get('CURRENT_USER') 

            if not user_id:
                st.error("🔒 Bạn chưa đăng nhập đúng MSSV ở thanh bên trái!")
                st.toast("Vui lòng nhập MSSV để tiếp tục!", icon="🔒")
                st.stop() # Dừng lại ngay, không chạy tiếp

                # BƯỚC 2: KIỂM TRA HẠN MỨC (QUOTA)
            tracker = get_usage_tracker()
            current_used = tracker.get(user_id, 0)
                
            if current_used >= MAX_AI_QUOTA:
                st.warning(f"⚠️ Sinh viên {user_id} đã hết lượt dùng AI ({MAX_AI_QUOTA}/{MAX_AI_QUOTA}).")
                st.stop()
            context = f"""
Dự án FDI:
- Vốn: {inv:,.0f} USD; CF/năm: {cf_yearly:,.0f} USD; Thanh lý: {salvage_val:,.0f} USD
- Số năm: {years}
- FX Spot: {fx_spot:,.0f}; Mất giá VND: {depre}%
- WACC: {wacc}%
- NPV: {npv:,.0f} VND; IRR: {irr_value:.2f}%; DPP: {payback_period}
"""
            task = """
1) Nhận xét tính khả thi (NPV, IRR so với WACC).
2) Nêu 2 rủi ro tỷ giá/khả năng chuyển lợi nhuận về nước.
3) Khuyến nghị: Duyệt hay Từ chối (1 câu chốt).
"""
            with st.spinner(f"Chuyên viên đang phân tích...(Lượt gọi AI thứ {current_used + 1}/{MAX_AI_QUOTA})"):
                try:
                    advise = ask_gemini_advisor("Investment Specialist", context, task)
                    # advise = ask_gemini_advisor("CFO Advisor", context, task)
                    if advise.startswith("⚠️"):
                        st.error(advise) # Hiện lỗi cho GV/SV biết
                        st.info("Lượt này chưa bị trừ do lỗi hệ thống.")
                    else:
                        # 1. Trừ quota trong Database/File
                        consume_quota(user_id)
                        
                        # 2. CẬP NHẬT SIDEBAR NGAY LẬP TỨC (Không cần Rerun)
                        # Lấy số mới để hiển thị
                        new_usage = current_used + 1
                        
                        # Bắn nội dung mới vào cái hộp "quota_placeholder" đang nằm bên Sidebar
                        # Lưu ý: Bạn cần đảm bảo biến 'quota_placeholder' truy cập được từ đây
                        quota_placeholder.info(f"Đã dùng: {new_usage}/{MAX_AI_QUOTA} lượt")
                        
                        # 3. Hiện kết quả AI ra màn hình chính
                        st.markdown(f'<div class="ai-box"><h4>🤖 CHUYÊN VIÊN AI NHẬN ĐỊNH</h4>{advise}</div>', unsafe_allow_html=True)
                        
                except Exception as e:
                    st.error(f"⚠️ Lỗi khi gọi AI: {str(e)}")        

    footer()


# ==============================================================================
# PHÒNG 5: MACRO STRATEGY
# ==============================================================================
def room_5_macro():
    st.markdown('<p class="header-style">📉 Ban Chiến lược Vĩ mô (Macro Strategy)</p>', unsafe_allow_html=True)
    st.markdown(
        """
<div class="role-card">
  <div class="role-title">👤 Vai diễn: Chuyên gia Chiến lược Vĩ mô (Macro Strategist)</div>
  <div class="mission-text">"Nhiệm vụ: Phân tích 'tác động kép' của tỷ giá: (1) Nợ công và (2) rủi ro dòng tiền nóng (Carry Trade Unwind)."</div>
</div>
        """,
        unsafe_allow_html=True,
    )

    tab_debt, tab_carry = st.tabs(["📉 Khủng hoảng Nợ công", "💸 Chiến lược Carry Trade"])

    # TAB 1
    with tab_debt:
        st.subheader("1. Mô phỏng Cú sốc Tỷ giá lên Nợ công")
        col_macro1, col_macro2 = st.columns(2)
        with col_macro1:
            debt_val = st.number_input("Tổng nợ nước ngoài (Tỷ USD):", value=50.0, step=1.0, key="r5_debt_val")
            base_rate = st.number_input("Tỷ giá hiện tại (VND/USD):", value=25_000.0, step=100.0, key="r5_base_rate")
        with col_macro2:
            st.markdown("#### Kịch bản Tỷ giá")
            shock_pct = st.slider(
                "Đồng nội tệ mất giá bao nhiêu %?",
                min_value=0.0,
                max_value=100.0,
                value=20.0,
                step=1.0,
                key="r5_shock",
            )

        new_rate = base_rate * (1 + shock_pct / 100)
        base_debt_vnd = debt_val * base_rate
        new_debt_vnd = debt_val * new_rate
        loss_vnd = new_debt_vnd - base_debt_vnd

        st.markdown("---")
        m1, m2, m3 = st.columns(3)
        m1.metric("Tỷ giá sau cú sốc", f"{new_rate:,.0f} VND", f"-{shock_pct}% (Mất giá)", delta_color="inverse")
        m2.metric("Nợ quy đổi ban đầu", f"{base_debt_vnd:,.0f} Tỷ VND")
        m3.metric("Gánh nặng TĂNG THÊM", f"{loss_vnd:,.0f} Tỷ VND", delta="RỦI RO VỠ NỢ", delta_color="inverse")

        # Cảnh báo động
        if shock_pct > 30:
            st.error(f"🚨 **BÁO ĐỘNG ĐỎ:** Mức mất giá {shock_pct}% tương đương kịch bản Khủng hoảng Châu Á 1997. Nguy cơ vỡ nợ quốc gia (Sovereign Default) là rất cao.")
        elif shock_pct > 10:
            st.warning(f"⚠️ **Cảnh báo:** Gánh nặng nợ tăng thêm {loss_vnd/1000:,.1f} nghìn tỷ VND sẽ gây áp lực cực lớn lên ngân sách.")


        with st.expander("🧮 GÓC HỌC TẬP: GIẢI MÃ SỐ LIỆU NỢ CÔNG", expanded=False):
            st.markdown("#### 1) Vì sao nợ tăng dù không vay thêm?")
            st.write("Nợ USD không đổi, nhưng **VND cần để mua USD trả nợ tăng** khi tỷ giá tăng.")

            st.markdown("#### 2) Công thức & thay số")
            st.markdown(
                f"""
- Nợ ban đầu: $$ {debt_val} \\times {base_rate:,.0f} = \\mathbf{{{base_debt_vnd:,.0f}}} $$
- Nợ sau cú sốc: $$ {debt_val} \\times {new_rate:,.0f} = \\mathbf{{{new_debt_vnd:,.0f}}} $$
- Tăng thêm: $$ {new_debt_vnd:,.0f} - {base_debt_vnd:,.0f} = \\mathbf{{{loss_vnd:,.0f}}} $$
"""
            )

        # --- PHẦN MINH HỌA LỊCH SỬ ---
        with st.expander("📚 BÀI HỌC LỊCH SỬ: KHỦNG HOẢNG TÀI CHÍNH 1997"):
            c_hist1, c_hist2 = st.columns([1, 2])
            with c_hist1:
                st.write("### 📉")
                st.caption("**Đồng Baht Thái sụp đổ**")
                # Kích hoạt tìm kiếm hình ảnh biểu đồ khủng hoảng
                st.markdown("")
            
            with c_hist2:
                st.write("""
                **Nguyên nhân sụp đổ:**
                Vào năm 1997, Thái Lan vay nợ nước ngoài rất lớn (giống ví dụ trên). Khi đồng Baht mất giá 50%, gánh nặng nợ quy đổi tăng gấp đôi, khiến các công ty không thể trả nợ và phá sản hàng loạt.
                """)

        macro_context = f"""
        Quốc gia nợ {debt_val} tỷ USD. Tỷ giá mất giá {shock_pct}%.
        Gánh nặng nợ tăng thêm {loss_vnd:,.0f} tỷ VND.
        So sánh với kịch bản khủng hoảng 1997.
        """

    # TAB 2
    with tab_carry:
        st.subheader("2. Đầu cơ Chênh lệch lãi suất (Carry Trade)")
        st.caption("Vay đồng tiền lãi thấp ➜ mua đồng tiền lãi cao. Lợi nhuận = lãi suất chênh + biến động tỷ giá.")

        c1, c2 = st.columns(2)
        with c1:
            capital = st.number_input("Vốn đầu tư (Triệu USD):", value=10.0, step=1.0, key="r5_capital")
            rate_borrow = st.number_input("Lãi vay (Funding Rate %):", value=0.5, step=0.1, key="r5_borrow")
        with c2:
            rate_invest = st.number_input("Lãi đầu tư (Target Rate %):", value=5.5, step=0.1, key="r5_invest")
            fx_move = st.slider("Biến động tỷ giá (%):", -10.0, 10.0, -2.0, 0.5, key="r5_fx_move")

        st.markdown("---")
        interest_diff = rate_invest - rate_borrow
        profit_interest = capital * (interest_diff / 100)
        profit_fx = capital * (fx_move / 100)
        total_pnl = profit_interest + profit_fx
        roi = (total_pnl / capital) * 100 if capital != 0 else 0

        c_res1, c_res2, c_res3 = st.columns(3)
        c_res1.metric("1) Lãi từ lãi suất (Spread)", f"${profit_interest:,.2f} M", f"Chênh lệch: {interest_diff:.1f}%")
        c_res2.metric("2) Lãi/Lỗ từ tỷ giá (FX)", f"${profit_fx:,.2f} M", f"Biến động: {fx_move}%")
        c_res3.metric("3) TỔNG LỢI NHUẬN", f"${total_pnl:,.2f} M", f"ROI: {roi:.1f}%")

        with st.expander("🧮 GÓC HỌC TẬP: GIẢI MÃ CÁCH TÍNH CARRY TRADE", expanded=False):
            st.markdown("Tổng lợi nhuận đến từ 2 nguồn:")

            st.markdown("#### A) Lợi nhuận từ lãi suất")
            st.latex(r"\text{Profit}_{Rate} = \text{Vốn} \times (r_{Invest} - r_{Borrow})")
            st.markdown(f"Áp dụng: {capital} × ({rate_invest}% - {rate_borrow}%) = **{profit_interest:,.2f} triệu USD**")

            st.divider()

            st.markdown("#### B) Lợi nhuận từ tỷ giá")
            st.latex(r"\text{Profit}_{FX} = \text{Vốn} \times \% \Delta FX")
            st.markdown(f"Áp dụng: {capital} × {fx_move}% = **{profit_fx:,.2f} triệu USD**")

            st.info(
                """
Carry Trade giống như “nhặt tiền lẻ (lãi suất) trước đầu xe lu (tỷ giá)”.
Bạn có thể lời đều từ chênh lãi suất, nhưng một cú đảo chiều tỷ giá có thể xóa sạch thành quả.
"""
            )

    st.markdown("---")
    if st.button("AI Advisor – Macro Strategist", type="primary", icon="🤖", key="btn_ai_macro"):
        user_id = st.session_state.get('CURRENT_USER') 

        if not user_id:
            st.error("🔒 Bạn chưa đăng nhập đúng MSSV ở thanh bên trái!")
            st.toast("Vui lòng nhập MSSV để tiếp tục!", icon="🔒")
            st.stop() # Dừng lại ngay, không chạy tiếp

                # BƯỚC 2: KIỂM TRA HẠN MỨC (QUOTA)
        tracker = get_usage_tracker()
        current_used = tracker.get(user_id, 0)
                
        if current_used >= MAX_AI_QUOTA:
            st.warning(f"⚠️ Sinh viên {user_id} đã hết lượt dùng AI ({MAX_AI_QUOTA}/{MAX_AI_QUOTA}).")
            st.stop() 

        full_context = f"""
TÌNH HUỐNG MÔ PHỎNG:
1) Nợ công: nợ {debt_val} tỷ USD, mất giá {shock_pct}%, nợ tăng thêm {loss_vnd:,.0f} tỷ VND.
2) Carry Trade: vốn {capital} triệu USD, chênh lãi {interest_diff:.2f}%, FX {fx_move}% ⇒ ROI {roi:.1f}%.
"""
        task = f"""
Làm báo cáo nhanh:
1) Giải thích rủi ro “unwind carry trade” và vì sao FX đảo chiều có thể gây chao đảo thị trường.
2) Đánh giá rủi ro nợ công trong kịch bản mất giá {shock_pct}% (nêu 1-2 dấu hiệu cảnh báo).
3) Lời khuyên hành động: thiên về Risk-On hay Risk-Off? (1 câu chốt).
"""
        with st.spinner(f"Đang tổng hợp tín hiệu vĩ mô... (Lượt gọi AI thứ {current_used + 1}/{MAX_AI_QUOTA})"):
            try:
                advise = ask_gemini_advisor("Macro Strategist", full_context, task)
                if advise.startswith("⚠️"):
                    st.error(advise) # Hiện lỗi cho GV/SV biết
                    st.info("Lượt này chưa bị trừ do lỗi hệ thống.")
                else:
                        # 1. Trừ quota trong Database/File
                        consume_quota(user_id)
                        
                        # 2. CẬP NHẬT SIDEBAR NGAY LẬP TỨC (Không cần Rerun)
                        # Lấy số mới để hiển thị
                        new_usage = current_used + 1
                        
                        # Bắn nội dung mới vào cái hộp "quota_placeholder" đang nằm bên Sidebar
                        # Lưu ý: Bạn cần đảm bảo biến 'quota_placeholder' truy cập được từ đây
                        quota_placeholder.info(f"Đã dùng: {new_usage}/{MAX_AI_QUOTA} lượt")
                        
                        # 3. Hiện kết quả AI ra màn hình chính
                        st.markdown(f'<div class="ai-box"><h4>🤖 CHUYÊN GIA AI BÁO CÁO CHIẾN LƯỢC</h4>{advise}</div>', unsafe_allow_html=True)
                    
            except Exception as e:
                st.error(f"⚠️ Lỗi khi gọi AI: {str(e)}")
            
    footer()


# ==============================================================================
# ROUTER
# ==============================================================================
if "1." in room:
    room_1_dealing()
elif "2." in room:
    room_2_risk()
elif "3." in room:
    room_3_trade()
elif "4." in room:
    room_4_invest()
elif "5." in room:
    room_5_macro()
