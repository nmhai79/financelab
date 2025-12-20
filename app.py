import streamlit as st
import pandas as pd
import altair as alt
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
    
    # 1. Nhập vốn (Động)
    capital = st.number_input("Vốn kinh doanh (USD):", value=1000000.0, step=10000.0, format="%.0f")
    
    st.markdown("---")
    
    # 2. Nhập tỷ giá các ngân hàng
    k1, k2, k3 = st.columns(3)
    with k1: bank_a = st.number_input("Bank A (USD/VND):", value=25000.0, help="Giá bán USD lấy VND")
    with k2: bank_b = st.number_input("Bank B (EUR/USD):", value=1.1000, help="Giá bán EUR lấy USD")
    with k3: bank_c = st.number_input("Bank C (EUR/VND):", value=28000.0, help="Giá bán EUR lấy VND")
    
    # --- TÍNH TOÁN LOGIC ---
    # Tính tỷ giá cân bằng lý thuyết (No Arbitrage Rate) để làm gợi ý
    fair_rate_c = bank_a * bank_b

    # Cách 1: USD -> EUR -> VND -> USD
    path1_eur = capital / bank_b
    path1_vnd = path1_eur * bank_c
    path1_usd_final = path1_vnd / bank_a
    profit1 = path1_usd_final - capital
    
    # Cách 2: USD -> VND -> EUR -> USD
    path2_vnd = capital * bank_a
    path2_eur = path2_vnd / bank_c
    path2_usd_final = path2_eur * bank_b
    profit2 = path2_usd_final - capital

    # --- [FIX LỖI] XÁC ĐỊNH KẾT QUẢ TỐT NHẤT ĐỂ CHO VÀO BIẾN ---
    # Đoạn này cần thiết để AI có dữ liệu đọc (biến best_direction chưa có ở code cũ)
    if profit1 > profit2 and profit1 > 0:
        best_direction = "Mua EUR (Bank B) ➔ Bán tại Bank C ➔ Đổi về Bank A"
        best_profit = profit1
    elif profit2 >= profit1 and profit2 > 0:
        best_direction = "Đổi VND (Bank A) ➔ Mua EUR (Bank C) ➔ Bán tại Bank B"
        best_profit = profit2
    else:
        best_direction = "Không có cơ hội (Thị trường cân bằng hoặc lỗ)"
        best_profit = 0.0

    # --- NÚT CHẠY MÔ HÌNH HIỂN THỊ ---
    if st.button("🚀 KÍCH HOẠT THUẬT TOÁN ARBITRAGE"):
        st.markdown("### 📝 Nhật ký giao dịch tối ưu:")
        
        if profit1 > 1.0: # Dùng > 1.0 để tránh lỗi làm tròn số cực nhỏ
            # Hiển thị Cách 1: B -> C -> A
            st.success(f"✅ PHÁT HIỆN CƠ HỘI: Mua EUR (Bank B) ➔ Bán tại Bank C ➔ Đổi về Bank A")
            
            st.markdown(f"""
            <div class="step-box">
            1. <b>Dùng USD mua EUR (tại Bank B):</b><br>
                {capital:,.0f} / {bank_b} = <b>{path1_eur:,.2f} EUR</b><br><br>
            2. <b>Bán EUR đổi lấy VND (tại Bank C):</b><br>
                {path1_eur:,.2f} × {bank_c} = <b>{path1_vnd:,.0f} VND</b> (Giá EUR ở C đang cao)<br><br>
            3. <b>Đổi VND về lại USD (tại Bank A):</b><br>
                {path1_vnd:,.0f} / {bank_a} = <b>{path1_usd_final:,.2f} USD</b>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown(f'<div class="result-box">🎉 LỢI NHUẬN: +{profit1:,.2f} USD</div>', unsafe_allow_html=True)
            
            # [GỢI Ý]
            st.info(f"💡 **Gợi ý:** Để thị trường cân bằng (hết lời), hãy thử chỉnh **Bank C** về **{fair_rate_c:,.0f}** (tức là {bank_a} × {bank_b}).")

        elif profit2 > 1.0:
            # Hiển thị Cách 2: A -> C -> B
            st.success(f"✅ PHÁT HIỆN CƠ HỘI: Đổi VND (Bank A) ➔ Mua EUR (Bank C) ➔ Bán tại Bank B")
            
            st.markdown(f"""
            <div class="step-box">
            1. <b>Đổi USD sang VND (tại Bank A):</b><br>
                {capital:,.0f} × {bank_a} = <b>{path2_vnd:,.0f} VND</b><br><br>
            2. <b>Dùng VND mua EUR (tại Bank C):</b><br>
                {path2_vnd:,.0f} / {bank_c} = <b>{path2_eur:,.2f} EUR</b> (Giá EUR ở C đang rẻ)<br><br>
            3. <b>Bán EUR đổi về USD (tại Bank B):</b><br>
                {path2_eur:,.2f} × {bank_b} = <b>{path2_usd_final:,.2f} USD</b>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown(f'<div class="result-box">🎉 LỢI NHUẬN: +{profit2:,.2f} USD</div>', unsafe_allow_html=True)
            
            # [GỢI Ý]
            st.info(f"💡 **Gợi ý:** Để thị trường cân bằng (hết lời), hãy thử chỉnh **Bank C** về **{fair_rate_c:,.0f}** (tức là {bank_a} × {bank_b}).")
            
        else:
            st.balloons()
            st.warning("⚖️ Thị trường cân bằng (No Arbitrage). Cả 2 chiều giao dịch đều không sinh lời.")
            # Khi đã cân bằng thì hiện thông báo khen ngợi
            st.success(f"👏 Xuất sắc! Bạn đã tìm ra tỷ giá cân bằng: {bank_c:,.0f} ≈ {bank_a} × {bank_b}")

        # Giải thích chung
        with st.expander("🎓 BẢN CHẤT: Tại sao có tiền lời?"):
            st.markdown("""
            **Nguyên lý:** Arbitrage tam giác (Triangular Arbitrage).
            
            Máy tính đã tự động so sánh hai con đường vòng quanh 3 ngân hàng:
            * **Vòng 1 (Chiều xuôi):** USD ➔ EUR (Bank B) ➔ VND (Bank C) ➔ USD (Bank A).
            * **Vòng 2 (Chiều ngược):** USD ➔ VND (Bank A) ➔ EUR (Bank C) ➔ USD (Bank B).
            
            Nếu chênh lệch giá đủ lớn, dòng tiền đi một vòng sẽ "đẻ" ra tiền lời.
            """)
            st.write("")          
    
    # --- [MỚI] THÊM DÒNG NÀY ĐỂ TẠO KHUNG BAO QUANH ---
    with st.container(border=True):
    # MINH HỌA BẰNG SƠ ĐỒ GRAPHVIZ
        st.markdown("##### 🔄 Minh họa dòng tiền kiếm lời:")

        # Tạo sơ đồ
        st.graphviz_chart('''
            digraph {
                # Thiết lập hướng từ Trái sang Phải (Left to Right)
                rankdir=LR; 
                node [fontname="Arial", shape=box, style="filled,rounded", fillcolor="#f0f2f6", color="#d1d5db"];
                edge [color="#555555", fontname="Arial", fontsize=10];

                # Định nghĩa các nút (Nodes)
                MarketA [label="📉 Thị trường A\\n(Giá Thấp)", fillcolor="#e8f5e9", color="#4caf50", penwidth=2];
                MarketB [label="📈 Thị trường B\\n(Giá Cao)", fillcolor="#ffebee", color="#f44336", penwidth=2];
                Wallet [label="💰 TÚI TIỀN\\n(Lợi nhuận)", shape=ellipse, fillcolor="#fff9c4", color="#fbc02d", style=filled];

                # Định nghĩa các đường đi (Edges)
                MarketA -> MarketB [label="1. Mua thấp & Chuyển sang", color="#4caf50", penwidth=2];
                MarketB -> Wallet [label="2. Bán cao & Chốt lời", color="#f44336", penwidth=2];
                
                # Đường ẩn để căn chỉnh (nếu cần)
            }
        ''', use_container_width=True)

        st.info("💡 **Dễ hiểu hơn:** Bạn giống như một người buôn chuyến, mua hàng ở chợ sỉ (giá rẻ) và mang ra chợ lẻ (giá cao) để bán ngay lập tức.")
            
    # --- BỔ SUNG AI CHO PHÒNG 1 (ĐÃ SỬA LỖI LOGIC ĐỘNG) ---
    st.markdown("---")
    
    if st.button("AI Trader: Đánh giá rủi ro", type="primary", icon="🤖"):
        if api_key:
            # Context ĐỘNG: Lấy đúng số vốn và lợi nhuận vừa tính ở trên
            context = f"""
            Tình huống: Giao dịch Arbitrage Tỷ giá (Triangular Arbitrage).
            - Số vốn đầu tư: {capital:,.0f} USD.
            - Tỷ giá thị trường: Bank A (USD/VND)={bank_a}, Bank B (EUR/USD)={bank_b}, Bank C (EUR/VND)={bank_c}.
            - Kết quả tính toán tốt nhất: {best_direction}.
            - Lợi nhuận lý thuyết dự kiến: {best_profit:,.2f} USD.
            """
            
            task = """
            Đóng vai một Senior FX Trader tại ngân hàng đầu tư (Goldman Sachs/JP Morgan).
            Hãy phân tích ngắn gọn:
            1. Rủi ro thực tế khi thực hiện 3 lệnh liên tiếp là gì (Gợi ý: Độ trễ/Latency và Trượt giá/Slippage)?
            2. Với mức lợi nhuận dự kiến trên, có đáng để mạo hiểm vào lệnh không? (So sánh với phí giao dịch transaction cost).
            3. Đưa ra quyết định: GO (Vào lệnh) hay NO-GO (Hủy)?
            """
            
            with st.spinner(f"AI đang phân tích cơ hội với vốn {capital:,.0f} USD..."):
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

    # --- [MỚI] BIỂU ĐỒ SO SÁNH TRỰC QUAN ---
    st.caption("👇 Biểu đồ so sánh: Cột màu XANH là phương án có chi phí thấp nhất")

    import altair as alt

    # 1. Xử lý dữ liệu: Tìm giá trị rẻ nhất để tô màu
    min_val = df_compare["Tổng chi phí (VND)"].min()
    
    # Tạo cột màu: Nếu bằng giá thấp nhất thì màu Xanh (#22c55e), còn lại màu Xám (#94a3b8)
    df_compare["Color"] = df_compare["Tổng chi phí (VND)"].apply(lambda x: "#22c55e" if x == min_val else "#94a3b8")

    # 2. Vẽ biểu đồ Cột (Bar Chart)
    base = alt.Chart(df_compare).encode(
        x=alt.X('Chiến lược', axis=alt.Axis(labelAngle=0, title=None)), # Nhãn ngang, không nghiêng
        y=alt.Y('Tổng chi phí (VND)', axis=alt.Axis(format=',.0f')),    # Trục tung format số
        tooltip=['Chiến lược', alt.Tooltip('Tổng chi phí (VND)', format=',.0f')] # Rê chuột hiện số
    )

    # Cột
    bars = base.mark_bar(cornerRadius=6).encode(
        color=alt.Color('Color', scale=None) # Dùng màu đã định nghĩa ở trên
    )

    # Nhãn số tiền trên đầu cột (Text Label)
    text = base.mark_text(
        align='center',
        baseline='bottom',
        dy=-5,  # Dịch chuyển chữ lên trên cột một chút
        color='black'
    ).encode(
        text=alt.Text('Tổng chi phí (VND)', format=',.0f')
    )

    # 3. Hiển thị biểu đồ (Kết hợp Cột + Chữ)
    st.altair_chart(bars + text, use_container_width=True)

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
            
            # Logic Delta màu sắc: Tìm giá rẻ nhất để so sánh
            best_price = min(tt_final, col_final, lc_final)
            
            m1.metric("1. Tổng phí T/T", f"${tt_final:,.2f}", 
                      delta="Rẻ nhất (Rủi ro cao)" if tt_final == best_price else None, delta_color="inverse")
            m2.metric("2. Tổng phí Nhờ thu", f"${col_final:,.2f}",
                      delta=f"+${col_final - tt_final:,.2f} vs T/T", delta_color="off")
            m3.metric("3. Tổng phí L/C", f"${lc_final:,.2f}", 
                      delta=f"+${lc_final - tt_final:,.2f} vs T/T", delta_color="off")

            # --- BIỂU ĐỒ ---
            chart_data = pd.DataFrame({
                "Phương thức": ["T/T", "Nhờ thu", "L/C"],
                "Phí Ngân hàng": [tt_total_bank, col_total_bank, lc_total_bank],
                "Chi phí Vốn (Lãi)": [tt_interest, col_interest, lc_interest]
            })
            st.bar_chart(chart_data.set_index("Phương thức"), stack=True, color=["#FF6C6C", "#4B4BFF"])
            
            # --- [HÌNH ẢNH MINH HỌA] ---
            # Thêm hình ảnh để minh họa phổ rủi ro vs chi phí
            st.write("")

            # --- [QUAN TRỌNG] DIỄN GIẢI CÔNG THỨC (FIXED DISPLAY) ---
            st.markdown("### 🧮 Bảng chi tiết lời giải (Step-by-step)")
            st.info("Dưới đây là cách tính chi tiết giúp bạn hiểu rõ nguồn gốc các con số:")

            # 1. T/T
            with st.expander("1️⃣ Chi tiết tính toán: T/T (Chuyển tiền)", expanded=False):
                st.latex(r"Cost_{T/T} = \text{Phí Bank} + \text{Lãi Vốn}")
                st.markdown(f"""
                **A. Phí dịch vụ Ngân hàng:**
                * Tính sơ bộ: {val:,.0f} USD × {tt_pct}% = {tt_raw:,.2f} USD
                * So sánh Min/Max ({tt_min} - {tt_max}) → Phí áp dụng: **{tt_bank_fee:,.2f} USD**
                * Cộng Điện phí ({tt_other} USD) → Tổng phí Bank: **{tt_total_bank:,.2f} USD**

                **B. Chi phí vốn (Lãi vay):**
                * Công thức: $\\text{{Giá trị}} \\times \\text{{Lãi suất}} \\times \\frac{{\\text{{Ngày}}}}{{360}}$
                * Thế số: {val:,.0f} × {interest_rate}% × ({days_tt}/360) = **{tt_interest:,.2f} USD**
                """)

            # 2. COLLECTION
            with st.expander("2️⃣ Chi tiết tính toán: Nhờ thu (Collection)", expanded=False):
                st.latex(r"Cost_{Col} = \text{Phí Nhờ Thu} + \text{Phí Khác} + \text{Lãi Vốn}")
                st.markdown(f"""
                **A. Phí dịch vụ Ngân hàng:**
                * Tính sơ bộ: {val:,.0f} USD × {col_pct}% = {col_raw:,.2f} USD
                * So sánh Min/Max ({col_min} - {col_max}) → Phí áp dụng: **{col_bank_fee:,.2f} USD**
                * Cộng phí khác ({col_other} USD) → Tổng phí Bank: **{col_total_bank:,.2f} USD**

                **B. Chi phí vốn:**
                * Thế số: {val:,.0f} × {interest_rate}% × ({days_col}/360) = **{col_interest:,.2f} USD**
                """)

            # 3. L/C
            with st.expander("3️⃣ Chi tiết tính toán: L/C (Tín dụng thư)", expanded=False):
                st.latex(r"Cost_{LC} = \text{Phí Mở} + \text{Phí T.Toán} + \text{Phí Khác} + \text{Lãi Vốn}")
                st.markdown(f"""
                **A. Các loại phí Ngân hàng:**
                * Phí Mở L/C: {val:,.0f} × {lc_open_pct}% = {lc_open_fee:,.2f} USD *(Tối thiểu {lc_min} USD)*
                * Phí Thanh toán: {val:,.0f} × {lc_pay_pct}% = {lc_pay_fee:,.2f} USD
                * Phí Khác: {lc_other:,.2f} USD

                **B. Chi phí vốn (Gánh nặng lớn nhất):**
                * Do L/C giữ vốn lâu hơn ({days_lc} ngày), tiền lãi phát sinh là:
                * {val:,.0f} × {interest_rate}% × ({days_lc}/360) = **{lc_interest:,.2f} USD**
                """)
                
            # --- KẾT LUẬN QUẢN TRỊ (DYNAMIC LOGIC UPDATE) ---
            st.markdown("---")
            
            # Tính toán chênh lệch
            diff_lc = lc_final - tt_final
            diff_col = col_final - tt_final
            
            with st.container():
                st.success(f"""
                #### 💡 GÓC NHÌN QUẢN TRỊ (MANAGEMENT INSIGHT)
                
                Dưới góc độ tài chính, chênh lệch chi phí chính là **"Phí mua sự an toàn"**. 
                Với lô hàng **{val:,.0f} USD** này, thị trường đang ra giá cho rủi ro như sau:
                
                **1. Nếu chọn NHỜ THU (Collection):**
                * Bạn trả thêm: **{diff_col:,.2f} USD** so với T/T.
                * *Đánh giá:* Mức phí trung bình. Ngân hàng hỗ trợ khống chế bộ chứng từ, nhưng không cam kết trả tiền thay người mua.
                
                **2. Nếu chọn L/C (Tín dụng thư):**
                * Bạn trả thêm: **{diff_lc:,.2f} USD** so với T/T.
                * *Đánh giá:* Mức phí cao nhất. Đổi lại, bạn mua được cam kết thanh toán từ Ngân hàng, loại bỏ rủi ro đối tác mất khả năng chi trả.
                
                👉 **QUYẾT ĐỊNH:** Nếu bạn thấy rủi ro mất trắng lô hàng {val:,.0f} USD là hiện hữu, thì con số **{diff_lc:,.2f} USD** là quá rẻ để bảo hiểm cho toàn bộ dòng tiền.
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
    
    # --- 0. KHỞI TẠO STATE (Lưu trạng thái các nút bấm) ---
    # Các cờ (Flags) để biết nút nào đang được BẬT
    if 's_late_ship' not in st.session_state: st.session_state['s_late_ship'] = False
    if 's_late_pres' not in st.session_state: st.session_state['s_late_pres'] = False
    if 's_over_amt' not in st.session_state: st.session_state['s_over_amt'] = False
    if 's_dirty_bl' not in st.session_state: st.session_state['s_dirty_bl'] = False

    # Các giá trị Input (Ngày tháng, số tiền)
    if 'chk_ship' not in st.session_state: st.session_state['chk_ship'] = pd.to_datetime("2025-01-15")
    if 'chk_exp' not in st.session_state: st.session_state['chk_exp'] = pd.to_datetime("2025-02-28")
    if 'chk_pres' not in st.session_state: st.session_state['chk_pres'] = pd.to_datetime("2025-01-20")
    if 'chk_inv' not in st.session_state: st.session_state['chk_inv'] = 100000.0
    if 'chk_dirty' not in st.session_state: st.session_state['chk_dirty'] = False

    # --- HÀM LOGIC: Cập nhật dữ liệu dựa trên các nút đang BẬT ---
    def update_inputs():
        # 1. Đặt về mặc định (Sạch) trước
        ship = pd.to_datetime("2025-01-15")
        exp = pd.to_datetime("2025-02-28")
        pres = pd.to_datetime("2025-01-20")
        amt = 100000.0
        is_dirty = False

        # 2. Cộng dồn các lỗi (Nếu nút đang BẬT)
        
        # Nếu lỗi Giao trễ -> Đẩy ngày giao sau ngày hết hạn
        if st.session_state['s_late_ship']:
            ship = pd.to_datetime("2025-03-01") 
        
        # Nếu lỗi Xuất trình muộn -> Đẩy ngày xuất trình = Ngày giao + 24 ngày
        if st.session_state['s_late_pres']:
            pres = ship + pd.Timedelta(days=24)
        else:
            # Nếu không lỗi, giữ logic hợp lý (Giao + 5 ngày) nhưng phải check lại nếu ship đã đổi
            pres = ship + pd.Timedelta(days=5)

        # Nếu lỗi Tiền -> Tăng tiền
        if st.session_state['s_over_amt']:
            amt = 110000.0 # Vượt dung sai
        
        # Nếu lỗi B/L -> Tick chọn
        if st.session_state['s_dirty_bl']:
            is_dirty = True

        # 3. Gán ngược lại vào Session State của Input
        st.session_state['chk_ship'] = ship
        st.session_state['chk_exp'] = exp
        st.session_state['chk_pres'] = pres
        st.session_state['chk_inv'] = amt
        st.session_state['chk_dirty'] = is_dirty

    # Hàm Reset toàn bộ
    def reset_scenarios():
        st.session_state['s_late_ship'] = False
        st.session_state['s_late_pres'] = False
        st.session_state['s_over_amt'] = False
        st.session_state['s_dirty_bl'] = False
        update_inputs() # Cập nhật lại về mặc định

    # Hàm Toggle (Bật/Tắt) từng nút
    def toggle_scenario(key):
        st.session_state[key] = not st.session_state[key]
        update_inputs()

    # --- [GIAO DIỆN] KHUNG CHỌN TÌNH HUỐNG ---
    with st.expander("🎯 GỢI Ý KỊCH BẢN (Cho phép chọn nhiều lỗi cùng lúc)", expanded=True):
        st.write("Bấm vào các nút để **Bật/Tắt** tình huống lỗi tương ứng (Nút sáng màu là đang chọn):")
        
        sc1, sc2, sc3, sc4, sc5 = st.columns(5)
        
        with sc1:
            # Nút Giao trễ
            btn_type = "primary" if st.session_state['s_late_ship'] else "secondary"
            if st.button("🚢 Giao trễ", key="btn_late", type=btn_type, help="Giao hàng sau ngày hết hạn L/C", use_container_width=True):
                toggle_scenario('s_late_ship')
                st.rerun()

        with sc2:
            # Nút Xuất trình muộn
            btn_type = "primary" if st.session_state['s_late_pres'] else "secondary"
            if st.button("🕒 Trình muộn", key="btn_pres", type=btn_type, help="Xuất trình quá 21 ngày", use_container_width=True):
                toggle_scenario('s_late_pres')
                st.rerun()

        with sc3:
            # Nút Vượt tiền
            btn_type = "primary" if st.session_state['s_over_amt'] else "secondary"
            if st.button("💸 Vượt tiền", key="btn_amt", type=btn_type, help="Hóa đơn vượt quá dung sai", use_container_width=True):
                toggle_scenario('s_over_amt')
                st.rerun()

        with sc4:
            # Nút B/L bẩn
            btn_type = "primary" if st.session_state['s_dirty_bl'] else "secondary"
            if st.button("📝 B/L bẩn", key="btn_dirty", type=btn_type, help="Vận đơn có ghi chú xấu", use_container_width=True):
                toggle_scenario('s_dirty_bl')
                st.rerun()
        
        with sc5:
            # Nút Reset (Nằm riêng, icon xoay)
            if st.button("🔄 Reset", help="Xóa hết chọn, quay về mặc định", type="secondary", use_container_width=True):
                reset_scenarios()
                st.rerun()

    st.markdown("---")

    # --- INPUTS (Đã gắn Key để liên kết với logic trên) ---
    c1, c2 = st.columns(2)
    
    with c1:
        st.markdown("#### 📅 Yếu tố Thời gian")
        lc_issue_date = st.date_input("Ngày phát hành L/C:", value=pd.to_datetime("2025-01-01"))
        
        # Các input này tự động nhảy số khi hàm update_inputs() chạy
        ship_date = st.date_input("Ngày giao hàng (On Board Date):", key='chk_ship')
        lc_exp_date = st.date_input("Ngày hết hạn L/C (Expiry Date):", key='chk_exp')
        pres_date = st.date_input("Ngày xuất trình (Presentation Date):", key='chk_pres')
        
    with c2:
        st.markdown("#### 💰 Yếu tố Tài chính & Hàng hóa")
        lc_amount = st.number_input("Giá trị L/C (USD):", value=100000.0, step=1000.0)
        tolerance = st.number_input("Dung sai cho phép (+/- %):", value=5.0, step=1.0)
        
        inv_amount = st.number_input("Giá trị Hóa đơn Thương mại (Invoice):", step=1000.0, key='chk_inv')
        
        st.markdown("#### 📝 Tình trạng Vận đơn (B/L)")
        is_dirty_bl = st.checkbox("Trên B/L có ghi chú xấu? (VD: 'Bao bì rách')", key='chk_dirty')
        
    st.markdown("---")
    
    # --- NÚT CHECKING (Logic giữ nguyên, chỉ lấy giá trị từ biến) ---
    if st.button("🔍 SOÁT XÉT CHỨNG TỪ (CHECKING)", type="secondary", use_container_width=True):
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
                <div style="background-color: #ffeded; color: #333333; padding: 10px; border-radius: 5px; margin-bottom: 10px; border-left: 5px solid #ff4b4b;">
                    <strong>{idx}. Lỗi: {err_name}</strong><br>
                    Explain: <em>{err_desc}</em><br>
                    ⚖️ Căn cứ: <strong>UCP 600 - {ucp_art}</strong>
                </div>
                """, unsafe_allow_html=True)
            
            st.warning("👉 **Hậu quả:** Ngân hàng có quyền TỪ CHỐI THANH TOÁN và thu phí bất hợp lệ (Discrepancy Fee) từ 50-100 USD/lỗi.")
    
    # --- NÚT GỌI AI ---
    st.markdown("---")
    if st.button("AI Luật sư: Tư vấn UCP 600", type="primary", icon="🤖"):
        if api_key:
            # TÍNH TOÁN LẠI ĐỂ LẤY DỮ LIỆU MỚI NHẤT GỬI AI
            curr_errs = []
            if ship_date > lc_exp_date: curr_errs.append("Late Shipment")
            if pres_date > lc_exp_date: curr_errs.append("L/C Expired")
            if (pres_date - ship_date).days > 21: curr_errs.append("Stale Documents")
            if inv_amount > (lc_amount * (1 + tolerance/100)): curr_errs.append("Overdrawn")
            if is_dirty_bl: curr_errs.append("Dirty B/L")

            context = f"""
            DỮ LIỆU: Ship: {ship_date}, Exp: {lc_exp_date}, Pres: {pres_date}, Inv: {inv_amount}, Dirty B/L: {is_dirty_bl}.
            LỖI PHÁT HIỆN: {', '.join(curr_errs) if curr_errs else 'None'}.
            """
            
            task = "Đóng vai chuyên gia UCP 600, giải thích ngắn gọn lỗi và cách khắc phục cho doanh nghiệp."
            
            with st.spinner("Đang tham vấn..."):
                advise = ask_gemini_advisor("Expert", context, task)
                st.markdown(f'<div class="ai-box">{advise}</div>', unsafe_allow_html=True)
        else:
            st.warning("⚠️ Vui lòng nhập API Key.")

    st.markdown("---")
    st.markdown('<div style="text-align: center; color: #888; font-size: 13px;">© 2026 Designed by Nguyễn Minh Hải</div>', unsafe_allow_html=True)
# ==============================================================================
# PHÒNG 4: ĐẦU TƯ QUỐC TẾ (FIX LỖI NÚT AI + SESSION STATE)
# ==============================================================================
elif "4." in room:
    # --- IMPORT THƯ VIỆN TÀI CHÍNH ---
    try:
        import numpy_financial as npf
    except ImportError:
        st.error("⚠️ Thư viện 'numpy_financial' chưa được cài đặt. Vui lòng chạy `pip install numpy-financial` để tính IRR.")
        import numpy as npf 

    st.markdown('<p class="header-style">🏭 Phòng Đầu tư Quốc tế (Investment Dept)</p>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="role-card">
        <div class="role-title">👤 Vai diễn: Chuyên viên Phân tích Đầu tư (Investment Analyst)</div>
        <div class="mission-text">"Nhiệm vụ: Thẩm định dự án FDI, Tính toán IRR/NPV và Đánh giá rủi ro tỷ giá."</div>
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
            wacc = st.number_input("Chi phí vốn (WACC %):", value=12.0, step=0.5, help="Tỷ suất sinh lời yêu cầu của nhà đầu tư (Hurdle Rate)")
            
    st.markdown("---")

    # --- XỬ LÝ TRẠNG THÁI (SESSION STATE) ĐỂ GIỮ NÚT AI KHÔNG BIẾN MẤT ---
    if "run_dcf" not in st.session_state:
        st.session_state.run_dcf = False

    # Nút kích hoạt tính toán
    if st.button("📊 CHẠY MÔ HÌNH DCF & PHÂN TÍCH ĐỘ NHẠY"):
        st.session_state.run_dcf = True

    # --- 2. TÍNH TOÁN & HIỂN THỊ (CHỈ CHẠY KHI ĐÃ KÍCH HOẠT) ---
    if st.session_state.run_dcf:
        
        # A. TÍNH DÒNG TIỀN CƠ SỞ (BASE CASE)
        data_cf = []
        cf_stream_vnd_nominal = [] # Dòng tiền danh nghĩa để tính IRR
        cumulative_pv = 0
        payback_period = None
        
        # Năm 0
        cf0_vnd = -inv * fx_spot
        cumulative_pv += cf0_vnd
        cf_stream_vnd_nominal.append(cf0_vnd)
        
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
            fx_future = fx_spot * ((1 + depre/100) ** i)
            cf_usd = cf_yearly + (salvage_val if i == years else 0)
            cf_vnd = cf_usd * fx_future
            cf_stream_vnd_nominal.append(cf_vnd) 
            
            pv_vnd = cf_vnd / ((1 + wacc/100) ** i)
            
            prev_cumulative = cumulative_pv
            cumulative_pv += pv_vnd
            
            if payback_period is None and cumulative_pv >= 0:
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
            
        npv = cumulative_pv 
        
        # Tính IRR
        try:
            irr_value = npf.irr(cf_stream_vnd_nominal) * 100
        except:
            irr_value = 0 
        
        # B. HIỂN THỊ KẾT QUẢ
        st.subheader("1. Kết quả Thẩm định")
        
        m1, m2, m3 = st.columns(3)
        m1.metric("NPV (Giá trị hiện tại ròng)", f"{npv:,.0f} VND", 
                 delta="Đáng đầu tư" if npv > 0 else "Lỗ vốn")
        
        if payback_period:
            m2.metric("Thời gian hoàn vốn (DPP)", f"{payback_period:.2f} Năm")
        else:
            m2.metric("Thời gian hoàn vốn", "Chưa hoàn vốn", delta_color="inverse")
            
        m3.metric("IRR (Hoàn vốn nội bộ)", f"{irr_value:.2f}%", 
                  help="Tỷ suất sinh lời thực tế. So sánh với WACC.",
                  delta=f"WACC: {wacc}%", delta_color="normal")

        # KẾT LUẬN TỰ ĐỘNG
        is_feasible = (npv > 0) and (irr_value > wacc)
        if is_feasible:
            st.success(f"✅ KẾT LUẬN: NÊN ĐẦU TƯ. Dự án tạo ra lợi nhuận ròng dương ({npv:,.0f} VND) và IRR ({irr_value:.2f}%) cao hơn chi phí vốn.")
        else:
            reason = []
            if npv <= 0: reason.append("NPV âm")
            if irr_value <= wacc: reason.append(f"IRR ({irr_value:.2f}%) thấp hơn WACC")
            st.error(f"⛔ KẾT LUẬN: KHÔNG NÊN ĐẦU TƯ. Lý do: {', '.join(reason)}.")

        # Biểu đồ kết hợp
        df_chart = pd.DataFrame(data_cf)
        st.bar_chart(df_chart.set_index("Năm")[["PV (Hiện giá VND)"]], color="#4B4BFF")
        
        with st.expander("🔎 Xem bảng dòng tiền chi tiết (Cashflow Table)"):
            st.dataframe(pd.DataFrame(data_cf).style.format("{:,.0f}"))

        # C. GIẢI THÍCH CÔNG THỨC CHI TIẾT
        with st.expander("🎓 GÓC HỌC TẬP: GIẢI MÃ CÔNG THỨC & SỐ LIỆU", expanded=True):
            
            # --- 1. NPV ---
            st.markdown("#### 1. Công thức tính NPV Điều chỉnh Tỷ giá")
            st.markdown("Dòng tiền USD được quy đổi ra VND theo tỷ giá kỳ vọng từng năm trước khi chiết khấu.")
            st.latex(r"NPV = -I_0 \times S_0 + \sum_{t=1}^{n} \frac{(CF_{t, USD} + TV_n) \times S_t}{(1 + \text{WACC})^t}")
            st.markdown(f"""
            **Trong đó:**
            * $I_0$: Vốn đầu tư ban đầu ({inv:,.0f} USD).
            * $CF_{{t, USD}}$: Dòng tiền hoạt động ({cf_yearly:,.0f} USD).
            * $S_t$: Tỷ giá dự báo năm $t$, tính bằng: $S_0 \\times (1 + {depre}\%)^t$.
            """)
            
            st.divider()
            
            # --- 2. DPP ---
            st.markdown("#### 2. Công thức Thời gian hoàn vốn (DPP)")
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

            # --- 3. IRR ---
            st.markdown("#### 3. Công thức Tỷ suất hoàn vốn nội bộ (IRR)")
            st.markdown("**IRR** là mức lãi suất mà tại đó **NPV = 0**.")
            st.latex(r"NPV = \sum_{t=0}^{n} \frac{CF_{t, VND}}{(1 + IRR)^t} = 0")
            st.markdown(f"👉 Trong bài này: IRR = **{irr_value:.2f}%** so với WACC = **{wacc}%**.")

        # D. PHÂN TÍCH ĐỘ NHẠY
        st.subheader("2. Phân tích Độ nhạy (Sensitivity Analysis)")
        st.markdown("Kiểm tra sức khỏe dự án khi **WACC** và **Mức mất giá VND** thay đổi.")
        
        wacc_range = [wacc - 2, wacc - 1, wacc, wacc + 1, wacc + 2]
        depre_range = [depre - 2, depre - 1, depre, depre + 1, depre + 2]
        
        sensitivity_data = []
        for w in wacc_range:
            row = []
            for d in depre_range:
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
        
        # E. AI ADVISOR (ĐÃ FIX LỖI BIẾN MẤT)
        st.markdown("---")
        
        # Tạo key unique cho button AI để tránh conflict
        if st.button("AI Chuyên viên: Đánh giá Dự án", type="primary", icon="🤖", key="btn_ai_invest"):
             if api_key:
                context = f"""
                Dự án FDI Thẩm định:
                - Vốn: {inv:,.0f} USD. CF hằng năm: {cf_yearly:,.0f} USD. Thanh lý: {salvage_val:,.0f} USD.
                - Số năm: {years}. WACC: {wacc}%. Mất giá VND: {depre}%.
                - NPV: {npv:,.0f} VND. IRR: {irr_value:.2f}%. DPP: {payback_period}.
                """
                task = """
                Đóng vai Giám đốc Tài chính (CFO). 
                1. Nhận xét về tính khả thi của dự án (NPV, IRR vs WACC).
                2. Phân tích rủi ro tỷ giá.
                3. Đưa ra khuyến nghị: Duyệt hay Từ chối?
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


