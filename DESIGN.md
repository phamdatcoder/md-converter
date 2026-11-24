# MD Converter — Studio A

## Thiết kế được duyệt

Người dùng chọn phương án A: cấu hình ở trái, vùng làm việc ở phải. Danh sách
tài liệu mặc định ẩn, nút hiện/ẩn giúp ưu tiên chiều rộng xem trước Markdown.
Khi mở danh sách, có thể kéo thanh chia để đổi chiều rộng. Cột cấu hình
không có thanh cuộn. Lựa chọn nguồn là radio nhỏ 32px, đệ quy là switch.
Đường dẫn nguồn trong ô một dòng có thể chọn/sao chép; đường dẫn lưu và nút
Chọn nằm cùng hàng. Gợi ý ngắn, chiều cao cố định để đường dẫn dài không làm
panel giãn. Nội dung được kiểm tra vừa cửa sổ nhỏ nhất 1000×760.

Nền kem `#F7F3EB`, giấy `#FFFEFA`, mực `#25252D`, cobalt `#3656D9`, vàng
`#FFE18B`. Viền mực, bo góc và bóng lệch nhẹ tạo chất comic. Không dark mode.
Token và component ở `desktop/studio.py`. Segoe UI có đủ dấu tiếng Việt,
dự phòng Arial/Tahoma nếu font không có; đồng bộ named font của Tk. Chuỗi nguồn
lưu UTF-8, phần xem trước chuẩn hóa Unicode NFC; không sửa Unicode file kết quả.

Icon tài liệu, ký hiệu Markdown, mũi tên và chớp vàng được vẽ bằng code trong
`tools/make_icon.py`, xuất ICO nhiều kích thước và PNG. Nhúng icon vào EXE,
cửa sổ và header; không cần phân phối ảnh rời.

Nơi lưu trống: tạo folder mới `Markdown` trong nguồn folder hoặc cạnh file đầu
tiên được chọn. Nếu đã có tên, tạo `Markdown (2)`, `(3)`… độc quyền trong worker.
Nhiều file khác thư mục: dùng thư mục file đầu tiên. Nơi lưu do người dùng chọn
giữ cơ chế tránh ghi đè. Liên kết kết quả trỏ đúng folder thực tế sau chuyển đổi.

Kiểm tra native window, ẩn/hiện danh sách, Unicode, cửa sổ nhỏ, lưu tự động và
chuyển đổi thật từ source/EXE bằng `tools/check_gui.py`, `desktop/gui_smoke.py`.
Tiếp tục kiểm tra hồi quy xung đột DLL. Ảnh kiểm tra dùng dữ liệu minh họa.

## Bản trước (đã thay bằng Studio A)

App tiện ích Windows tiếng Việt: chuyển một/nhiều file hoặc cả folder sang
Markdown, chọn nơi lưu, theo dõi phần trăm và mở folder kết quả.

Một cửa sổ: chọn nguồn và nơi lưu ở trên; nút chuyển/dừng; thanh tiến độ;
danh sách file bên trái và nội dung/chi tiết lỗi bên phải; đường dẫn kết quả
có thể bấm ở dưới. Các yêu cầu giao diện được người dùng nêu trực tiếp.

Giao diện native Tk/ttk, nền sáng flat, không dark mode. Không có dữ liệu giả.
Dùng Segoe UI có sẵn trên Windows để hỗ trợ dấu tiếng Việt, thay cho font web
Inter của skill UI. Màu nhấn xanh dương; màu và font tập trung ở `COLORS`/`FONT`
trong `desktop/gui.py`. Component native thay cho mẫu HTML/CSS của skill.

Trạng thái: chưa chọn nguồn, quét, khởi tạo, đang chuyển, thành công, có lỗi,
không có file phù hợp, đang dừng, đã dừng. Tiến độ là tỷ lệ số file đã xử lý;
không tạo phần trăm giả cho thời gian xử lý nội bộ từng tài liệu.

Luồng: chọn file/folder → chọn nơi lưu → bắt đầu → quét → chuyển từng file →
lưu Markdown → xem kết quả/bấm đường dẫn mở folder. File lỗi hiện chi tiết và
tiếp tục file sau; dừng/đóng chờ file hiện tại hoàn tất; lần chạy sau không ghi
đè kết quả cũ. Hủy hộp chọn file/folder giữ nguyên lựa chọn trước.

Kiểm tra native UI bằng cửa sổ Tk thực tế khi môi trường có Tcl/Tk hoạt động;
không dùng browser probe dành cho HTML để đánh giá cửa sổ desktop.
