Tuyệt vời! Để sinh viên có thể truy cập bằng điện thoại (Mobile) mọi lúc mọi nơi, cách nhanh nhất, miễn phí và ổn định nhất là sử dụng **Streamlit Community Cloud**.

Đây là nền tảng "chính chủ" của Streamlit, cho phép bạn đưa web lên mạng chỉ trong 5 phút.

Dưới đây là quy trình từng bước:

### Bước 1: Chuẩn bị file `requirements.txt`

Server trên mạng cần biết app của bạn dùng thư viện gì để cài đặt. Bạn cần tạo một file tên là `requirements.txt` nằm cùng thư mục với file `app.py`.

Nội dung file `requirements.txt` chỉ cần 3 dòng này:

```text
streamlit
pandas
numpy

```

*(Lưu ý: Không cần cài đặt gì thêm, chỉ cần tạo file text này là được).*

### Bước 2: Đẩy code lên GitHub

Streamlit Cloud lấy code từ GitHub. Nếu bạn chưa có tài khoản GitHub, hãy tạo một cái (miễn phí).

1. Đăng nhập **GitHub**.
2. Bấm dấu **+** (góc trên bên phải) -> chọn **New repository**.
3. Đặt tên kho (ví dụ: `BDU-Finance-Lab`). Chọn **Public**.
4. Bấm **Create repository**.
5. Tại màn hình tiếp theo, chọn dòng **"uploading an existing file"**.
6. Kéo thả 2 file của bạn vào:
* `app.py` (File code chính)
* `requirements.txt` (File thư viện vừa tạo ở Bước 1)


7. Bấm **Commit changes** để lưu.

### Bước 3: Triển khai (Deploy) lên Streamlit Cloud

1. Truy cập: [share.streamlit.io](https://share.streamlit.io/)
2. Bấm **Sign in with GitHub** (Đăng nhập bằng tài khoản GitHub vừa tạo).
3. Bấm nút **"New app"** (hoặc "Deploy an app").
4. Điền thông tin:
* **Repository:** Chọn tên kho bạn vừa tạo (`BDU-Finance-Lab`).
* **Branch:** Thường là `main`.
* **Main file path:** `app.py`.


5. Bấm nút **Deploy!**

### 🎈 Kết quả

* Màn hình sẽ hiện ra lò nướng bánh (Baking...) chạy khoảng 1-2 phút.
* Sau khi xong, nó sẽ cấp cho bạn một đường link kiểu: `https://bdu-finance-lab.streamlit.app`.
* **Gửi link này cho sinh viên.** Họ bấm vào bằng điện thoại là dùng được ngay (giao diện sẽ tự động co giãn vừa màn hình điện thoại).

---

### 💡 Một số lưu ý khi dùng trên Mobile:

1. **Chế độ ngủ (Sleep Mode):** Vì là gói miễn phí, nếu sau khoảng 3-7 ngày không ai vào, app sẽ "ngủ" để tiết kiệm tài nguyên.
* *Khắc phục:* Khi sinh viên bấm vào link thấy nó đang ngủ, chỉ cần bấm nút **"Yes, wake it up"**, đợi khoảng 30 giây là nó chạy lại bình thường.


2. **Giao diện Mobile:**
* Streamlit tự động chuyển Sidebar thành cái **nút Menu (🍔)** ở góc trên bên trái trên điện thoại. Bạn nên dặn sinh viên bấm vào đó để chọn phòng ban.
* Các bảng tính (`st.table` hoặc `st.dataframe`) trên điện thoại có thể hơi nhỏ. Sinh viên có thể cần xoay ngang điện thoại để xem bảng rõ hơn.


3. **QR Code:** Để chuyên nghiệp hơn trên giảng đường, bạn có thể copy cái link Streamlit đó, vào trang tạo mã QR (như `qr-code-generator.com`), tạo một mã QR to đùng rồi chiếu lên slide. Sinh viên chỉ cần giơ máy ảnh lên quét là vào thực hành ngay.

Chúc bạn triển khai thành công cho lớp học! 🎓
