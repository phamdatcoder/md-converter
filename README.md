# MD Converter — Windows desktop

Ứng dụng desktop dùng mã nguồn MarkItDown có sẵn trong `markitdown-main/`.
Mục tiêu đóng gói: **chỉ một file `dist/MD Converter.exe`**, chạy trên Windows
10/11 x64, không cần cài Python, Microsoft Office hay LibreOffice trên máy dùng.

## Chức năng

- **Theo file:** chọn một hoặc nhiều tài liệu.
- **Theo folder:** quét các tài liệu được hỗ trợ; có tùy chọn gồm thư mục con.
- Chọn folder đầu ra, hoặc để trống để tạo folder `Markdown` trong folder nguồn
  hay cạnh file đầu tiên được chọn. Nếu đã tồn tại, tạo `Markdown (2)`, `(3)`…
- Studio A: nền kem, xanh cobalt, vàng nhấn theo phong cách comic. Danh sách
  mặc định ẩn; nút **Hiện danh sách** / **Ẩn danh sách** ưu tiên vùng xem trước.
- Giữ cấu trúc thư mục con khi chuyển cả folder. Folder đầu ra nằm trong folder
  nguồn sẽ được loại khỏi việc quét; không đi theo symlink/junction.
- Thanh tiến độ và phần trăm **số file đã xử lý / tổng số file**. Ví dụ 3/10 file
  là 30%. Một file lớn có thể mất lâu ở cùng một mức phần trăm: thư viện không
  cung cấp tiến độ bên trong từng file. 100% nghĩa là mọi file đã được thử xử lý;
  số file thành công và số lỗi luôn được hiển thị riêng.
- Lỗi một file không chặn các file còn lại; chọn dòng lỗi để xem chi tiết.
- Xem nội dung Markdown đã lưu; bản xem trước giới hạn 256.000 ký tự để giữ UI
  phản hồi, còn file đầu ra chứa đầy đủ nội dung.
- Sau khi có kết quả thành công, bấm đường dẫn hoặc **Mở folder kết quả** để mở
  folder đầu ra bằng Explorer.
- Tên trùng được thêm `(2)`, `(3)`…; không ghi đè tài liệu hay kết quả có sẵn.
- Giữ màu chữ và chữ gạch bỏ trong DOCX, XLSX, PPTX và HTML có style nội tuyến.
  Chữ gạch bỏ dùng `~~…~~`; chữ có màu dùng HTML `<span style="color: #RRGGBB">`.
  Khi kết hợp, dùng `<del>` bên trong span. Trình đọc Markdown cần cho phép
  HTML/style để hiển thị màu. Bộ đọc PDF, DOC/XLS cũ và RTF chưa giữ màu/gạch bỏ.
  PPTX hỗ trợ màu run/đoạn trực tiếp; Excel đọc font ô và rich text, không tính
  màu từ conditional formatting. Chưa xử lý CSS ngoài/class của HTML.
- PDF ưu tiên trích xuất theo dòng trên trang. Các dòng văn bản liên tiếp dùng
  ngắt dòng cứng Markdown (`\` cuối dòng), để trình đọc không gộp lại thành một
  đoạn. Ô bảng có nhiều dòng dùng `<br>` và giữ nguyên cấu trúc hàng/cột. Giữ
  phát hiện form không viền và fallback của engine; thứ tự đọc PDF nhiều cột
  vẫn có thể cần kiểm tra thủ công. Đây không phải tái tạo bố cục trang in.
- **Dừng** và đóng cửa sổ khi đang chạy đều chờ file hiện tại hoàn tất trước
  khi ngừng, giữ những kết quả đã lưu.

## Định dạng

| Loại | Phần mở rộng | Ghi chú |
| --- | --- | --- |
| Word | `.docx` | Chuyển văn bản, tiêu đề, danh sách, bảng bằng MarkItDown |
| Word cũ | `.doc` | Word 97–2003 không mã hóa; trích xuất văn bản chính, không giữ style/hình ảnh. RTF mang đuôi DOC cũng được đọc |
| Excel | `.xlsx`, `.xls` | Đọc các sheet thành Markdown |
| PDF | `.pdf` | Cần có lớp chữ; chưa tích hợp OCR cho bản scan |
| PowerPoint | `.pptx` | Không hỗ trợ định dạng `.ppt` cũ |
| Trang web lưu trên máy | `.html`, `.htm`, `.xhtml` | Chuyển sang Markdown |
| Văn bản và dữ liệu | `.txt`, `.csv`, `.tsv`, `.json`, `.xml`, `.rtf` | Đầu ra UTF-8 |
| Ebook, notebook, email | `.epub`, `.ipynb`, `.msg` | Chuyển nội dung văn bản |

Không hỗ trợ file có mật khẩu, OCR ảnh, âm thanh hoặc video trong bản này.
Chuyển đổi tài liệu cục bộ không cần API key. App không chủ động tải tài liệu
lên dịch vụ AI; một số converter của thư viện gốc có thể truy cập tài nguyên
được tham chiếu trong tài liệu. Markdown ưu tiên nội dung và cấu trúc, không
tái tạo bố cục trang in. Các font mã cũ VNI/TCVN3 trong DOC chưa được chuyển mã.

## Build một EXE

Máy **build** cần Python 3.12–3.14 x64 có Tcl/Tk và Internet để tải dependency
lần đầu. Máy **chạy EXE** không cần các công cụ này.

Chạy từ PowerShell trong folder này:

```powershell
.\build.ps1
```

Nếu Python chưa nằm trong PATH, truyền đường dẫn:

```powershell
.\build.ps1 -Python 'C:\Path\To\Python\python.exe'
```

Nếu PowerShell chặn script, có thể mở một process chỉ áp dụng ExecutionPolicy
cho lần build này:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

Script tạo `.venv-build/` riêng, cài engine từ **source trong folder hiện tại**,
chạy unit test và chuyển đổi các tài liệu mẫu thật, thu thập license, build
bằng PyInstaller, rồi chạy kiểm tra chuyển đổi từ chính EXE. `dist/` chỉ được
coi là build thành công khi chứa duy nhất `MD Converter.exe` và các kiểm tra
đều đạt. Không xóa dữ liệu cũ trong `dist/` tự động; hãy chuyển file không liên
quan ra ngoài nếu script báo có file thừa.

```powershell
# Những lần build sau, khi dependency đã được cài:
.\build.ps1 -SkipInstall
```

`MDConverter.spec` đóng gói Python, Tcl/Tk, ONNX model của Magika, các thư viện
đọc tài liệu và license vào EXE. File có thể lớn; lần mở đầu sẽ giải nén các thư
viện vào thư mục tạm rồi tự dọn sau khi đóng. Đây là cơ chế one-file của
[PyInstaller](https://pyinstaller.org/en/stable/usage.html), không cần phân phối
thêm file bên cạnh EXE. EXE chưa được ký số.

Nếu EXE cũ đang chạy, Windows khóa file trong `dist/`; bản build đã kiểm tra
sẽ được lưu ở `release/MD Converter.exe`. Đóng bản cũ rồi mở bản mới này.
Script kiểm tra từng ảnh icon nhúng trong EXE khớp chính xác ICO comic gốc.

Kết quả kiểm tra lưu trong `.build-tools/source-smoke.json`,
`.build-tools/exe-smoke.json`, `.build-tools/source-gui-smoke.json` và
`.build-tools/exe-gui-smoke.json`; phiên bản dependency đã dùng được lưu ở
`.build-tools/requirements-resolved.txt`. Khi cần build lại đúng phiên bản,
dùng file phiên bản này làm constraints cho pip. Chỉ có file spec/script trong
repo không đồng nghĩa EXE đã được build hoặc kiểm tra thành công.

## Chạy từ source và kiểm thử

```powershell
.\.venv-build\Scripts\python.exe app.py
.\.venv-build\Scripts\python.exe -m unittest discover -s tests -v
.\.venv-build\Scripts\python.exe tools/check_gui.py
.\.venv-build\Scripts\python.exe app.py --self-test --fixtures markitdown-main/packages/markitdown/tests/test_files --report .build-tools/manual-smoke.json
```

Unit test của batch và parser DOC chỉ dùng thư viện chuẩn; có thể chạy khi chưa
cài MarkItDown. Smoke test cần toàn bộ dependency để kiểm tra các converter
thật. Bộ đọc DOC dựa trên [đặc tả MS-DOC của Microsoft](https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-doc/01d5d8c4-cf9c-4ef9-80fd-439e763cfe01).

`tools/check_gui.py` kiểm tra cửa sổ Tk thật với backend văn bản mô phỏng, gồm
chọn file/folder, trạng thái lỗi, tiến độ, nút mở folder, dừng và kích thước nhỏ
nhất. Ảnh kiểm tra nằm trong `.build-tools/gui-*.png`. Kiểm tra này không xác
nhận các thư viện đọc Word/Excel/PDF hoạt động; việc đó thuộc smoke test dùng
MarkItDown thật ở trên.

Build còn kiểm tra cửa sổ thật: mở và hủy hộp chọn file native, bấm Bắt đầu để
chuyển DOCX/XLSX/XLS/PDF/PPTX trong luồng nền, rồi chuyển folder có thư mục con.
Nếu máy có TortoiseGit, kiểm tra tái tạo việc shell extension nạp bản
`MSVCP140.dll` cũ. App nạp C++ runtime đi kèm EXE trước khi mở giao diện để tránh
xung đột DLL dẫn đến crash ONNX Runtime. Không cần thay đổi hay gỡ TortoiseGit.
EXE được build và kiểm tra ở `.build-tools/release/` trước khi chép vào `dist/`.

## Cấu trúc mã nguồn

- `app.py`: điểm khởi động source/EXE.
- `desktop/gui.py`: giao diện native tiếng Việt bằng Tk/ttk.
- `desktop/studio.py`: bố cục Studio A, component comic và font tiếng Việt.
- `desktop/assets/`: icon Windows và biểu tượng app; tái tạo bằng
  `python tools/make_icon.py` (cần Pillow trên máy phát triển).
- `desktop/conversion.py`: quét folder, chuyển đổi nền, tiến độ, lưu an toàn.
- `desktop/legacy_doc.py`: đọc văn bản DOC Word 97–2003.
- `desktop/smoke.py`: kiểm tra converter từ source và EXE.
- `tests/`: kiểm thử batch và DOC.
- `build.ps1`, `MDConverter.spec`: quy trình build Windows một file.
- `markitdown-main/`: giữ nguyên thư viện gốc và license MIT.
