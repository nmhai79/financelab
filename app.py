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
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Thị trường 1: USD/VND")
            usd_bid = st.number_input("BID (NH Mua vào):", value=25350.0, step=10.0)
            usd_ask = st.number_input("ASK (NH Bán ra):", value=25450.0, step=10.0)
        with c2:
            st.subheader("Thị trường 2: EUR/USD")
            eur_bid = st.number_input("BID (NH Mua EUR):", value=1.0820, format="%.4f")
            eur_ask = st.number_input("ASK (NH Bán EUR):", value=1.0850, format="%.4f")
            
        if st.button("🚀 TÍNH TOÁN & NIÊM YẾT"):
            cross_bid = eur_bid * usd_bid
            cross_ask = eur_ask * usd_ask
            spread = cross_ask - cross_bid
            
            st.success(f"✅ TỶ GIÁ EUR/VND NIÊM YẾT: {cross_bid:,.0f} - {cross_ask:,.0f}")
            st.info(f"Spread (Chênh lệch giá): {spread:,.0f} VND")
            
            # --- PHẦN GIẢI THÍCH ---
            with st.expander("🎓 GIẢI THÍCH CÔNG THỨC & NGHIỆP VỤ", expanded=True):
                st.markdown(r"""
                **1. Công thức toán học:**
                $$
                \text{EUR/VND}_{Bid} = \text{EUR/USD}_{Bid} \times \text{USD/VND}_{Bid}
                $$
                $$
                \text{EUR/VND}_{Ask} = \text{EUR/USD}_{Ask} \times \text{USD/VND}_{Ask}
                $$
                
                **2. Giải thích nghiệp vụ:**
                Tại sao lại nhân `Bid x Bid`?
                * Để Ngân hàng Mua EUR (trả VND) cho khách, ngân hàng phải thực hiện 2 bước trên thị trường quốc tế:
                    1.  Mua EUR (trả bằng USD) -> Dùng tỷ giá **EUR/USD Bid**.
                    2.  Bán ngay số USD đó (để lấy VND trả khách) -> Dùng tỷ giá mua USD của thị trường (tức **USD/VND Bid**).
                * Do đó, Tỷ giá chéo Bid là tích của 2 tỷ giá Bid thành phần.
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

    with tab2:
        st.write("Vốn kinh doanh: **1,000,000 USD**")
        k1, k2, k3 = st.columns(3)
        with k1: bank_a = st.number_input("Bank A (USD/VND):", value=25000.0)
        with k2: bank_b = st.number_input("Bank B (EUR/USD):", value=1.1000)
        with k3: bank_c = st.number_input("Bank C (EUR/VND):", value=28000.0)
        
        # Nút tính toán ban đầu
        if st.button("🔍 CHẠY MÔ HÌNH DÒNG TIỀN"):
            step1_eur = 1000000 / bank_b
            step2_vnd = step1_eur * bank_c
            step3_usd = step2_vnd / bank_a
            profit = step3_usd - 1000000
            
            st.markdown("### 📝 Nhật ký giao dịch chi tiết:")
            st.markdown(f"""
            <div class="step-box">
            1. <b>Bán USD tại Bank B:</b> 1,000,000 / {bank_b} = <b>{step1_eur:,.2f} EUR</b><br>
            2. <b>Bán EUR tại Bank C:</b> {step1_eur:,.2f} x {bank_c} = <b>{step2_vnd:,.0f} VND</b><br>
            3. <b>Mua lại USD tại Bank A:</b> {step2_vnd:,.0f} / {bank_a} = <b>{step3_usd:,.2f} USD</b>
            </div>
            """, unsafe_allow_html=True)
            
            if profit > 0:
                st.markdown(f'<div class="result-box">🎉 LỢI NHUẬN: +{profit:,.2f} USD</div>', unsafe_allow_html=True)
            else:
                st.error(f"⚠️ THUA LỖ: {profit:,.2f} USD")
            
            with st.expander("🎓 BẢN CHẤT ARBITRAGE"):
                st.write("""
                Cơ hội kinh doanh chênh lệch giá (Arbitrage) xuất hiện khi tỷ giá chéo tính toán (Lý thuyết) khác với tỷ giá chéo thực tế trên thị trường.
                Trong trường hợp này, dòng tiền chạy theo vòng tròn (USD -> EUR -> VND -> USD) để tận dụng sự định giá sai lệch giữa các ngân hàng.
                """)
                
        # --- BỔ SUNG AI CHO PHÒNG 1 ---
        st.markdown("---")
        # Dùng tham số icon="🤖" để render ổn định hơn
        if st.button("Hỏi AI Trader: Đánh giá rủi ro", type="primary", icon="🤖"):
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
    st.caption("Bước đầu tiên: Xác định mức giá 'công bằng' dựa trên chênh lệch lãi suất VND và USD.")
    
    col_irp1, col_irp2, col_irp3 = st.columns(3)
    with col_irp1:
        spot_irp = st.number_input("Spot Rate (Hiện tại):", value=25000.0, step=10.0)
    with col_irp2:
        r_vnd = st.number_input("Lãi suất VND (%/năm):", value=6.0, step=0.1)
    with col_irp3:
        r_usd = st.number_input("Lãi suất USD (%/năm):", value=3.0, step=0.1)
        
    # Công thức IRP
    fwd_cal = spot_irp * (1 + (r_vnd/100)*(days_loan/360)) / (1 + (r_usd/100)*(days_loan/360))
    
    # Hiển thị kết quả & Công thức
    col_res_irp1, col_res_irp2 = st.columns([1, 2])
    with col_res_irp1:
        st.metric("Tỷ giá Forward (IRP)", f"{fwd_cal:,.2f} VND")
    with col_res_irp2:
        with st.expander("🎓 CÔNG THỨC IRP"):
            st.latex(r"F = S \times \frac{1 + r_{VND} \times \frac{n}{360}}{1 + r_{USD} \times \frac{n}{360}}")
            st.caption("Nguyên lý: Lãi suất VND cao hơn USD -> VND sẽ giảm giá trong tương lai (Forward > Spot).")

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
    if st.button("Hỏi AI CFO: Phân tích chuyên sâu", type="primary", icon="🤖"):
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
    
    tab_cost, tab_check = st.tabs(["💰 Bài toán Chi phí (L/C vs T/T)", "📝 Kiểm tra Chứng từ (Checking)"])
    
    with tab_cost:
        # 1. Nhập giá trị hợp đồng
        st.subheader("1. Thông tin Hợp đồng")
        val = st.number_input("Giá trị hợp đồng (USD):", value=100000, step=1000)

        st.markdown("---")
        
        # 2. Cấu hình Biểu phí (Cho phép sinh viên tự nhập)
        st.subheader("2. Cấu hình Biểu phí Ngân hàng")
        col_fee1, col_fee2 = st.columns(2)
        
        with col_fee1:
            st.markdown("#### 📉 Phương thức T/T (Chuyển tiền)")
            st.caption("Thường gồm: Phí chuyển tiền (%) + Điện phí.")
            tt_pct = st.number_input("Phí chuyển tiền (% trên giá trị):", value=0.2, step=0.01, format="%.2f")
            tt_fixed = st.number_input("Điện phí cố định (USD):", value=20.0, step=5.0)
            
        with col_fee2:
            st.markdown("#### 🛡️ Phương thức L/C (Tín dụng thư)")
            st.caption("Thường gồm: Phí phát hành (%) + Phí xử lý chứng từ.")
            lc_pct = st.number_input("Phí phát hành L/C (% trên giá trị):", value=1.0, step=0.01, format="%.2f")
            lc_fixed = st.number_input("Phí xử lý & bưu điện phí (USD):", value=100.0, step=10.0)

        st.markdown("---")

        if st.button("🚀 TÍNH TOÁN & SO SÁNH CHI PHÍ"):
            # 1. Tính toán
            tt_fee_total = val * (tt_pct / 100) + tt_fixed
            lc_fee_total = val * (lc_pct / 100) + lc_fixed
            
            # 2. Hiển thị kết quả dạng Metrics
            c1, c2 = st.columns(2)
            c1.metric("Tổng phí T/T (Chuyển tiền)", f"{tt_fee_total:,.2f} USD")
            
            # Logic hiển thị so sánh
            if lc_fee_total > tt_fee_total:
                # Trường hợp phổ biến: L/C đắt hơn
                diff = lc_fee_total - tt_fee_total
                times = lc_fee_total / tt_fee_total if tt_fee_total > 0 else 0
                c2.metric("Tổng phí L/C (Tín dụng thư)", f"{lc_fee_total:,.2f} USD", delta=f"Đắt gấp {times:.1f} lần T/T", delta_color="inverse")
                
                result_msg = f"💡 **Kết luận:** L/C đắt hơn T/T là **{diff:,.2f} USD**."
                reason_msg = f"""
                Dựa trên số liệu bạn nhập, L/C cao hơn chủ yếu do:
                1.  **Phí rủi ro ({lc_pct}%):** Bạn đang trả tiền để Ngân hàng gánh rủi ro thay cho mình.
                2.  **Phí thủ tục ({lc_fixed}$):** Quy trình kiểm tra chứng từ của L/C phức tạp hơn nhiều so với chỉ 'bấm nút chuyển tiền' của T/T.
                """
                
            elif tt_fee_total > lc_fee_total:
                # Trường hợp hiếm (hoặc do nhập liệu đặc biệt): T/T đắt hơn
                diff = tt_fee_total - lc_fee_total
                times = tt_fee_total / lc_fee_total if lc_fee_total > 0 else 0
                c2.metric("Tổng phí L/C (Tín dụng thư)", f"{lc_fee_total:,.2f} USD", delta=f"Rẻ hơn T/T {diff:,.2f} USD", delta_color="normal")
                
                result_msg = f"💡 **Kết luận thú vị:** Trong kịch bản này, T/T lại đắt hơn L/C là **{diff:,.2f} USD**."
                reason_msg = f"""
                **Tại sao lại có kết quả lạ này?**
                * Có vẻ bạn đang đặt phí chuyển tiền T/T quá cao (**{tt_pct}%**) hoặc phí L/C quá thấp.
                * Trong thực tế, điều này hiếm khi xảy ra vì L/C luôn bao gồm cả công sức xử lý chứng từ và rủi ro tín dụng.
                """
            else:
                # Trường hợp bằng nhau
                c2.metric("Tổng phí L/C (Tín dụng thư)", f"{lc_fee_total:,.2f} USD", delta="Bằng nhau", delta_color="off")
                result_msg = "💡 **Kết luận:** Hai phương thức có chi phí bằng nhau."
                reason_msg = "Bạn đã thiết lập các mức phí khiến chi phí hai bên cân bằng. Hãy thử tăng phí phát hành L/C để thấy sự khác biệt thực tế."

            # 3. Xuất ra màn hình
            st.info(result_msg)
            
            with st.expander("🎓 GIẢI THÍCH CHI TIẾT", expanded=True):
                st.markdown(reason_msg)

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
        st.subheader("1. Thông tin Bộ chứng từ")
        
        # Chia 2 cột: Cột Thời gian & Cột Tài chính/Hàng hóa
        c1, c2 = st.columns(2)
        
        with c1:
            st.markdown("#### 📅 Yếu tố Thời gian")
            lc_issue_date = st.date_input("Ngày phát hành L/C:", value=pd.to_datetime("2025-01-01"))
            ship_date = st.date_input("Ngày giao hàng (On Board Date):", value=pd.to_datetime("2025-01-15"))
            lc_exp_date = st.date_input("Ngày hết hạn L/C (Expiry Date):", value=pd.to_datetime("2025-02-28"))
            pres_date = st.date_input("Ngày xuất trình (Presentation Date):", value=pd.to_datetime("2025-01-20"))
            
        with c2:
            st.markdown("#### 💰 Yếu tố Tài chính & Hàng hóa")
            lc_amount = st.number_input("Giá trị L/C (USD):", value=100000.0, step=1000.0)
            tolerance = st.number_input("Dung sai cho phép (+/- %):", value=5.0, step=1.0, help="Điều 30 UCP 600")
            inv_amount = st.number_input("Giá trị Hóa đơn Thương mại (Invoice):", value=104000.0, step=1000.0)
            
            st.markdown("#### 📝 Tình trạng Vận đơn (B/L)")
            is_dirty_bl = st.checkbox("Trên B/L có ghi chú xấu? (VD: 'Bao bì rách', 'Thùng rò rỉ')", value=False)
            
        st.markdown("---")
        
        # Biến lưu lỗi để AI đọc (nếu cần)
        ai_errors = []
        
        if st.button("🔍 SOÁT XÉT CHỨNG TỪ (CHECKING)"):
            errors = []
            
            # --- LOGIC KIỂM TRA (CHECKING LOGIC) ---
            
            # 1. Kiểm tra Thời gian (Dates)
            if ship_date > lc_exp_date:
                errors.append(("Late Shipment", "Hàng được giao sau ngày hết hạn L/C.", "Điều 14c"))
            
            if pres_date > lc_exp_date:
                errors.append(("L/C Expired", "Chứng từ xuất trình khi L/C đã hết hạn.", "Điều 6d"))
                
            presentation_period = (pres_date - ship_date).days
            if presentation_period > 21:
                errors.append(("Stale Documents", f"Xuất trình muộn {presentation_period} ngày (Quy định tối đa 21 ngày sau ngày giao hàng).", "Điều 14c"))
            
            if presentation_period < 0:
                 errors.append(("Impossible Date", "Ngày xuất trình diễn ra TRƯỚC ngày giao hàng (Vô lý).", "Logic"))

            # 2. Kiểm tra Số tiền (Amount & Tolerance)
            max_allowed = lc_amount * (1 + tolerance/100)
            if inv_amount > max_allowed:
                over_amt = inv_amount - max_allowed
                errors.append(("Overdrawn Credit", f"Số tiền hóa đơn ({inv_amount:,.0f}) vượt quá dung sai cho phép ({max_allowed:,.0f}). Vượt: {over_amt:,.0f} USD.", "Điều 30b"))

            # 3. Kiểm tra Vận đơn (Clean B/L)
            if is_dirty_bl:
                errors.append(("Unclean B/L", "Vận đơn không hoàn hảo (Dirty/Claused B/L). Ngân hàng từ chối thanh toán nếu hàng hóa/bao bì bị ghi chú tình trạng xấu.", "Điều 27"))

            # --- HIỂN THỊ KẾT QUẢ ---
            if not errors:
                st.success("✅ **CLEAN DOCUMENTS (BỘ CHỨNG TỪ HOÀN HẢO)**")
                st.info("💡 **Kết luận:** Ngân hàng phát hành **bắt buộc phải thanh toán** (Honour) vì chứng từ phù hợp quy định.")
                ai_errors = [] # Reset cho AI
            else:
                st.error(f"❌ **DISCREPANT DOCUMENTS (BỘ CHỨNG TỪ CÓ {len(errors)} LỖI)**")
                
                # Tạo danh sách lỗi để hiển thị và gửi cho AI
                ai_errors = [e[0] for e in errors] 
                
                for idx, (err_name, err_desc, ucp_art) in enumerate(errors, 1):
                    st.markdown(f"""
                    **{idx}. Lỗi: {err_name}**
                    * *Chi tiết:* {err_desc}
                    * *Căn cứ pháp lý:* **UCP 600 - {ucp_art}**
                    """)
                
                st.warning("💡 **Hậu quả:** Ngân hàng có quyền **TỪ CHỐI THANH TOÁN** và thu phí bất hợp lệ (Discrepancy Fee).")

        # --- NÚT GỌI AI (ĐÃ CẬP NHẬT LOGIC ĐỌC LỖI CHI TIẾT) ---
        st.markdown("---")
        if st.button("🤖 Hỏi AI Luật sư: Tư vấn UCP 600", type="primary", icon="🤖"):
            if api_key:
                # Logic lấy context cho AI
                # Lưu ý: Cần bấm nút "SOÁT XÉT" trước để biến ai_errors có dữ liệu, 
                # hoặc ta phải tính lại logic này trong block button AI (như code dưới đây để an toàn)
                
                # --- TÍNH LẠI LOGIC NGẮN GỌN ĐỂ LẤY CONTEXT (Tránh trường hợp user chưa bấm nút Check) ---
                curr_errs = []
                # Check Date
                if ship_date > lc_exp_date: curr_errs.append("Late Shipment")
                if pres_date > lc_exp_date: curr_errs.append("L/C Expired")
                if (pres_date - ship_date).days > 21: curr_errs.append("Stale Documents (>21 days)")
                # Check Amount
                if inv_amount > (lc_amount * (1 + tolerance/100)): curr_errs.append(f"Overdrawn (Invoice {inv_amount} > Limit {lc_amount * (1 + tolerance/100)})")
                # Check Clean B/L
                if is_dirty_bl: curr_errs.append("Dirty/Unclean Bill of Lading")
                
                context = f"Danh sách lỗi chứng từ: {', '.join(curr_errs) if curr_errs else 'Không có lỗi (Clean Documents)'}"
                task = "Giải thích ngắn gọn hậu quả pháp lý của các lỗi này theo UCP 600. Nếu là 'Dirty B/L' hoặc 'Overdrawn' thì tại sao ngân hàng lại sợ rủi ro này?"
                
                with st.spinner("Luật sư đang tra cứu UCP 600..."):
                    advise = ask_gemini_advisor("Legal Expert (UCP 600)", context, task)
                    st.markdown(f'<div class="ai-box"><h4>🤖 TƯ VẤN PHÁP LÝ</h4>{advise}</div>', unsafe_allow_html=True)
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
# PHÒNG 4: INVESTMENT DEPT
# ==============================================================================
elif "4." in room:
    st.markdown('<p class="header-style">🏭 Phòng Đầu tư Quốc tế (Investment Dept)</p>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="role-card">
        <div class="role-title">👤 Vai diễn: Chuyên viên Phân tích Đầu tư (Investment Analyst)</div>
        <div class="mission-text">"Nhiệm vụ: Thẩm định dự án FDI bằng mô hình DCF, có tính đến sự trượt giá của đồng nội tệ (Currency Depreciation)."</div>
    </div>
    """, unsafe_allow_html=True)
    
    c1, c2 = st.columns(2)
    with c1:
        inv = st.number_input("Vốn đầu tư ban đầu (USD):", value=1000000)
        cf = st.number_input("Dòng tiền ròng/năm (USD):", value=400000)
        years = st.slider("Vòng đời dự án (năm):", 1, 10, 3)
    with c2:
        fx = st.number_input("Tỷ giá Spot hiện tại:", value=25000.0)
        depre = st.number_input("Mức độ mất giá VND (%/năm):", value=3.0)
        wacc = st.number_input("Chi phí vốn (WACC %):", value=12.0)
        
    if st.button("📊 LẬP BẢNG DÒNG TIỀN (CF)"):
        st.subheader("Bảng chiết khấu dòng tiền chi tiết:")
        data = []
        total_pv = 0
        
        # Năm 0
        cf0_vnd = -inv * fx
        data.append(["Năm 0", fx, f"{-inv:,.0f}", f"{cf0_vnd:,.0f}", f"{cf0_vnd:,.0f}"])
        
        # Vòng lặp tính toán
        for i in range(1, years + 1):
            fx_future = fx * ((1 + depre/100) ** i) # Tỷ giá tương lai
            cf_vnd = cf * fx_future                 # Quy đổi ra VND
            pv = cf_vnd / ((1 + wacc/100) ** i)     # Chiết khấu về hiện tại
            total_pv += pv
            data.append([f"Năm {i}", f"{fx_future:,.0f}", f"{cf:,.0f}", f"{cf_vnd:,.0f}", f"{pv:,.0f}"])
            
        npv = total_pv + cf0_vnd
        
        df_cf = pd.DataFrame(data, columns=["Năm", "Tỷ giá (Dự báo)", "CF (USD)", "CF Quy đổi (VND)", "PV (Hiện giá)"])
        st.table(df_cf)
        
        st.markdown(f"### 🏁 KẾT QUẢ NPV: {npv:,.0f} VND")
        
        with st.expander("🎓 GIẢI THÍCH MÔ HÌNH NPV QUỐC TẾ"):
            st.latex(r"NPV = CF_0 + \sum_{t=1}^{n} \frac{CF_{USD, t} \times S_t}{(1 + WACC)^t}")
            st.write("""
            Khác với NPV thông thường, dự án quốc tế chịu tác động kép:
            1.  **Dòng tiền kinh doanh:** (CF USD)
            2.  **Rủi ro tỷ giá:** ($S_t$) - Nếu VND mất giá, doanh thu quy đổi sẽ tăng (lợi cho xuất khẩu/đầu tư mang ngoại tệ về), nhưng chi phí vốn cũng thay đổi.
            """)

    # --- BỔ SUNG AI CHO PHÒNG 4 ---
    st.markdown("---")
    # Dùng tham số icon="🤖"
    if st.button("Hỏi AI Chuyên viên: Phân tích dự án", type="primary", icon="🤖"):
        if api_key:
            context = f"Vốn: {inv}$. Dòng tiền: {cf}$/năm. Mất giá nội tệ: {depre}%/năm. WACC: {wacc}%."
            task = "Phân tích SWOT nhanh về dự án này. Ngoài tài chính, nhà đầu tư cần lo ngại gì về vĩ mô (Lạm phát, chính trị, chuyển lợi nhuận về nước)?"
            
            with st.spinner("Chuyên gia đang đánh giá môi trường đầu tư..."):
                advise = ask_gemini_advisor("Investment Strategist", context, task)
                st.markdown(f'<div class="ai-box"><h4>🤖 PHÂN TÍCH CHIẾN LƯỢC ĐẦU TƯ</h4>{advise}</div>', unsafe_allow_html=True)
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
        <div class="mission-text">"Nhiệm vụ: Phân tích 'Tác động kép' của tỷ giá: (1) Đo lường gánh nặng Nợ công quốc gia (Currency Mismatch) và (2) Đánh giá rủi ro dòng tiền nóng tháo chạy (Carry Trade Unwind)."</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Tạo 2 Tab: Nợ công & Đầu cơ (Carry Trade)
    tab_debt, tab_carry = st.tabs(["📉 Gánh nặng Nợ công", "💸 Chiến lược Carry Trade"])

    # --- TAB 1: QUẢN LÝ NỢ CÔNG (IMPROVED) ---
    with tab_debt:
        st.subheader("1. Mô phỏng Cú sốc Tỷ giá lên Nợ công")
        
        col_macro1, col_macro2 = st.columns(2)
        with col_macro1:
            debt_val = st.number_input("Tổng nợ nước ngoài (Tỷ USD):", value=50.0, step=1.0)
            base_rate = st.number_input("Tỷ giá hiện tại (VND/USD):", value=25000.0, step=100.0)
        
        with col_macro2:
            st.markdown("#### Kịch bản Tỷ giá")
            shock_pct = st.slider("Đồng nội tệ mất giá bao nhiêu %?", min_value=0.0, max_value=50.0, value=10.0, step=0.5)
            
        # Tính toán
        new_rate = base_rate * (1 + shock_pct/100)
        base_debt_vnd = debt_val * base_rate # Tỷ VND
        new_debt_vnd = debt_val * new_rate   # Tỷ VND
        loss_vnd = new_debt_vnd - base_debt_vnd
        
        st.markdown("---")
        
        # Hiển thị kết quả Metric
        m1, m2, m3 = st.columns(3)
        m1.metric("Tỷ giá sau cú sốc", f"{new_rate:,.0f} VND", f"-{shock_pct}% (Mất giá)", delta_color="inverse")
        m2.metric("Quy mô nợ (Quy đổi)", f"{new_debt_vnd:,.0f} Tỷ VND")
        m3.metric("Gánh nặng tăng thêm", f"{loss_vnd:,.0f} Tỷ VND", delta="RỦI RO TÀI KHÓA", delta_color="inverse")

        # Giải thích động (Dynamic Logic)
        if shock_pct > 20:
            st.warning(f"⚠️ **CẢNH BÁO KHỦNG HOẢNG:** Mức mất giá **{shock_pct}%** là cực kỳ nghiêm trọng. Gánh nặng nợ tăng thêm **{loss_vnd/1000:,.1f} nghìn tỷ VND** có thể gây vỡ nợ quốc gia (Sovereign Default) hoặc buộc chính phủ phải thắt lưng buộc bụng.")
        elif shock_pct > 0:
            st.info(f"💡 **Phân tích:** Đồng tiền mất giá làm tăng giá trị nghĩa vụ nợ. Chính phủ cần trích thêm **{loss_vnd:,.0f} tỷ VND** từ ngân sách chỉ để trả phần chênh lệch tỷ giá này.")
        else:
            st.success("✅ Tỷ giá ổn định, không phát sinh gánh nặng nợ thêm.")

        # Context cho AI (Tab 1)
        macro_context = f"""
        Tình huống: Quốc gia có {debt_val} tỷ USD nợ nước ngoài.
        Tỷ giá mất giá: {shock_pct}%.
        Thiệt hại tài chính: Tăng thêm {loss_vnd:,.0f} tỷ VND nợ quy đổi.
        """

    # --- TAB 2: CARRY TRADE (MỚI HOÀN TOÀN) ---
    with tab_carry:
        st.subheader("2. Đầu cơ Chênh lệch lãi suất (Carry Trade)")
        st.caption("Nguyên lý: Vay đồng tiền lãi suất thấp (Funding Currency) -> Đầu tư vào đồng tiền lãi suất cao (Target Currency).")
        
        c1, c2 = st.columns(2)
        with c1:
            capital = st.number_input("Vốn đầu tư (Triệu USD):", value=10.0, step=1.0)
            rate_borrow = st.number_input("Lãi suất đồng tiền đi vay (VD: JPY):", value=0.5, step=0.1, format="%.1f")
            st.caption("Ví dụ: Yên Nhật (JPY) thường có lãi suất thấp.")
            
        with c2:
            rate_invest = st.number_input("Lãi suất đồng tiền đầu tư (VD: USD/VND):", value=5.5, step=0.1, format="%.1f")
            fx_move = st.slider("Biến động tỷ giá đồng tiền đầu tư (%):", min_value=-10.0, max_value=10.0, value=-2.0, step=0.5)
            st.caption("Dương (+) = Tăng giá (Lời thêm) | Âm (-) = Giảm giá (Lỗ tỷ giá).")

        st.markdown("---")
        
        # Tính toán Carry Trade
        # 1. Lời từ chênh lệch lãi suất (Interest Differential)
        interest_diff_pct = rate_invest - rate_borrow
        interest_profit = capital * (interest_diff_pct / 100)
        
        # 2. Lời/Lỗ từ tỷ giá (FX Gain/Loss)
        fx_profit = capital * (fx_move / 100)
        
        # 3. Tổng kết
        total_pnl = interest_profit + fx_profit
        total_roi = (total_pnl / capital) * 100
        
        # Hiển thị
        col_res1, col_res2, col_res3 = st.columns(3)
        col_res1.metric("1. Lợi nhuận từ Lãi suất", f"{interest_profit:+,.2f} M$", f"Spread: {interest_diff_pct:.1f}%")
        col_res2.metric("2. Lợi nhuận từ Tỷ giá", f"{fx_profit:+,.2f} M$", f"FX Change: {fx_move}%")
        col_res3.metric("3. TỔNG LÃI/LỖ THỰC TẾ", f"{total_pnl:+,.2f} M$", f"ROI: {total_roi:.2f}%", delta_color="normal")

        # Logic giải thích động Carry Trade
        carry_msg = ""
        if total_pnl > 0:
            if fx_move < 0:
                carry_msg = f"😅 **HÚ VÍA:** Bạn bị lỗ tỷ giá ({fx_move}%), nhưng nhờ chênh lệch lãi suất cao ({interest_diff_pct:.1f}%) nên tổng thể vẫn **CÓ LÃI**. Đây là 'ăn ít đi để an toàn'."
            else:
                carry_msg = "🚀 **THẮNG LỚN (Double Win):** Bạn ăn trọn cả 'chênh lệch lãi suất' lẫn 'đồng tiền lên giá'. Kịch bản trong mơ của mọi quỹ đầu cơ!"
        elif total_pnl < 0:
            if interest_diff_pct > 0:
                carry_msg = f"💀 **CARRY TRADE UNWIND:** Dù lãi suất đầu tư cao hơn vay ({interest_diff_pct:.1f}%), nhưng đồng tiền đầu tư rớt giá quá mạnh ({fx_move}%) đã **THỔI BAY** toàn bộ lợi nhuận. Đây là rủi ro 'lượm bạc cắc, mất tiền cọc'."
            else:
                carry_msg = "📉 **Quyết định sai lầm:** Vay lãi cao đầu tư lãi thấp, lại còn lỗ tỷ giá. Thua lỗ kép."
        
        st.info(carry_msg)
        
        # Context cho AI (Tab 2)
        carry_context = f"""
        Chiến lược Carry Trade:
        - Vốn: {capital} triệu USD.
        - Chênh lệch lãi suất (Interest Spread): {interest_diff_pct:.1f}% (Lợi thế).
        - Biến động tỷ giá (FX Move): {fx_move}% (Tác động).
        - Kết quả cuối cùng: {'LÃI' if total_pnl > 0 else 'LỖ'} {total_pnl:.2f} triệu USD.
        """

    # --- NÚT HỎI AI CHUNG CHO CẢ PHÒNG ---
    st.markdown("---")
    if st.button("Hỏi AI Chuyên gia: Phân tích Rủi ro & Cơ hội", type="primary", icon="🤖"):
        if api_key:
            # Xác định user đang xem tab nào để gửi context đó (đơn giản hóa thì gửi cả 2 hoặc cái nào đang active)
            # Ở đây ta gửi context kết hợp
            full_context = f"""
            TÔI ĐANG CÓ 2 KỊCH BẢN VĨ MÔ:
            
            KỊCH BẢN 1 (NỢ CÔNG):
            {macro_context}
            
            KỊCH BẢN 2 (CARRY TRADE STRATEGY):
            {carry_context}
            """
            
            task = "Với vai trò Giám đốc Chiến lược (Macro Strategist), hãy phân tích rủi ro của từng kịch bản. Với Carry Trade, hãy giải thích tại sao 'Lượm bạc cắc (lãi suất) có thể mất tiền cọc (tỷ giá)'?"
            
            with st.spinner("Đang phân tích dữ liệu vĩ mô..."):
                analysis = ask_gemini_advisor("Macro Strategist", full_context, task)
                st.markdown(f'<div class="ai-box"><h4>🤖 PHÂN TÍCH CHIẾN LƯỢC</h4>{analysis}</div>', unsafe_allow_html=True)
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


