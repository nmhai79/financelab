import streamlit as st
import pandas as pd
import numpy as np
import google.generativeai as genai
import os

# --- CẤU HÌNH TRANG ---
st.set_page_config(
    page_title="Finance Lab", 
    layout="wide", 
    initial_sidebar_state="expanded",
    page_icon="🏦"
)

def init_style():
    st.markdown("""
        <style>
        /* 1. Tùy chỉnh Nút bấm thường (Secondary) -> Chuyển thành màu Xanh lá */
        /* Selector này nhắm vào các nút không phải là Primary */
        div.stButton > button:first-child {
            background-color: #28a745 !important; /* Màu xanh lá tiền tệ */
            color: white !important;
            border: none;
            border-radius: 8px; /* Bo tròn góc */
            font-weight: bold;
            padding: 0.5rem 1rem;
            transition: all 0.3s ease; /* Hiệu ứng mượt mà */
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }

        /* Hiệu ứng khi di chuột vào (Hover) */
        div.stButton > button:first-child:hover {
            background-color: #218838 !important; /* Xanh đậm hơn */
            transform: scale(1.02); /* Phóng to nhẹ tạo cảm giác bấm */
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        }

        /* 2. Giữ nguyên hoặc tùy chỉnh Nút AI (Primary) -> Màu đỏ/Cam đặc trưng */
        /* Streamlit dùng class riêng cho Primary, ta đảm bảo nó nổi bật */
        button[kind="primary"] {
            background-color: #FF4B4B !important;
            border: none;
            box-shadow: 0 2px 4px rgba(255, 75, 75, 0.4);
        }
        button[kind="primary"]:hover {
            background-color: #FF2B2B !important;
            box-shadow: 0 4px 8px rgba(255, 75, 75, 0.6);
        }
        </style>
    """, unsafe_allow_html=True)

# --- GỌI HÀM NÀY NGAY ĐẦU CHƯƠNG TRÌNH ---
init_style()

# --- CẤU HÌNH API GEMINI (TỰ ĐỘNG LẤY TỪ SECRETS) ---
api_key = None
try:
    # Ưu tiên lấy từ Secrets (trên Cloud)
    api_key = st.secrets["GEMINI_API_KEY"]
except (FileNotFoundError, KeyError):
    # Fallback cho trường hợp chạy local mà chưa setup secrets
    api_key = os.getenv("GEMINI_API_KEY")

# Chỉ cấu hình nếu tìm thấy Key
if api_key:
    genai.configure(api_key=api_key)

# --- HÀM GỌI AI CHUNG CHO CÁC PHÒNG (Dùng gemini-2.0-flash) ---
def ask_gemini_advisor(role, context_data, task):
    """Hàm AI Advisor dùng chung cho các phòng nghiệp vụ"""
    try:
        # CHÍNH XÁC MODEL BẠN YÊU CẦU
        model = genai.GenerativeModel('gemini-2.0-flash') 
        
        prompt = f"""
        Đóng vai: {role}.
        
        Dữ liệu đầu vào:
        {context_data}
        
        Yêu cầu:
        {task}
        
        Văn phong: Ngắn gọn, súc tích (khoảng 3-4 câu), đi thẳng vào rủi ro và khuyến nghị chuyên môn.
        """
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg:
            return "⚠️ AI đang bận (Quá tải). Vui lòng thử lại sau."
        elif "404" in error_msg:
            return "⚠️ Lỗi Model: Tài khoản chưa hỗ trợ gemini-2.0-flash."
        else:
            return f"⚠️ Lỗi kết nối: {error_msg}"

# Hàm gọi AI cũ của bạn (Giữ nguyên cho Room 5)
def ask_gemini_macro(debt_increase, shock_percent, new_rate):
    """Hàm gọi AI để phân tích vĩ mô"""
    try:
        model = genai.GenerativeModel('gemini-2.0-flash') 
        
        prompt = f"""
        Đóng vai một Cố vấn Kinh tế cấp cao của Chính phủ (Economic Advisor).
        
        Tình huống hiện tại:
        - Đồng nội tệ vừa mất giá: {shock_percent}%
        - Tỷ giá mới: {new_rate:,.0f} VND/USD
        - Hậu quả tài khóa: Gánh nặng nợ công quốc gia vừa tăng thêm {debt_increase:,.0f} Tỷ VND do chênh lệch tỷ giá.
        
        Yêu cầu:
        Hãy viết một báo cáo ngắn gọn (khoảng 3 gạch đầu dòng lớn) cảnh báo Chính phủ về 3 tác động thực tế đến đời sống người dân và doanh nghiệp (Ví dụ: Lạm phát nhập khẩu, Giá xăng dầu, Áp lực thuế).
        Văn phong: Trang trọng, cảnh báo rủi ro, chuyên nghiệp. Không dùng Markdown đậm nhạt quá nhiều.
        """
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"⚠️ Lỗi kết nối AI: {str(e)}"

# --- CSS GIAO DIỆN (THEME XANH DƯƠNG CHUYÊN NGHIỆP) ---
st.markdown("""
<style>
    /* Card Vai diễn */
    .role-card {
        background-color: #e3f2fd;
        border-left: 6px solid #1565c0;
        padding: 20px;
        border-radius: 8px;
        margin-bottom: 25px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .role-title { 
        color: #1565c0; 
        font-weight: bold; 
        font-size: 20px; 
        margin-bottom: 8px;
        display: flex;
        align-items: center;
    }
    .mission-text { color: #424242; font-style: italic; font-size: 16px; line-height: 1.5; }
    
    /* Header phòng ban */
    .header-style { 
        font-size: 28px; font-weight: bold; color: #0d47a1; 
        border-bottom: 2px solid #eee; padding-bottom: 15px; margin-bottom: 25px;
    }
    
    /* Box kết quả & Giải thích */
    .result-box { background-color: #f1f8e9; padding: 15px; border-radius: 5px; border: 1px solid #c5e1a5; color: #33691e; font-weight: bold;}
    
    /* FIX LỖI HIỂN THỊ: Thêm color: #333 để chữ luôn đen */
    .step-box { 
        background-color: #fafafa; 
        color: #333333; 
        padding: 15px; 
        border-radius: 5px; 
        border: 1px dashed #bdbdbd; 
        margin-bottom: 10px; 
    }
    
    .explanation-box { background-color: #fff8e1; padding: 15px; border-radius: 5px; border-left: 4px solid #ffb300; margin-top: 10px; }
    
    /* SỬA LỖI 2: CSS AI Box - Ép màu chữ đen (#333) */
    .ai-box {
        background-color: #fff3e0;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #ff9800;
        margin-top: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        color: #333333 !important; /* Quan trọng: Ép màu chữ đen */
    }
    .ai-box h4 {
        color: #e65100 !important;
        font-weight: bold;
        margin-bottom: 10px;
    }
    .ai-box p, .ai-box li {
        color: #333333 !important; /* Đảm bảo nội dung con cũng màu đen */
    }

    /* --- NÚT AI ĐỒNG BỘ (NỀN ĐỎ CHỮ TRẮNG - FIX ICON MÀU) --- */
    div[data-testid="stButton"] > button[kind="primary"] {
        background-color: #ff2b2b !important;
        color: white !important;
        border: none;
        box-shadow: 0 2px 5px rgba(0,0,0,0.2);
        transition: all 0.3s ease;
        
        /* QUAN TRỌNG: Ép dùng Font Emoji màu sắc thay vì font đen trắng của Linux/Browser mặc định */
        font-family: "Segoe UI Emoji", "Noto Color Emoji", "Apple Color Emoji", "Android Emoji", sans-serif !important;
    }
    
    div[data-testid="stButton"] > button[kind="primary"]:hover {
        background-color: #d32f2f !important;
        box-shadow: 0 4px 8px rgba(0,0,0,0.3);
    }
    
    /* Copyright Footer */
    .copyright {
        font-size: 12px;
        color: #888;
        text-align: center;
        margin-top: 50px;
    }
</style>
""", unsafe_allow_html=True)

st.title("🏦 INTERNATIONAL FINANCE LAB")
st.caption("Hệ thống Mô phỏng Nghiệp vụ Tài chính Quốc tế với Trợ lý AI Gemini")

# --- MENU NAVIGATION (SIDEBAR CHUẨN) ---
with st.sidebar:
    st.header("🏢 MÔ PHỎNG NGHIỆP VỤ")
    st.write("Di chuyển đến:")
    
    room = st.radio(
        "Phòng nghiệp vụ:",
        [
            "1. Sàn Kinh doanh Ngoại hối (Dealing Room)",
            "2. Phòng Quản trị Rủi ro (Risk Management)",
            "3. Phòng Thanh toán Quốc tế (Trade Finance)",
            "4. Phòng Đầu tư Quốc tế (Investment Dept)",
            "5. Ban Chiến lược Vĩ mô (Macro Strategy)"
        ],
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    st.info("💡 **Gợi ý:** Sau khi tính toán, hãy xem **'Giải thích'** hoặc gọi **'Chuyên gia AI'** để được tư vấn chuyên sâu.")
    
    # --- BẢN QUYỀN (Copyright) ---
    st.markdown("---")
    st.caption("© 2026 - Nguyễn Minh Hải",text_alignment="center")

# ==============================================================================
# PHÒNG 1: DEALING ROOM
# ==============================================================================
if "1." in room:
    st.markdown('<p class="header-style">💱 Sàn Kinh doanh Ngoại hối (Dealing Room)</p>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="role-card">
        <div class="role-title">👤 Vai diễn: Chuyên viên Kinh doanh Tiền tệ (FX Trader)</div>
        <div class="mission-text">"Nhiệm vụ: Niêm yết tỷ giá chéo (Cross-rate) và thực hiện kinh doanh chênh lệch giá (Arbitrage) khi phát hiện thị trường mất cân bằng."</div>
    </div>
    """, unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["🔢 Niêm yết Tỷ giá Chéo", "⚡ Săn Arbitrage (Tam giác)"])
    
    with tab1:
        st.subheader("🏦 Bảng điện tử Tỷ giá liên ngân hàng")
        st.caption("Nhập tỷ giá thị trường quốc tế và nội địa để tính tỷ giá chéo (EUR/VND).")
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 🇺🇸 Thị trường 1: USD/VND")
            usd_bid = st.number_input("BID (NH Mua USD):", value=25350.0, step=10.0, format="%.0f")
            usd_ask = st.number_input("ASK (NH Bán USD):", value=25450.0, step=10.0, format="%.0f")
        with c2:
            st.markdown("##### 🇪🇺 Thị trường 2: EUR/USD")
            eur_bid = st.number_input("BID (NH Mua EUR):", value=1.0820, step=0.0001, format="%.4f")
            eur_ask = st.number_input("ASK (NH Bán EUR):", value=1.0850, step=0.0001, format="%.4f")
            
        st.markdown("---")
        
        if st.button("🚀 TÍNH TOÁN & NIÊM YẾT", key="btn_cross_rate"):
            # Tính toán
            cross_bid = eur_bid * usd_bid
            cross_ask = eur_ask * usd_ask
            spread = cross_ask - cross_bid
            
            # Hiển thị kết quả chính
            st.success(f"✅ TỶ GIÁ NIÊM YẾT (EUR/VND): {cross_bid:,.0f} - {cross_ask:,.0f}")
            st.info(f"📊 Spread (Chênh lệch Mua-Bán): {spread:,.0f} VND/EUR")
            
            # --- PHẦN GIẢI THÍCH CHI TIẾT (UPDATED) ---
            with st.expander("🎓 GÓC HỌC TẬP: GIẢI MÃ CÔNG THỨC & SỐ LIỆU", expanded=True):
                st.markdown("")
                
                # 1. Lý thuyết
                st.markdown("#### 1. Công thức Toán học")
                st.latex(r"\text{EUR/VND}_{Bid} = \text{EUR/USD}_{Bid} \times \text{USD/VND}_{Bid}")
                st.latex(r"\text{EUR/VND}_{Ask} = \text{EUR/USD}_{Ask} \times \text{USD/VND}_{Ask}")
                
                st.divider()
                
                # 2. Áp dụng số liệu thực tế (Phần mới thêm)
                st.markdown("#### 2. Áp dụng số liệu bạn vừa nhập")
                st.write("Hệ thống đã thực hiện phép tính cụ thể như sau:")
                
                st.markdown(f"""
                **a) Tính Tỷ giá Mua (BID):**
                $$
                {eur_bid:.4f} \\text{{ (EUR/USD Bid)}} \\times {usd_bid:,.0f} \\text{{ (USD/VND Bid)}} = \\mathbf{{{cross_bid:,.0f} \\text{{ VND}}}}
                $$
                
                **b) Tính Tỷ giá Bán (ASK):**
                $$
                {eur_ask:.4f} \\text{{ (EUR/USD Ask)}} \\times {usd_ask:,.0f} \\text{{ (USD/VND Ask)}} = \\mathbf{{{cross_ask:,.0f} \\text{{ VND}}}}
                $$
                
                **c) Tính Spread (Lợi nhuận gộp/Rủi ro):**
                $$
                {cross_ask:,.0f} \\text{{ (Ask)}} - {cross_bid:,.0f} \\text{{ (Bid)}} = \\mathbf{{{spread:,.0f} \\text{{ VND}}}}
                $$
                """)
                
                st.divider()

                # 3. Giải thích nghiệp vụ
                st.markdown("#### 3. Tại sao lại nhân `Bid x Bid`?")
                st.info("""
                Để Ngân hàng Việt Nam mua EUR từ khách hàng (trả VND), họ phải đi "đường vòng" qua USD:
                1.  **Bước 1:** Ngân hàng bán EUR lấy USD trên thị trường quốc tế (Dùng giá Mua EUR của đối tác = **EUR/USD Bid**).
                2.  **Bước 2:** Ngân hàng bán số USD đó lấy VND tại Việt Nam (Dùng giá Mua USD của thị trường = **USD/VND Bid**).
                
                👉 **Kết luận:** Tỷ giá chéo Bid luôn là tích của các tỷ giá Bid thành phần.
                """)

    with tab2:
        st.header("⚡ Săn Arbitrage (Kinh doanh chênh lệch giá)")
        
        # 1. Nhập vốn (Cải tiến: Không fix cứng 1 triệu $)
        capital = st.number_input("Vốn kinh doanh (USD):", value=1000000.0, step=10000.0, format="%.0f")
        
        st.markdown("---")
        
        # 2. Nhập tỷ giá các ngân hàng
        k1, k2, k3 = st.columns(3)
        with k1: bank_a = st.number_input("Bank A (USD/VND):", value=25000.0, help="Giá bán USD lấy VND")
        with k2: bank_b = st.number_input("Bank B (EUR/USD):", value=1.1000, help="Giá bán EUR lấy USD")
        with k3: bank_c = st.number_input("Bank C (EUR/VND):", value=28000.0, help="Giá bán EUR lấy VND")
        
        # Nút chạy mô hình
        if st.button("🚀 KÍCH HOẠT THUẬT TOÁN ARBITRAGE"):
            st.markdown("### 📝 Nhật ký giao dịch tối ưu:")
            
            # --- LOGIC TỰ ĐỘNG TÌM ĐƯỜNG CÓ LÃI ---
            
            # Cách 1: USD -> EUR -> VND -> USD (Vòng kim đồng hồ)
            # Công thức: (Vốn / B) * C / A
            res1_eur = capital / bank_b
            res1_vnd = res1_eur * bank_c
            res1_usd_final = res1_vnd / bank_a
            profit1 = res1_usd_final - capital
            
            # Cách 2: USD -> VND -> EUR -> USD (Vòng ngược kim đồng hồ)
            # Công thức: (Vốn * A) / C * B
            res2_vnd = capital * bank_a
            res2_eur = res2_vnd / bank_c
            res2_usd_final = res2_eur * bank_b
            profit2 = res2_usd_final - capital

            # --- HIỂN THỊ KẾT QUẢ TỐT NHẤT ---
            
            if profit1 > 0:
                # Hiển thị Cách 1
                st.success(f"✅ PHÁT HIỆN CƠ HỘI: Mua EUR (Bank B) -> Bán lấy VND (Bank C)")
                st.markdown(f"""
                <div class="step-box">
                1. <b>Dùng USD mua EUR (tại Bank B):</b><br>
                   {capital:,.0f} / {bank_b} = <b>{res1_eur:,.2f} EUR</b><br><br>
                2. <b>Bán EUR đổi lấy VND (tại Bank C):</b><br>
                   {res1_eur:,.2f} × {bank_c} = <b>{res1_vnd:,.0f} VND</b> (Giá EUR ở C đang cao)<br><br>
                3. <b>Đổi VND về lại USD (tại Bank A):</b><br>
                   {res1_vnd:,.0f} / {bank_a} = <b>{res1_usd_final:,.2f} USD</b>
                </div>
                """, unsafe_allow_html=True)
                st.markdown(f'<div class="result-box">🎉 LỢI NHUẬN: +{profit1:,.2f} USD</div>', unsafe_allow_html=True)

            elif profit2 > 0:
                # Hiển thị Cách 2
                st.success(f"✅ PHÁT HIỆN CƠ HỘI: Bán USD (Bank A) -> Mua EUR (Bank C)")
                st.markdown(f"""
                <div class="step-box">
                1. <b>Đổi USD sang VND (tại Bank A):</b><br>
                   {capital:,.0f} × {bank_a} = <b>{res2_vnd:,.0f} VND</b><br><br>
                2. <b>Dùng VND mua EUR (tại Bank C):</b><br>
                   {res2_vnd:,.0f} / {bank_c} = <b>{res2_eur:,.2f} EUR</b> (Giá EUR ở C đang rẻ)<br><br>
                3. <b>Bán EUR đổi về USD (tại Bank B):</b><br>
                   {res2_eur:,.2f} × {bank_b} = <b>{res2_usd_final:,.2f} USD</b>
                </div>
                """, unsafe_allow_html=True)
                st.markdown(f'<div class="result-box">🎉 LỢI NHUẬN: +{profit2:,.2f} USD</div>', unsafe_allow_html=True)
                
            else:
                st.warning("⚖️ Thị trường cân bằng (No Arbitrage). Cả 2 chiều giao dịch đều không sinh lời hoặc lỗ phí.")
                st.info("Gợi ý: Hãy thử chỉnh chênh lệch giá giữa Bank B (Quốc tế) và Bank C (Việt Nam) lớn hơn.")

            # Giải thích chung
            with st.expander("🎓 BẢN CHẤT: Tại sao có tiền lời?"):
                st.write("""
                **Nguyên lý:** Mua ở nơi giá thấp, bán ở nơi giá cao.
                Máy tính đã tự động so sánh hai con đường:
                1.  **Vòng 1:** Mua EUR quốc tế đem về VN bán.
                2.  **Vòng 2:** Mua EUR ở VN đem ra quốc tế bán.
                Nếu chênh lệch giá đủ lớn (lớn hơn phí giao dịch), lợi nhuận phi rủi ro sẽ xuất hiện.
                """)
                
        # --- BỔ SUNG AI CHO PHÒNG 1 ---
        st.markdown("---")
        # Dùng tham số icon="🤖" để render ổn định hơn
        if st.button("AI Trader: Đánh giá rủi ro", type="primary", icon="🤖"):
            if api_key:
                # Tính toán lại giá trị để gửi cho AI
                s1 = 1000000 / bank_b
                s2 = s1 * bank_c
                s3 = s2 / bank_a
                prof = s3 - 1000000
                
                context = f"Vốn: 1M USD. Tỷ giá A: {bank_a}, B: {bank_b}, C: {bank_c}. Lợi nhuận dự kiến: {prof:.2f} USD."
                task = "Đánh giá rủi ro thanh khoản, độ trượt giá (Slippage) khi thực hiện 3 lệnh liên tiếp. Có nên vào lệnh không?"
                
                with st.spinner("AI đang phân tích thị trường..."):
                    advise = ask_gemini_advisor("Senior FX Trader", context, task)
                    st.markdown(f'<div class="ai-box"><h4>🤖 LỜI KHUYÊN CỦA TRADER</h4>{advise}</div>', unsafe_allow_html=True)
            else:
                st.warning("⚠️ Vui lòng nhập API Key.")
        st.markdown("---")
        st.markdown(
            """
            <div style="text-align: center; color: #888; font-size: 13px; margin-top: 10px;">
                © 2026 Designed by Nguyễn Minh Hải
            </div>
            """, 
            unsafe_allow_html=True
        )
elif "2." in room:
    st.markdown('<p class="header-style">🛡️ Phòng Quản trị Rủi ro (Risk Management)</p>', unsafe_allow_html=True)
    
    # --- 1. THIẾT LẬP HỒ SƠ KHOẢN NỢ ---
    st.subheader("1. Hồ sơ Khoản nợ (Debt Profile)")
    c1, c2 = st.columns(2)
    with c1:
        debt_amount = st.number_input("Giá trị khoản phải trả (USD):", value=1000000.0, step=10000.0, format="%.0f")
    with c2:
        days_loan = st.number_input("Thời hạn thanh toán (Ngày):", value=90, step=30)

    # Role Card động theo input
    st.markdown(f"""
    <div class="role-card">
        <div class="role-title">👤 Vai diễn: Giám đốc Tài chính (CFO)</div>
        <div class="mission-text">"Nhiệm vụ: Tính toán tỷ giá kỳ hạn hợp lý và lựa chọn công cụ phòng vệ (Forward hay Option) tối ưu cho khoản nợ <b>{debt_amount:,.0f} USD</b> đáo hạn sau <b>{days_loan} ngày</b>."</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    # --- 2. TÍNH TOÁN TỶ GIÁ KỲ HẠN (IRP) ---
    st.subheader("2. Tính Tỷ giá Kỳ hạn (Fair Forward Rate)")
    st.caption("Công cụ định giá Forward dựa trên chênh lệch lãi suất VND và USD.")

    # 1. INPUT DATA
    c_input1, c_input2, c_input3, c_input4 = st.columns(4)
    with c_input1:
        spot_irp = st.number_input("Spot Rate (Hiện tại):", value=25000.0, step=10.0, format="%.0f")
    with c_input2:
        r_vnd = st.number_input("Lãi suất VND (%/năm):", value=6.0, step=0.1)
    with c_input3:
        r_usd = st.number_input("Lãi suất USD (%/năm):", value=3.0, step=0.1)
    with c_input4:
        days_loan = st.number_input("Kỳ hạn (Ngày):", value=90, step=30)
        
    # 2. TÍNH TOÁN LOGIC
    # Công thức: F = S * (1 + r_vnd * n/360) / (1 + r_usd * n/360)
    numerator = 1 + (r_vnd/100)*(days_loan/360)
    denominator = 1 + (r_usd/100)*(days_loan/360)
    fwd_cal = spot_irp * (numerator / denominator)
    swap_point = fwd_cal - spot_irp
    
    st.markdown("---")

    # 3. HIỂN THỊ KẾT QUẢ & GIẢI THÍCH (Tỷ lệ 1:1.5)
    col_res_irp1, col_res_irp2 = st.columns([1, 1.5])
    
    # --- CỘT TRÁI: KẾT QUẢ SỐ LIỆU ---
    with col_res_irp1:
        st.markdown("##### 🏁 KẾT QUẢ TÍNH TOÁN")
        st.metric("Tỷ giá Forward (F)", f"{fwd_cal:,.0f} VND", help="Tỷ giá kỳ hạn hợp lý theo IRP")
        
        # Hiển thị Swap Point
        st.metric("Điểm kỳ hạn (Swap Point)", f"{swap_point:,.0f} VND", 
                 delta="VND giảm giá (Forward > Spot)" if swap_point > 0 else "VND tăng giá (Forward < Spot)", 
                 delta_color="inverse")
        
        # Tóm tắt nhanh
        if r_vnd > r_usd:
            st.warning(f"📉 **Quy luật:** Lãi suất VND cao hơn USD ({r_vnd}% > {r_usd}%), nên VND bị thị trường 'trừ điểm' (giảm giá) trong tương lai.")
        else:
            st.success(f"📈 **Quy luật:** Lãi suất VND thấp hơn USD, nên VND được 'cộng điểm' (tăng giá).")
    
    # --- CỘT PHẢI: GÓC HỌC TẬP (GIẢI MÃ) ---
    with col_res_irp2:
        with st.expander("🎓 GÓC HỌC TẬP: GIẢI MÃ IRP & CÔNG THỨC", expanded=True):
            st.markdown("")
            
            # --- [MỚI] 1. GIẢI THÍCH THUẬT NGỮ ---
            st.markdown("#### 1. IRP là gì?")
            st.info("""
            **IRP** là viết tắt của **Interest Rate Parity** (Ngang giá Lãi suất).
            
            💡 **Ý nghĩa:** Đây là điều kiện cân bằng mà tại đó chênh lệch lãi suất giữa hai quốc gia bằng đúng chênh lệch giữa tỷ giá kỳ hạn và tỷ giá giao ngay. 
            Nói đơn giản: **"Chênh lệch lãi suất = Chênh lệch tỷ giá"**.
            """)

            # 2. CÔNG THỨC & THAY SỐ
            st.markdown("#### 2. Công thức tính toán")
            st.latex(r"F = S \times \frac{1 + r_{VND} \times \frac{n}{360}}{1 + r_{USD} \times \frac{n}{360}}")
            st.caption("Thay số cụ thể từ dữ liệu bạn nhập:")
            st.latex(f"F = {spot_irp:,.0f} \\times \\frac{{1 + {r_vnd}\\% \\times \\frac{{{days_loan}}}{{360}}}}{{1 + {r_usd}\\% \\times \\frac{{{days_loan}}}{{360}}}} = \\mathbf{{{fwd_cal:,.0f} \\text{{ VND}}}}")
            
            st.divider()
            
            # 3. ĐIỂM KỲ HẠN
            st.markdown("#### 3. Điểm kỳ hạn (Swap Point)")
            st.write("Là chênh lệch giá trị tuyệt đối giữa Forward và Spot:")
            st.latex(f"\\text{{Swap}} = {fwd_cal:,.0f} - {spot_irp:,.0f} = \\mathbf{{{swap_point:,.0f} \\text{{ VND}}}}")

            st.divider()

            # 4. BẢN CHẤT
            st.markdown("#### 4. Tại sao có quy luật này?")
            st.write("""
            Theo nguyên lý **"Không có bữa trưa miễn phí" (No Arbitrage)**:
            * Nếu bạn gửi VND lãi cao ({r_vnd}%) mà tỷ giá VND không giảm, thì ai cũng bán USD để gửi VND -> Lãi to.
            * Để ngăn điều này, thị trường buộc VND phải **mất giá** trong tương lai để triệt tiêu phần lãi suất chênh lệch đó.
            """)
    st.markdown("---")

    # --- 3. MA TRẬN RA QUYẾT ĐỊNH (DECISION MATRIX) ---
    st.subheader("3. So sánh Chiến lược Phòng vệ")
    
    # Hướng dẫn sinh viên cách nhập số liệu (MỤC YÊU CẦU CỦA BẠN)
    st.info("""
    💡 **HƯỚNG DẪN SINH VIÊN (TRY IT):**
    * Để **Option thắng Forward**: Hãy chỉnh `Giá thực hiện (Strike)` + `Phí` < `Giá Forward`. Đồng thời kéo `Dự báo Tỷ giá` lên cao.
    * Để **Forward thắng Option**: Hãy chỉnh `Giá Forward` thấp hơn tổng chi phí Option.
    * Để **Thả nổi thắng**: Kéo `Dự báo Tỷ giá` xuống thấp hơn cả giá Forward.
    """)

    col_strat1, col_strat2 = st.columns(2)
    
    with col_strat1:
        st.markdown("#### 🏦 Chốt Deal với Ngân hàng")
        # Forward lấy mặc định từ IRP nhưng cho phép sửa (thương lượng)
        f_rate_input = st.number_input("Giá Forward Bank chào:", value=float(f"{fwd_cal:.2f}"), help="Thường Bank sẽ chào giá này hoặc cao hơn chút ít.")
        
        st.markdown("**Thông số Quyền chọn (Option):**")
        strike = st.number_input("Strike Price (Giá thực hiện):", value=25100.0)
        premium = st.number_input("Phí Option (VND/USD):", value=100.0)
        
    with col_strat2:
        st.markdown("#### 🔮 Dự báo Thị trường")
        future_spot = st.slider(f"Dự báo Spot sau {days_loan} ngày:", 24000.0, 26000.0, 25400.0, step=10.0)
        
        # --- CẬP NHẬT THÔNG BÁO THÔNG MINH HƠN ---
        if future_spot > f_rate_input:
            st.warning(f"""
            🔥 **Cảnh báo:** Tỷ giá thị trường ({future_spot:,.0f}) cao hơn giá Forward ({f_rate_input:,.0f}).
            👉 **Nên Phòng vệ:** Cả Forward và Option đều đang giúp bạn "né" được mức giá cao này.
            """)
        else:
            st.success(f"""
            ❄️ **Thị trường hạ nhiệt:** Tỷ giá dự báo ({future_spot:,.0f}) thấp hơn giá Bank chào.
            👉 **Cân nhắc:** Thả nổi hoặc Option (bỏ quyền) sẽ có lợi hơn Forward cứng.
            """)

    # --- TÍNH TOÁN CORE LOGIC & TẠO CỘT CÔNG THỨC ---
    
    # 1. Thả nổi
    cost_open = debt_amount * future_spot
    formula_open = f"{debt_amount:,.0f} × {future_spot:,.0f}" # Diễn giải
    
    # 2. Forward
    cost_fwd = debt_amount * f_rate_input
    formula_fwd = f"{debt_amount:,.0f} × {f_rate_input:,.0f}" # Diễn giải
    
    # 3. Option (Logic liên kết thanh kéo Future Spot)
    if future_spot > strike:
        # Spot cao -> Dùng quyền (Strike)
        action_text = "Thực hiện quyền"
        price_base = strike
        explanation_opt = "✅ Đã được bảo hiểm (Dùng Strike)"
        # Công thức: Lượng tiền * (Strike + Phí)
        formula_opt = f"{debt_amount:,.0f} × ({strike:,.0f} + {premium:,.0f})"
    else:
        # Spot thấp -> Bỏ quyền -> Mua giá chợ (Future Spot)
        action_text = "Bỏ quyền (Lapse)"
        price_base = future_spot
        explanation_opt = "📉 Mua giá chợ (Rẻ hơn Strike)"
        # Công thức: Lượng tiền * (Spot + Phí)
        formula_opt = f"{debt_amount:,.0f} × ({future_spot:,.0f} + {premium:,.0f})"
        
    effective_opt_rate = price_base + premium
    cost_opt = debt_amount * effective_opt_rate

    # Tạo DataFrame kết quả CÓ CỘT CÁCH TÍNH
    df_compare = pd.DataFrame({
        "Chiến lược": ["1. Thả nổi (No Hedge)", "2. Kỳ hạn (Forward)", "3. Quyền chọn (Option)"],
        "Trạng thái": [
            "Chấp nhận rủi ro",
            "Khóa cứng tỷ giá",
            explanation_opt
        ],
        "Cách tính (Debt × Rate)": [ # <--- CỘT MỚI
            formula_open, 
            formula_fwd, 
            formula_opt
        ],
        "Tỷ giá thực tế": [future_spot, f_rate_input, effective_opt_rate],
        "Tổng chi phí (VND)": [cost_open, cost_fwd, cost_opt]
    })
    
    # Format bảng hiển thị
    st.table(df_compare.style.format({
        "Tỷ giá thực tế": "{:,.0f}",
        "Tổng chi phí (VND)": "{:,.0f}"
    }))

    # --- KẾT LUẬN TỰ ĐỘNG ---
    best_idx = df_compare['Tổng chi phí (VND)'].idxmin()
    best_strat = df_compare.loc[best_idx, "Chiến lược"]
    
    st.markdown(f"### 🏆 KẾT LUẬN: Chọn **{best_strat}**")
    
    if best_idx == 1: # Forward Thắng
        st.success(f"""
        **Tại sao chọn Forward?**
        * Giá Forward ({f_rate_input:,.0f}) đang rẻ hơn thị trường dự báo ({future_spot:,.0f}).
        * Nó cũng rẻ hơn Option (vốn phải gánh thêm phí premium thành {effective_opt_rate:,.0f}).
        * 👉 Phù hợp với doanh nghiệp thích "Ăn chắc mặc bền", cố định chi phí.
        """)
    elif best_idx == 2: # Option Thắng
        st.success(f"""
        **Tại sao chọn Option?**
        * Tổng chi phí Option ({effective_opt_rate:,.0f}) đang là thấp nhất.
        * Dù mất phí mua quyền ({premium}), nhưng bạn được mua với giá Strike ({strike:,.0f}) thấp hơn nhiều so với thị trường bùng nổ ({future_spot:,.0f}).
        * 👉 Option phát huy tác dụng khi thị trường biến động mạnh vượt quá dự kiến.
        """)
    else: # Thả nổi Thắng
        st.warning(f"""
        **Tại sao chọn Thả nổi?**
        * Bạn dự báo tỷ giá tương lai sẽ GIẢM sâu ({future_spot:,.0f}).
        * Việc chốt giá Forward hay mua Option lúc này là lãng phí.
        * 👉 *Lưu ý: Đây là chiến lược rủi ro nhất. Nếu dự báo sai, thiệt hại sẽ rất lớn.*
        """)

    # --- AI ADVISOR ---
    st.markdown("---")
    if st.button("AI CFO: Phân tích chuyên sâu", type="primary", icon="🤖"):
        if api_key:
            context = f"""
            Bài toán: Nợ {debt_amount:,.0f} USD. Spot hiện tại: {spot_irp}.
            Các phương án:
            1. Thả nổi (Giá dự kiến {future_spot:,.0f}) -> Tổng: {cost_open:,.0f}
            2. Forward (Giá {f_rate_input:,.0f}) -> Tổng: {cost_fwd:,.0f}
            3. Option (Strike {strike:,.0f} + Phí {premium}) -> Tổng: {cost_opt:,.0f}
            
            Kết quả máy tính chọn: {best_strat}.
            """
            task = "Đóng vai CFO. Hãy nhận xét kết quả này. Phân tích thêm về 'Chi phí cơ hội'. Nếu chọn Forward thì ta mất đi cơ hội gì nếu tỷ giá giảm? Nếu chọn Option thì ta trả phí để mua cái gì?"
            
            with st.spinner("Đang phân tích chiến lược..."):
                advise = ask_gemini_advisor("CFO Expert", context, task)
                st.markdown(f'<div class="ai-box"><h4>🤖 GÓC NHÌN CHUYÊN GIA</h4>{advise}</div>', unsafe_allow_html=True)
        
    st.markdown("---")
    st.markdown(
        """
        <div style="text-align: center; color: #888; font-size: 13px; margin-top: 10px;">
            © 2026 Designed by Nguyễn Minh Hải
        </div>
        """, 
        unsafe_allow_html=True
    )

# ==============================================================================
# PHÒNG 3: TRADE FINANCE
# ==============================================================================
elif "3." in room:
    st.markdown('<p class="header-style">🚢 Phòng Thanh toán Quốc tế (Trade Finance)</p>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="role-card">
        <div class="role-title">👤 Vai diễn: Chuyên viên Thanh toán Quốc tế</div>
        <div class="mission-text">"Nhiệm vụ: Tư vấn phương thức thanh toán tối ưu chi phí và kiểm tra bộ chứng từ (Checking) theo chuẩn UCP 600."</div>
    </div>
    """, unsafe_allow_html=True)
    
    tab_cost, tab_check = st.tabs(["💰 Bài toán Chi phí (T/T, Nhờ thu, L/C)", "📝 Kiểm tra Chứng từ (Checking)"])
    
    with tab_cost:
        st.header("💸 Bài toán Tối ưu Chi phí Thanh toán Quốc tế")
        st.caption("So sánh toàn diện: Phí Ngân hàng & Chi phí Vốn (Lãi vay) giữa T/T, Nhờ thu và L/C")

        # --- 1. THÔNG SỐ ĐẦU VÀO (INPUTS) ---
        with st.expander("📝 BƯỚC 1: NHẬP GIÁ TRỊ HỢP ĐỒNG & LÃI SUẤT", expanded=True):
            c1, c2 = st.columns(2)
            with c1:
                val = st.number_input("Giá trị hợp đồng (USD):", value=100000.0, step=1000.0)
                interest_rate = st.number_input("Lãi suất vay vốn (%/năm):", value=7.0, step=0.1, help="Dùng để tính chi phí cơ hội/lãi vay trong thời gian chờ thanh toán")
            with c2:
                # Thời gian đọng vốn
                days_tt = st.number_input("Số ngày đọng vốn T/T:", value=5, help="Thời gian tiền đi trên đường")
                days_col = st.number_input("Số ngày đọng vốn Nhờ thu:", value=15, help="Thời gian gửi chứng từ")
                days_lc = st.number_input("Số ngày đọng vốn L/C:", value=30, help="Thời gian xử lý bộ chứng từ phức tạp")

        st.markdown("---")
        
        # --- 2. CẤU HÌNH BIỂU PHÍ (BANK TARIFF) ---
        st.subheader("🏦 BƯỚC 2: CẤU HÌNH BIỂU PHÍ NGÂN HÀNG")
        
        col_tt, col_col, col_lc = st.columns(3)
        
        # Cột T/T
        with col_tt:
            st.markdown("#### 1. T/T (Chuyển tiền)")
            tt_pct = st.number_input("Phí chuyển tiền (%):", value=0.2, step=0.01, format="%.2f")
            tt_min = st.number_input("Min (USD) - T/T:", value=10.0)
            tt_max = st.number_input("Max (USD) - T/T:", value=200.0)
            tt_other = st.number_input("Điện phí (USD):", value=20.0)

        # Cột Collection
        with col_col:
            st.markdown("#### 2. Nhờ thu (D/P, D/A)")
            col_pct = st.number_input("Phí nhờ thu (%):", value=0.15, step=0.01, format="%.2f")
            col_min = st.number_input("Min (USD) - Col:", value=20.0)
            col_max = st.number_input("Max (USD) - Col:", value=250.0)
            col_other = st.number_input("Bưu điện phí (USD):", value=50.0)

        # Cột L/C
        with col_lc:
            st.markdown("#### 3. L/C (Tín dụng thư)")
            lc_open_pct = st.number_input("Phí mở L/C (%):", value=0.3, step=0.01, format="%.2f")
            lc_pay_pct = st.number_input("Phí thanh toán (%):", value=0.2, step=0.01, format="%.2f")
            lc_min = st.number_input("Min (USD) - L/C:", value=50.0)
            lc_other = st.number_input("Phí khác (USD):", value=100.0, help="Tu chỉnh, Bất hợp lệ...")

        st.markdown("---")

        # --- 3. TÍNH TOÁN & HIỂN THỊ ---
        if st.button("🚀 TÍNH TOÁN & SO SÁNH NGAY"):
            
            # Hàm tính phí có Min/Max
            def calculate_fee_min_max(amount, pct, fee_min, fee_max):
                raw_fee = amount * (pct / 100)
                final_fee = max(fee_min, min(raw_fee, fee_max))
                return final_fee, raw_fee

            # --- A. TÍNH T/T ---
            tt_bank_fee, tt_raw = calculate_fee_min_max(val, tt_pct, tt_min, tt_max)
            tt_total_bank = tt_bank_fee + tt_other
            tt_interest = val * (interest_rate / 100) * (days_tt / 360)
            tt_final = tt_total_bank + tt_interest

            # --- B. TÍNH COLLECTION ---
            col_bank_fee, col_raw = calculate_fee_min_max(val, col_pct, col_min, col_max)
            col_total_bank = col_bank_fee + col_other
            col_interest = val * (interest_rate / 100) * (days_col / 360)
            col_final = col_total_bank + col_interest

            # --- C. TÍNH L/C ---
            # L/C thường tính Min trên phí mở, phí thanh toán tính riêng
            lc_open_fee = max(lc_min, val * (lc_open_pct / 100)) 
            lc_pay_fee = val * (lc_pay_pct / 100)
            lc_total_bank = lc_open_fee + lc_pay_fee + lc_other
            lc_interest = val * (interest_rate / 100) * (days_lc / 360)
            lc_final = lc_total_bank + lc_interest

            # --- HIỂN THỊ KẾT QUẢ (METRICS) ---
            st.subheader("📊 Kết quả Tổng hợp")
            m1, m2, m3 = st.columns(3)
            
            # Logic Delta màu sắc
            best_price = min(tt_final, col_final, lc_final)
            
            m1.metric("1. Tổng phí T/T", f"${tt_final:,.2f}", 
                      delta="Rẻ nhất" if tt_final == best_price else None, delta_color="inverse")
            m2.metric("2. Tổng phí Nhờ thu", f"${col_final:,.2f}",
                      delta="Rẻ nhất" if col_final == best_price else None, delta_color="inverse")
            m3.metric("3. Tổng phí L/C", f"${lc_final:,.2f}", 
                      delta=f"Chênh lệch: +${lc_final - tt_final:,.2f} so với T/T", delta_color="off")

            # --- BIỂU ĐỒ ---
            chart_data = pd.DataFrame({
                "Phương thức": ["T/T", "Nhờ thu", "L/C"],
                "Phí Ngân hàng": [tt_total_bank, col_total_bank, lc_total_bank],
                "Chi phí Vốn (Lãi)": [tt_interest, col_interest, lc_interest]
            })
            st.bar_chart(chart_data.set_index("Phương thức"), stack=True, color=["#FF6C6C", "#4B4BFF"])

            # --- [QUAN TRỌNG] DIỄN GIẢI CÔNG THỨC (FIXED DISPLAY) ---
            st.markdown("### 🧮 Bảng chi tiết lời giải (Step-by-step)")
            st.info("Dưới đây là cách tính chi tiết giúp bạn hiểu rõ nguồn gốc các con số:")

            # Lưu ý: Dùng ký tự \$ để tránh lỗi xung đột với công thức toán LaTeX ($...$)
            
            # 1. T/T (CHUYỂN TIỀN)
            with st.expander("1️⃣ Chi tiết tính toán: T/T (Chuyển tiền)", expanded=False):
                st.latex(r"Cost_{T/T} = \text{Phí Bank} + \text{Lãi Vốn}")
                
                # Sử dụng dedent hoặc viết sát lề để tránh lỗi hiển thị code block
                st.markdown(f"""
**A. Phí dịch vụ Ngân hàng:**
* Tính sơ bộ: {val:,.0f} USD × {tt_pct}% = {tt_raw:,.2f} USD
* So sánh Min/Max ({tt_min} - {tt_max}) → Phí áp dụng: **{tt_bank_fee:,.2f} USD**
* Cộng Điện phí ({tt_other} USD) → Tổng phí Bank: **{tt_total_bank:,.2f} USD**

**B. Chi phí vốn (Lãi vay):**
* Công thức: $\\text{{Giá trị}} \\times \\text{{Lãi suất}} \\times \\frac{{\\text{{Ngày}}}}{{360}}$
* Thế số: {val:,.0f} × {interest_rate}% × ({days_tt}/360) = **{tt_interest:,.2f} USD**

👉 **TỔNG CHI PHÍ T/T:** {tt_total_bank:,.2f} + {tt_interest:,.2f} = **{tt_final:,.2f} USD**
                """)

            # 2. COLLECTION (NHỜ THU)
            with st.expander("2️⃣ Chi tiết tính toán: Nhờ thu (Collection)", expanded=False):
                st.latex(r"Cost_{Col} = \text{Phí Nhờ Thu} + \text{Phí Khác} + \text{Lãi Vốn}")
                
                st.markdown(f"""
**A. Phí dịch vụ Ngân hàng:**
* Tính sơ bộ: {val:,.0f} USD × {col_pct}% = {col_raw:,.2f} USD
* So sánh Min/Max ({col_min} - {col_max}) → Phí áp dụng: **{col_bank_fee:,.2f} USD**
* Cộng phí khác ({col_other} USD) → Tổng phí Bank: **{col_total_bank:,.2f} USD**

**B. Chi phí vốn:**
* Thế số: {val:,.0f} × {interest_rate}% × ({days_col}/360) = **{col_interest:,.2f} USD**

👉 **TỔNG CHI PHÍ COLLECTION:** {col_total_bank:,.2f} + {col_interest:,.2f} = **{col_final:,.2f} USD**
                """)

            # 3. L/C (TÍN DỤNG THƯ)
            with st.expander("3️⃣ Chi tiết tính toán: L/C (Tín dụng thư)", expanded=True):
                st.latex(r"Cost_{LC} = \text{Phí Mở} + \text{Phí T.Toán} + \text{Phí Khác} + \text{Lãi Vốn}")
                
                st.markdown(f"""
**A. Các loại phí Ngân hàng:**
* Phí Mở L/C: {val:,.0f} × {lc_open_pct}% = {lc_open_fee:,.2f} USD *(Tối thiểu {lc_min} USD)*
* Phí Thanh toán: {val:,.0f} × {lc_pay_pct}% = {lc_pay_fee:,.2f} USD
* Phí Khác: {lc_other:,.2f} USD

**B. Chi phí vốn (Gánh nặng lớn nhất):**
* Do L/C giữ vốn lâu hơn ({days_lc} ngày), tiền lãi phát sinh là:
* {val:,.0f} × {interest_rate}% × ({days_lc}/360) = **{lc_interest:,.2f} USD**

👉 **TỔNG CHI PHÍ L/C:** {lc_total_bank:,.2f} (Bank) + {lc_interest:,.2f} (Lãi) = **{lc_final:,.2f} USD**
                """)
                
            # --- KẾT LUẬN QUẢN TRỊ ---
            st.markdown("---")
            diff_val = lc_final - tt_final
            
            #  - có thể thêm diagram ở đây nếu cần minh họa quy trình
            
            if diff_val > 0:
                # Dùng st.container để bọc nội dung, giúp định dạng markdown ổn định hơn
                with st.container():
                    st.success(f"""
                    #### 💡 GÓC NHÌN QUẢN TRỊ
                    
                    Để có được sự an toàn tuyệt đối của phương thức L/C, doanh nghiệp phải trả thêm chi phí bảo hiểm rủi ro là:
                    
                    # {diff_val:,.2f} USD
                    *(Chênh lệch giữa L/C và T/T)*
                    
                    Hãy tự đặt câu hỏi: **"Việc loại bỏ rủi ro mất trắng lô hàng trị giá {val:,.0f} USD có xứng đáng với mức phí {diff_val:,.2f} USD này không?"**
                    
                    Nếu câu trả lời là **CÓ**, thì L/C là phương án tối ưu!
                    """)
            else:
                st.warning(f"""
                ⚠️ **TRƯỜNG HỢP ĐẶC BIỆT:**
                Hiện tại chi phí L/C đang **RẺ HƠN** hoặc **BẰNG** T/T.
                * Chênh lệch: {diff_val:,.2f} USD
                * Nguyên nhân: Có thể do số ngày chiếm dụng vốn (Days) của T/T đang được cấu hình quá cao.
                """)
        st.markdown("---")
        st.markdown(
            """
            <div style="text-align: center; color: #888; font-size: 13px; margin-top: 10px;">
                © 2026 Designed by Nguyễn Minh Hải
            </div>
            """, 
            unsafe_allow_html=True
        )

    with tab_check:
        st.subheader("1. Giả lập Bộ chứng từ & Soát xét lỗi")
        
        # --- [MỚI] KHUNG GỢI Ý KỊCH BẢN THỰC HÀNH ---
        with st.expander("🎯 GỢI Ý KỊCH BẢN: Bấm vào đây để tự động tạo lỗi", expanded=True):
            st.write("Chọn một tình huống bên dưới để máy tính tự điền số liệu, sau đó bấm **'Soát xét chứng từ'** để xem kết quả.")
            sc1, sc2, sc3, sc4 = st.columns(4)
            
            # Helper function để reset session state an toàn
            def set_scenario(ship, exp, pres, amount, dirty):
                st.session_state['chk_ship'] = pd.to_datetime(ship)
                st.session_state['chk_exp'] = pd.to_datetime(exp)
                st.session_state['chk_pres'] = pd.to_datetime(pres)
                st.session_state['chk_inv'] = float(amount)
                st.session_state['chk_dirty'] = dirty

            with sc1:
                if st.button("🚢 Lỗi Giao trễ", help="Mô phỏng: Hàng giao sau ngày hết hạn L/C"):
                    set_scenario("2025-03-01", "2025-02-28", "2025-03-05", 100000.0, False)
                    st.toast("Đã nạp kịch bản: Giao hàng sau ngày hết hạn L/C!")
            
            with sc2:
                if st.button("🕒 Lỗi Xuất trình muộn", help="Mô phỏng: Xuất trình quá 21 ngày sau khi giao hàng"):
                    set_scenario("2025-01-01", "2025-02-28", "2025-01-25", 100000.0, False) # 24 ngày
                    st.toast("Đã nạp kịch bản: Xuất trình quá 21 ngày!")
            
            with sc3:
                if st.button("💸 Lỗi Vượt tiền", help="Mô phỏng: Hóa đơn vượt quá giá trị L/C cho phép"):
                    set_scenario("2025-01-15", "2025-02-28", "2025-01-20", 110000.0, False) # Vượt 10%
                    st.toast("Đã nạp kịch bản: Số tiền vượt dung sai!")

            with sc4:
                if st.button("📝 Lỗi B/L bẩn", help="Mô phỏng: Vận đơn có ghi chú xấu"):
                    set_scenario("2025-01-15", "2025-02-28", "2025-01-20", 100000.0, True)
                    st.toast("Đã nạp kịch bản: Vận đơn không hoàn hảo!")
        
        st.markdown("---")

        # --- INPUTS (Đã gắn Key để liên kết với các nút bấm trên) ---
        c1, c2 = st.columns(2)
        
        with c1:
            st.markdown("#### 📅 Yếu tố Thời gian")
            # Thiết lập giá trị mặc định nếu chưa có trong session_state
            if 'chk_ship' not in st.session_state: st.session_state['chk_ship'] = pd.to_datetime("2025-01-15")
            if 'chk_exp' not in st.session_state: st.session_state['chk_exp'] = pd.to_datetime("2025-02-28")
            if 'chk_pres' not in st.session_state: st.session_state['chk_pres'] = pd.to_datetime("2025-01-20")

            lc_issue_date = st.date_input("Ngày phát hành L/C:", value=pd.to_datetime("2025-01-01"))
            # Sử dụng key để nút bấm phía trên có thể can thiệp vào giá trị
            ship_date = st.date_input("Ngày giao hàng (On Board Date):", key='chk_ship')
            lc_exp_date = st.date_input("Ngày hết hạn L/C (Expiry Date):", key='chk_exp')
            pres_date = st.date_input("Ngày xuất trình (Presentation Date):", key='chk_pres')
            
        with c2:
            st.markdown("#### 💰 Yếu tố Tài chính & Hàng hóa")
            if 'chk_inv' not in st.session_state: st.session_state['chk_inv'] = 104000.0
            if 'chk_dirty' not in st.session_state: st.session_state['chk_dirty'] = False

            lc_amount = st.number_input("Giá trị L/C (USD):", value=100000.0, step=1000.0)
            tolerance = st.number_input("Dung sai cho phép (+/- %):", value=5.0, step=1.0, help="Điều 30 UCP 600")
            inv_amount = st.number_input("Giá trị Hóa đơn Thương mại (Invoice):", step=1000.0, key='chk_inv')
            
            st.markdown("#### 📝 Tình trạng Vận đơn (B/L)")
            is_dirty_bl = st.checkbox("Trên B/L có ghi chú xấu? (VD: 'Bao bì rách')", key='chk_dirty')
            
        st.markdown("---")
        
        # --- NÚT CHECKING ---
        if st.button("🔍 SOÁT XÉT CHỨNG TỪ (CHECKING)"):
            errors = []
            
            # 1. Logic Kiểm tra Thời gian
            if ship_date > lc_exp_date:
                errors.append(("Late Shipment", "Ngày giao hàng diễn ra SAU ngày hết hạn L/C.", "Điều 14c"))
            
            if pres_date > lc_exp_date:
                errors.append(("L/C Expired", "Ngày xuất trình diễn ra SAU ngày hết hạn L/C.", "Điều 6d"))
                
            presentation_period = (pres_date - ship_date).days
            if presentation_period > 21:
                errors.append(("Stale Documents", f"Xuất trình muộn {presentation_period} ngày (UCP 600 quy định tối đa 21 ngày).", "Điều 14c"))
            
            if presentation_period < 0:
                 errors.append(("Impossible Date", "Ngày xuất trình diễn ra TRƯỚC ngày giao hàng (Phi logic).", "Logic"))

            # 2. Logic Kiểm tra Số tiền
            max_allowed = lc_amount * (1 + tolerance/100)
            if inv_amount > max_allowed:
                over_amt = inv_amount - max_allowed
                errors.append(("Overdrawn Credit", f"Số tiền hóa đơn ({inv_amount:,.0f}) vượt quá dung sai cho phép ({max_allowed:,.0f}).", "Điều 30b"))

            # 3. Logic Kiểm tra B/L
            if is_dirty_bl:
                errors.append(("Unclean B/L", "Vận đơn không hoàn hảo (Dirty/Claused B/L). Ngân hàng từ chối thanh toán.", "Điều 27"))

            # --- HIỂN THỊ KẾT QUẢ ---
            if not errors:
                st.success("✅ **CLEAN DOCUMENTS (BỘ CHỨNG TỪ HỢP LỆ)**")
                st.balloons()
                st.info("💡 **Kết luận:** Ngân hàng phát hành **bắt buộc phải thanh toán** (Honour).")
            else:
                st.error(f"❌ **DISCREPANT DOCUMENTS (PHÁT HIỆN {len(errors)} LỖI BẤT HỢP LỆ)**")
                
                for idx, (err_name, err_desc, ucp_art) in enumerate(errors, 1):
                    st.markdown(f"""
                    <div style="background-color: #ffeded; padding: 10px; border-radius: 5px; margin-bottom: 10px; border-left: 5px solid #ff4b4b;">
                        <strong>{idx}. Lỗi: {err_name}</strong><br>
                        Explain: <em>{err_desc}</em><br>
                        ⚖️ Căn cứ: <strong>UCP 600 - {ucp_art}</strong>
                    </div>
                    """, unsafe_allow_html=True)
                
                st.warning("👉 **Hậu quả:** Ngân hàng có quyền TỪ CHỐI THANH TOÁN và thu phí bất hợp lệ (Discrepancy Fee) từ 50-100 USD/lỗi.")
        
        # --- NÚT GỌI AI (ĐÃ NÂNG CẤP CONTEXT CHI TIẾT) ---
        st.markdown("---")
        if st.button("AI Luật sư: Tư vấn UCP 600", type="primary", icon="🤖"):
            if api_key:
                # 1. TÍNH LẠI LOGIC (Để đảm bảo có dữ liệu mới nhất ngay cả khi chưa bấm nút Soát xét)
                curr_errs = []
                
                # Check Thời gian
                if ship_date > lc_exp_date: 
                    curr_errs.append(f"Late Shipment (Giao {ship_date.strftime('%d/%m')} sau hạn {lc_exp_date.strftime('%d/%m')})")
                if pres_date > lc_exp_date: 
                    curr_errs.append("L/C Expired (L/C đã hết hạn)")
                
                days_late = (pres_date - ship_date).days
                if days_late > 21: 
                    curr_errs.append(f"Stale Documents (Xuất trình muộn {days_late} ngày > 21 ngày)")
                
                # Check Số tiền
                max_allow = lc_amount * (1 + tolerance/100)
                if inv_amount > max_allow: 
                    curr_errs.append(f"Overdrawn (Invoice {inv_amount:,.0f} > Max {max_allow:,.0f})")
                
                # Check B/L
                if is_dirty_bl: 
                    curr_errs.append("Unclean/Dirty B/L (Vận đơn có ghi chú xấu)")
                
                # 2. TẠO CONTEXT GỬI AI (Bổ sung thông tin chi tiết)
                context = f"""
                Tôi là nhân viên ngân hàng đang kiểm tra bộ chứng từ thanh toán L/C (UCP 600).
                
                DỮ LIỆU CỤ THỂ:
                - Ngày giao hàng: {ship_date}
                - Ngày hết hạn L/C: {lc_exp_date}
                - Ngày xuất trình: {pres_date}
                - Số tiền Invoice: {inv_amount:,.0f} USD (L/C: {lc_amount:,.0f} USD, Dung sai {tolerance}%)
                - Tình trạng B/L: {'Có ghi chú xấu (Dirty)' if is_dirty_bl else 'Sạch (Clean)'}
                
                DANH SÁCH LỖI MÁY TÍNH PHÁT HIỆN:
                {', '.join(curr_errs) if curr_errs else 'Không có lỗi (Clean Documents)'}
                """
                
                task = """
                Đóng vai Chuyên gia pháp lý UCP 600 (Legal Advisor).
                1. Hãy giải thích ngắn gọn tại sao các lỗi trên lại nghiêm trọng? (Dựa vào số ngày/số tiền cụ thể ở trên để giải thích).
                2. Nếu tôi là Ngân hàng Phát hành, tôi có quyền TỪ CHỐI THANH TOÁN (Dishonour) không?
                3. Đưa ra lời khuyên cho Doanh nghiệp xuất khẩu: Lần sau phải làm gì để tránh lỗi này?
                """
                
                with st.spinner("Luật sư đang tra cứu điều khoản UCP 600..."):
                    advise = ask_gemini_advisor("Legal Expert (UCP 600)", context, task)
                    st.markdown(f'<div class="ai-box"><h4>🤖 TƯ VẤN PHÁP LÝ & CÁCH KHẮC PHỤC</h4>{advise}</div>', unsafe_allow_html=True)
            else:
                st.warning("⚠️ Vui lòng nhập API Key.")

        st.markdown("---")
        st.markdown(
            """
            <div style="text-align: center; color: #888; font-size: 13px; margin-top: 10px;">
                © 2026 Designed by Nguyễn Minh Hải
            </div>
            """, 
            unsafe_allow_html=True
        )
# ==============================================================================
# PHÒNG 4: ĐẦU TƯ QUỐC TẾ
# ==============================================================================
elif "4." in room:
            st.markdown('<p class="header-style">🏭 Phòng Đầu tư Quốc tế (Investment Dept)</p>', unsafe_allow_html=True)
            
            st.markdown("""
            <div class="role-card">
                <div class="role-title">👤 Vai diễn: Chuyên viên Phân tích Đầu tư (Investment Analyst)</div>
                <div class="mission-text">"Nhiệm vụ: Thẩm định dự án FDI, Phân tích độ nhạy (Sensitivity Analysis) và Đánh giá rủi ro tỷ giá."</div>
            </div>
            """, unsafe_allow_html=True)
            
            # --- 1. INPUTS ---
            with st.expander("📝 THÔNG SỐ DỰ ÁN ĐẦU TƯ", expanded=True):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("##### 1. Dòng tiền Dự án (USD)")
                    inv = st.number_input("Vốn đầu tư ban đầu (CapEx):", value=1000000.0, step=10000.0, format="%.0f")
                    cf_yearly = st.number_input("Dòng tiền ròng hằng năm (Operating CF):", value=300000.0, step=5000.0, format="%.0f")
                    salvage_val = st.number_input("Giá trị thanh lý cuối kỳ (Terminal Value):", value=200000.0, help="Tiền bán thanh lý tài sản khi kết thúc dự án")
                    years = st.slider("Vòng đời dự án (năm):", 3, 10, 5)
                    
                with c2:
                    st.markdown("##### 2. Thị trường & Vĩ mô")
                    fx_spot = st.number_input("Tỷ giá Spot hiện tại (VND/USD):", value=25000.0, step=10.0)
                    depre = st.number_input("Mức độ mất giá VND (%/năm):", value=3.0, step=0.1, help="Dự báo VND mất giá bao nhiêu % so với USD mỗi năm")
                    wacc = st.number_input("Chi phí vốn (WACC %):", value=12.0, step=0.5, help="Tỷ suất sinh lời yêu cầu của nhà đầu tư")
                    
            st.markdown("---")

            # --- 2. TÍNH TOÁN & HIỂN THỊ ---
            if st.button("📊 CHẠY MÔ HÌNH DCF & PHÂN TÍCH ĐỘ NHẠY"):
                
                # A. TÍNH DÒNG TIỀN CƠ SỞ (BASE CASE)
                # -----------------------------------
                data_cf = []
                cumulative_pv = 0
                payback_period = None
                
                # Năm 0
                cf0_vnd = -inv * fx_spot
                cumulative_pv += cf0_vnd
                data_cf.append({
                    "Năm": 0, 
                    "Tỷ giá (VND/USD)": fx_spot, 
                    "CF (USD)": -inv, 
                    "CF Quy đổi (VND)": cf0_vnd, 
                    "PV (Hiện giá VND)": cf0_vnd, 
                    "Lũy kế PV": cumulative_pv
                })
                
                # Năm 1 -> n
                for i in range(1, years + 1):
                    # Tính tỷ giá tương lai: S_t = S_0 * (1 + delta)^t
                    fx_future = fx_spot * ((1 + depre/100) ** i)
                    
                    # Tính dòng tiền USD: Operating CF + Terminal Value (nếu là năm cuối)
                    cf_usd = cf_yearly + (salvage_val if i == years else 0)
                    
                    # Quy đổi VND: CF_VND = CF_USD * S_t
                    cf_vnd = cf_usd * fx_future
                    
                    # Chiết khấu: PV = CF_VND / (1 + WACC)^t
                    pv_vnd = cf_vnd / ((1 + wacc/100) ** i)
                    
                    # Lưu lại giá trị lũy kế cũ để tính Payback Period
                    prev_cumulative = cumulative_pv
                    cumulative_pv += pv_vnd
                    
                    # Check thời gian hoàn vốn (Lần đầu tiên Lũy kế chuyển từ Âm sang Dương)
                    if payback_period is None and cumulative_pv >= 0:
                        # Công thức nội suy: Năm trước + (Số tiền còn thiếu / Dòng tiền năm nay)
                        fraction = abs(prev_cumulative) / pv_vnd
                        payback_period = (i - 1) + fraction
                    
                    data_cf.append({
                        "Năm": i, 
                        "Tỷ giá (VND/USD)": fx_future, 
                        "CF (USD)": cf_usd, 
                        "CF Quy đổi (VND)": cf_vnd, 
                        "PV (Hiện giá VND)": pv_vnd, 
                        "Lũy kế PV": cumulative_pv
                    })
                    
                npv = cumulative_pv # NPV chính là Lũy kế năm cuối cùng
                
                # B. HIỂN THỊ KẾT QUẢ
                # -----------------------------------
                st.subheader("1. Kết quả Thẩm định")
                
                m1, m2, m3 = st.columns(3)
                m1.metric("NPV (Giá trị hiện tại ròng)", f"{npv:,.0f} VND", 
                         delta="Đáng đầu tư" if npv > 0 else "Không nên đầu tư")
                
                if payback_period:
                    m2.metric("Thời gian hoàn vốn (DPP)", f"{payback_period:.2f} Năm")
                else:
                    m2.metric("Thời gian hoàn vốn", "Chưa hoàn vốn", delta_color="inverse")
                    
                roi = (npv / abs(cf0_vnd)) * 100
                m3.metric("ROI (Tỷ suất sinh lời)", f"{roi:.2f}%", help="=(NPV / Vốn đầu tư ban đầu) * 100")

                # Biểu đồ kết hợp
                df_chart = pd.DataFrame(data_cf)
                st.bar_chart(df_chart.set_index("Năm")[["PV (Hiện giá VND)"]], color="#4B4BFF")
                
                with st.expander("🔎 Xem bảng dòng tiền chi tiết (Cashflow Table)"):
                    st.dataframe(pd.DataFrame(data_cf).style.format("{:,.0f}"))

                # --- [NEW] C. GIẢI THÍCH CÔNG THỨC (EDUCATIONAL PART) ---
                # --------------------------------------------------------
                with st.expander("🎓 GÓC HỌC TẬP: GIẢI MÃ CÔNG THỨC (READING MATERIAL)", expanded=True):
                    st.markdown("#### 1. Công thức tính NPV Điều chỉnh Tỷ giá")
                    st.markdown("Mô hình này khác NPV thông thường vì dòng tiền USD phải được quy đổi ra VND theo tỷ giá kỳ vọng từng năm trước khi chiết khấu.")
                    
                    # FIX: Dùng \text{WACC} để chữ hiển thị liền nhau đẹp hơn
                    st.latex(r"NPV = -I_0 \times S_0 + \sum_{t=1}^{n} \frac{(CF_{t, USD} + TV_n) \times S_t}{(1 + \text{WACC})^t}")
                    
                    st.markdown(f"""
                    **Trong đó:**
                    * $I_0$: Vốn đầu tư ban đầu ({inv:,.0f} USD).
                    * $CF_{{t, USD}}$: Dòng tiền hoạt động ({cf_yearly:,.0f} USD).
                    * $TV_n$: Giá trị thanh lý năm cuối ({salvage_val:,.0f} USD).
                    * $S_t$: Tỷ giá dự báo năm $t$, tính bằng: $S_0 \times (1 + {depre}\%)^t$.
                    * $\\text{{WACC}}$: Chi phí vốn ({wacc}%).
                    """)
                    
                    st.divider()
                    
                    # --- 2. CÔNG THỨC DPP (ĐÃ SỬA LỖI TRUY XUẤT DỮ LIỆU) ---
                    st.markdown("#### 2. Công thức Thời gian hoàn vốn (DPP)")
                    
                    # A. Hiển thị công thức tổng quát
                    st.latex(r"DPP = Y_{negative} + \frac{|PV_{Cumulative}|}{PV_{NextYear}}")
                    
                    # B. Giải thích các tham số (Legend)
                    st.markdown("""
                    **Trong đó:**
                    * $Y_{negative}$: Số năm mà dòng tiền lũy kế vẫn còn âm (Năm liền trước khi hoàn vốn).
                    * $|PV_{Cumulative}|$: Số vốn "còn thiếu" tại cuối năm $Y_{negative}$ (Lấy trị tuyệt đối).
                    * $PV_{NextYear}$: Dòng tiền (đã chiết khấu) thu được trong năm kế tiếp.
                    """)

                    # C. Ráp số liệu thực tế (Plug-in Values)
                    if payback_period:
                        y_neg_idx = int(payback_period) # Ví dụ: 4
                        
                        try:
                            # [FIX] Lấy dữ liệu từ mảng data_cf đã tính ở trên
                            # data_cf là list of dicts, index 0 là năm 0, index 1 là năm 1...
                            # Nên index trùng với số năm
                            
                            val_missing = abs(data_cf[y_neg_idx]["Lũy kế PV"]) # Số tiền còn thiếu (dương)
                            val_next = data_cf[y_neg_idx + 1]["PV (Hiện giá VND)"] # Tiền kiếm được năm sau
                            
                            st.markdown("👇 **Áp dụng số liệu dự án:**")
                            st.latex(f"DPP = {y_neg_idx} + \\frac{{|{val_missing:,.0f}|}}{{{val_next:,.0f}}} = \\mathbf{{{payback_period:.2f} \\text{{ Năm}}}}")
                            
                            st.info(f"""
                            💡 **Diễn giải:** Dự án mất **{y_neg_idx} năm** chẵn để gần hòa vốn. 
                            Tại cuối năm {y_neg_idx}, dự án vẫn còn thiếu **{val_missing:,.0f} VND**. 
                            Sang năm {y_neg_idx + 1}, dự án kiếm được **{val_next:,.0f} VND**, đủ bù đắp phần thiếu đó.
                            """)
                        except Exception as e:
                            # Fallback nếu index vượt quá giới hạn (ít gặp)
                            st.warning(f"Đã tính được DPP ({payback_period:.2f} năm), nhưng không thể hiển thị chi tiết phép chia.")
                    else:
                        st.info("Dự án chưa hoàn vốn nên không thể áp dụng công thức chi tiết.")

                    st.divider()

                    # --- 3. PHÂN TÍCH ĐỘ NHẠY (GIỮ NGUYÊN) ---
                    st.markdown("#### 3. Tại sao cần Phân tích Độ nhạy (Sensitivity)?")
                    st.write("""
                    Trong thực tế, Tỷ giá và WACC là hai biến số khó dự đoán nhất. 
                    Ma trận bên dưới (Sensitivity Matrix) giúp trả lời câu hỏi: 
                    *"Nếu Tỷ giá biến động xấu hơn dự kiến (ví dụ mất giá 5% thay vì 3%), dự án có còn lãi không?"*
                    """)

                # D. PHÂN TÍCH ĐỘ NHẠY (SENSITIVITY ANALYSIS)
                # ------------------------------------------------------
                st.subheader("2. Phân tích Độ nhạy (Sensitivity Analysis)")
                
                # Tạo ma trận biến thiên
                wacc_range = [wacc - 2, wacc - 1, wacc, wacc + 1, wacc + 2]
                depre_range = [depre - 2, depre - 1, depre, depre + 1, depre + 2]
                
                sensitivity_data = []
                for w in wacc_range:
                    row = []
                    for d in depre_range:
                        # Tính nhanh NPV loop
                        sim_npv = -inv * fx_spot
                        for t in range(1, years + 1):
                            sim_fx = fx_spot * ((1 + d/100) ** t)
                            sim_cf_usd = cf_yearly + (salvage_val if t == years else 0)
                            sim_npv += (sim_cf_usd * sim_fx) / ((1 + w/100) ** t)
                        row.append(sim_npv)
                    sensitivity_data.append(row)
                    
                df_sens = pd.DataFrame(
                    sensitivity_data, 
                    index=[f"WACC {w:.1f}%" for w in wacc_range],
                    columns=[f"Mất giá {d:.1f}%" for d in depre_range]
                )
                
                def color_negative_red(val):
                    color = '#ffcccc' if val < 0 else '#ccffcc'
                    return f'background-color: {color}; color: black'

                st.dataframe(df_sens.style.applymap(color_negative_red).format("{:,.0f}"))
                
                # E. AI ADVISOR (Context Updated)
                # -------------------------------
                st.markdown("---")
                if st.button("AI Chuyên viên: Đánh giá Dự án", type="primary", icon="🤖"):
                     if api_key:
                        context = f"""
                        Dự án FDI Thẩm định:
                        - Vốn: {inv:,.0f} USD. CF hằng năm: {cf_yearly:,.0f} USD. Thanh lý: {salvage_val:,.0f} USD.
                        - Số năm: {years}. WACC: {wacc}%. Mất giá VND: {depre}%.
                        
                        KẾT QUẢ CHẠY MÔ HÌNH:
                        - NPV: {npv:,.0f} VND.
                        - Hoàn vốn sau: {payback_period if payback_period else 'Không bao giờ'} năm.
                        - ROI: {roi:.1f}%.
                        """
                        
                        task = """
                        Đóng vai Giám đốc Tài chính (CFO). 
                        1. Nhận xét về tính khả thi của dự án (Dựa trên NPV và Thời gian hoàn vốn).
                        2. Phân tích rủi ro tỷ giá: Với dự án thu dòng tiền USD (doanh thu xuất khẩu/FDI), việc VND mất giá là lợi hay hại? Tại sao?
                        3. Đưa ra khuyến nghị cuối cùng: Duyệt (Approve) hay Từ chối (Reject)?
                        """
                        
                        with st.spinner("CFO đang phân tích..."):
                            advise = ask_gemini_advisor("CFO Advisor", context, task)
                            st.markdown(f'<div class="ai-box"><h4>🤖 CFO NHẬN ĐỊNH</h4>{advise}</div>', unsafe_allow_html=True)
                     else:
                        st.warning("⚠️ Vui lòng nhập API Key.")

            st.markdown("---")
            st.markdown(
                """
                <div style="text-align: center; color: #888; font-size: 13px; margin-top: 10px;">
                    © 2026 Designed by Nguyễn Minh Hải
                </div>
                """, 
                unsafe_allow_html=True
            )

# ==============================================================================
# PHÒNG 5: MACRO STRATEGY (CÓ TÍCH HỢP AI)
# ==============================================================================
elif "5." in room:
    st.markdown('<p class="header-style">📉 Ban Chiến lược Vĩ mô (Macro Strategy)</p>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="role-card">
        <div class="role-title">👤 Vai diễn: Chuyên gia Chiến lược Vĩ mô (Macro Strategist)</div>
        <div class="mission-text">"Nhiệm vụ: Phân tích 'Tác động kép' của tỷ giá: (1) Khủng hoảng Nợ công (Bài học 1997) và (2) Rủi ro dòng tiền nóng (Carry Trade Unwind)."</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Tạo 2 Tab
    tab_debt, tab_carry = st.tabs(["📉 Khủng hoảng Nợ công & Bài học 1997", "💸 Chiến lược Carry Trade"])

    # ==========================================================================
    # TAB 1: NỢ CÔNG & BÀI HỌC 1997
    # ==========================================================================
    with tab_debt:
        st.subheader("1. Mô phỏng Cú sốc Tỷ giá lên Nợ công")
        
        col_macro1, col_macro2 = st.columns(2)
        with col_macro1:
            debt_val = st.number_input("Tổng nợ nước ngoài (Tỷ USD):", value=50.0, step=1.0, help="Số tiền quốc gia vay bằng ngoại tệ (USD)")
            base_rate = st.number_input("Tỷ giá hiện tại (VND/USD):", value=25000.0, step=100.0)
        
        with col_macro2:
            st.markdown("#### Kịch bản Tỷ giá")
            shock_pct = st.slider("Đồng nội tệ mất giá bao nhiêu %?", min_value=0.0, max_value=100.0, value=20.0, step=1.0, help="Ví dụ: Năm 1997, đồng Baht Thái mất giá hơn 50% chỉ trong vài tháng.")
            
        # --- TÍNH TOÁN ---
        new_rate = base_rate * (1 + shock_pct/100)
        base_debt_vnd = debt_val * base_rate 
        new_debt_vnd = debt_val * new_rate   
        loss_vnd = new_debt_vnd - base_debt_vnd
        
        st.markdown("---")
        
        # HIỂN THỊ KẾT QUẢ METRIC
        m1, m2, m3 = st.columns(3)
        m1.metric("Tỷ giá sau cú sốc", f"{new_rate:,.0f} VND", f"-{shock_pct}% (Mất giá)", delta_color="inverse")
        m2.metric("Nợ quy đổi ban đầu", f"{base_debt_vnd:,.0f} Tỷ VND")
        m3.metric("Gánh nặng TĂNG THÊM", f"{loss_vnd:,.0f} Tỷ VND", delta="RỦI RO VỠ NỢ", delta_color="inverse")

        # Cảnh báo động
        if shock_pct > 30:
            st.error(f"🚨 **BÁO ĐỘNG ĐỎ:** Mức mất giá {shock_pct}% tương đương kịch bản Khủng hoảng Châu Á 1997. Nguy cơ vỡ nợ quốc gia (Sovereign Default) là rất cao.")
        elif shock_pct > 10:
            st.warning(f"⚠️ **Cảnh báo:** Gánh nặng nợ tăng thêm {loss_vnd/1000:,.1f} nghìn tỷ VND sẽ gây áp lực cực lớn lên ngân sách.")

        # --- [NEW] GIẢI THÍCH CÔNG THỨC CHI TIẾT (NỢ CÔNG) ---
        with st.expander("🧮 GÓC HỌC TẬP: GIẢI MÃ SỐ LIỆU NỢ CÔNG", expanded=True):
            st.markdown("#### 1. Tại sao Nợ lại tăng dù không vay thêm?")
            st.write("Nợ gốc tính bằng USD vẫn giữ nguyên, nhưng số tiền VND phải bỏ ra để mua USD trả nợ tăng lên do tỷ giá tăng.")
            
            st.markdown("#### 2. Công thức tính toán cụ thể:")
            st.markdown(f"""
            * **Nợ quy đổi ban đầu:** $${debt_val} \\text{{ (Tỷ USD)}} \\times {base_rate:,.0f} \\text{{ (Tỷ giá cũ)}} = \\mathbf{{{base_debt_vnd:,.0f} \\text{{ Tỷ VND}}}}$$
            
            * **Nợ sau khi mất giá:** $${debt_val} \\text{{ (Tỷ USD)}} \\times {new_rate:,.0f} \\text{{ (Tỷ giá mới)}} = \\mathbf{{{new_debt_vnd:,.0f} \\text{{ Tỷ VND}}}}$$
            
            * **Gánh nặng tăng thêm (Thiệt hại):**
                $${new_debt_vnd:,.0f} - {base_debt_vnd:,.0f} = \\mathbf{{{loss_vnd:,.0f} \\text{{ Tỷ VND}}}}$$
            """)

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

    # ==========================================================================
    # TAB 2: CARRY TRADE STRATEGY (ĐÃ CHỈNH SỬA HIỂN THỊ)
    # ==========================================================================
    with tab_carry:
        st.subheader("2. Đầu cơ Chênh lệch lãi suất (Carry Trade)")
        st.caption("Chiến lược: Vay đồng tiền lãi thấp (Funding Ccy) -> Mua đồng tiền lãi cao (Target Ccy).")
        
        # Kích hoạt tìm kiếm hình ảnh minh họa cơ chế Carry Trade
        st.markdown("")

        c1, c2 = st.columns(2)
        with c1:
            capital = st.number_input("Vốn đầu tư (Triệu USD):", value=10.0, step=1.0)
            rate_borrow = st.number_input("Lãi vay (Funding Rate %):", value=0.5, step=0.1, help="Ví dụ: Lãi suất JPY (Yên Nhật)")
            
        with c2:
            rate_invest = st.number_input("Lãi đầu tư (Target Rate %):", value=5.5, step=0.1, help="Ví dụ: Lãi suất USD hoặc VND")
            fx_move = st.slider("Biến động tỷ giá (%):", -10.0, 10.0, -2.0, 0.5, help="Dương: Đồng tiền đầu tư tăng giá (Lời). Âm: Đồng tiền đầu tư giảm giá (Lỗ).")

        st.markdown("---")
        
        # TÍNH TOÁN
        interest_diff = rate_invest - rate_borrow
        profit_interest = capital * (interest_diff / 100)
        profit_fx = capital * (fx_move / 100)
        total_pnl = profit_interest + profit_fx
        roi = (total_pnl / capital) * 100
        
        # HIỂN THỊ KẾT QUẢ
        c_res1, c_res2, c_res3 = st.columns(3)
        c_res1.metric("1. Lãi từ Lãi suất (Spread)", f"${profit_interest:,.2f} M", f"Chênh lệch: {interest_diff:.1f}%")
        c_res2.metric("2. Lãi/Lỗ từ Tỷ giá (FX)", f"${profit_fx:,.2f} M", f"Biến động: {fx_move}%")
        c_res3.metric("3. TỔNG LỢI NHUẬN", f"${total_pnl:,.2f} M", f"ROI: {roi:.1f}%", delta_color="normal")

        # --- [UPDATED] GIẢI THÍCH CÔNG THỨC CHI TIẾT ---
        with st.expander("🧮 GÓC HỌC TẬP: GIẢI MÃ CÁCH TÍNH CARRY TRADE", expanded=True):
            st.markdown("Tổng lợi nhuận đến từ 2 nguồn riêng biệt:")
            
            st.markdown("#### A. Lợi nhuận từ Lãi suất (Interest Profit)")
            st.latex(r"\text{Profit}_{\text{Rate}} = \text{Vốn} \times (\text{Lãi}_{\text{Đầu tư}} - \text{Lãi}_{\text{Vay}})")
            # Sử dụng markdown thuần túy để tránh lỗi hiển thị ký tự đặc biệt
            st.markdown(f"""
            👉 **Áp dụng:** {capital} Triệu USD × ({rate_invest}% - {rate_borrow}%) = **{profit_interest:,.2f} Triệu USD** *(Đây là phần lợi nhuận "chắc ăn" nếu tỷ giá không đổi)*
            """)
            
            st.divider()
            
            st.markdown("#### B. Lợi nhuận từ Tỷ giá (FX Profit/Loss)")
            st.latex(r"\text{Profit}_{\text{FX}} = \text{Vốn} \times \% \text{Biến động Tỷ giá}")
            st.markdown(f"""
            👉 **Áp dụng:** {capital} Triệu USD × {fx_move}% = **{profit_fx:,.2f} Triệu USD**
            """)
            
            st.info("""
            **Quy luật cốt lõi:** Carry Trade giống như việc **"nhặt tiền lẻ (Lãi suất) trước đầu xe lu (Tỷ giá)"**. 
            Bạn có thể kiếm được lợi nhuận nhỏ đều đặn từ lãi suất, nhưng một cú trượt giá bất ngờ (xe lu) có thể xóa sạch thành quả.
            """)

        carry_context = f"""
        Chiến lược Carry Trade: Capital {capital}M. Interest Spread {interest_diff}%. FX Move {fx_move}%.
        Kết quả: {'LÃI' if total_pnl > 0 else 'LỖ'} {total_pnl:.2f}M USD.
        """

    # --- AI ADVISOR (ĐỘNG) ---
    st.markdown("---")
    if st.button("AI Chuyên gia: Phân tích Rủi ro & Xu hướng", type="primary", icon="🤖"):
        if api_key:
            # Gộp ngữ cảnh cả 2 Tab
            full_context = f"""
            TÌNH HUỐNG MÔ PHỎNG:
            1. [Nợ công] Quốc gia đang chịu áp lực tỷ giá mất {shock_pct}%, nợ tăng thêm {loss_vnd:,.0f} tỷ VND.
            2. [Carry Trade] Nhà đầu cơ đang { 'lãi' if total_pnl > 0 else 'lỗ' } với ROI {roi:.1f}% (Spread {interest_diff}%, FX {fx_move}%).
            """
            
            task = """
            Đóng vai Giám đốc Chiến lược (Macro Strategist). Hãy thực hiện báo cáo nhanh:
            1.  **So sánh thực tế:** Liên hệ tình huống Carry Trade trên với sự kiện "Yên Nhật (JPY) Unwind" năm 2024. Tại sao khi đồng JPY tăng giá, thị trường chứng khoán toàn cầu lại chao đảo?
            2.  **Đánh giá rủi ro Nợ công:** Với mức mất giá {shock_pct}% của kịch bản 1, liệu quốc gia này có lặp lại vết xe đổ Thái Lan 1997 không?
            3.  **Lời khuyên:** Nhà đầu tư nên "Risk On" (Chấp nhận rủi ro) hay "Risk Off" (Trú ẩn an toàn) lúc này?
            """
            
            with st.spinner("Đang kết nối dữ liệu vĩ mô toàn cầu..."):
                advise = ask_gemini_advisor("Macro Strategist", full_context, task)
                st.markdown(f'<div class="ai-box"><h4>🤖 BÁO CÁO CHIẾN LƯỢC TOÀN CẦU</h4>{advise}</div>', unsafe_allow_html=True)
        else:
            st.warning("⚠️ Vui lòng nhập API Key.")
    
    st.markdown("---")
    st.markdown(
        """
        <div style="text-align: center; color: #888; font-size: 13px; margin-top: 10px;">
            © 2026 Designed by Nguyễn Minh Hải
        </div>
        """, 
        unsafe_allow_html=True
    )


