# Thực nghiệm fuzzing C cho tồn kho badminton

## Trạng thái cập nhật ngày 15/10/2026

Phần này thay thế các nhận định về trạng thái hiện tại trong phần lịch sử bên dưới.
Chưa sửa báo cáo PDF ở bước 7. Không sửa mã frontend, backend hoặc cấu hình web.

| Bước | Trạng thái | Bằng chứng |
|---|---|---|
| 1. Chốt nghiệp vụ | PASS trong phạm vi mô hình | SHA-256 hai service khớp mốc trong stock_spec.json |
| 2. Đặc tả có thể thực thi | PASS | JSON chứa quy tắc reserve/settle, 6 liên kết yêu cầu–test case và dữ liệu 10 sheet Excel |
| 3. Sinh C từ đặc tả | PASS | 9 kiểm tra bộ sinh; đổi giới hạn trong JSON thực sự đổi hành vi C; 25/25 ca hồi quy C |
| 4. Fuzz mã sinh | PASS theo ngân sách | Chiến dịch 20261015-124739-faca951a: 3.000 lượt, không bất thường; 62/63 dòng, 79/104 nhánh |
| 5. Kiểm thử backend thật, tách biệt | PASS theo các ca đã chạy | api-fuzz_stock_0aa67d3960ad: 90 ca đối chiếu HTTP–C–DB và 8 ca validation/xác thực, JaCoCo XML/HTML |
| 6. Excel và nghiệm thu ứng dụng | Excel PASS, GUI chưa xác nhận lại | File lưu khớp toàn bộ 10 sheet JSON; công cụ chụp cửa sổ ứng dụng lỗi timeout hai lần |

PASS không đồng nghĩa phủ 100%, kiểm tra toàn bộ website hoặc không còn lỗ hổng.
Chưa thể kết luận hoàn thành toàn bộ bước 6 khi chưa chạy lại pipeline GUI với Excel hiện tại.

### Các file và vai trò hiện tại

- `stock_spec.json`: nguồn đặc tả chung, chứa quy tắc có thể sinh mã và bảng dữ liệu Excel.
- `generate_simulator.py`: dịch quy tắc reserve/settle thành C. Không sao chép hai hàm
  nghiệp vụ viết tay. Adapter đọc 28 byte, điều phối action, xuất JSON và kiểm tra
  bất biến vẫn được tái sử dụng từ `stock_simulator.c`; không tuyên bố mọi dòng
  giao tiếp C đều được tổng hợp từ đặc tả.
- `stock_simulator.c`: giữ nguyên mẫu cũ để lấy adapter; không còn là target được
  runner trực tiếp biên dịch. Target hiện tại là C được sinh trong thư mục chiến dịch.
- `test_generator.py`: kiểm tra bộ sinh, hash backend, truy vết và ca hồi quy C.
- `fuzz_runner.py`: tự sinh C trước khi biên dịch; fuzz black-box và coverage-guided
  bằng GCC/gcov. Không gọi HTTP hoặc database.
- `api_fuzz.py`: khởi chạy backend thử ở `127.0.0.1:18080`, database mới có tiền tố
  `fuzz_stock_`, gửi HTTP thật và đối chiếu C cùng tồn tổng/biến thể trong DB.
- `badminton_spec.xlsx`: đầu vào của Spec Verification Lab, không phải báo cáo lỗi
  tự sinh sau mỗi lượt fuzz. Chỉ thay mô tả liên quan tới quy trình mới; cấu trúc
  10 sheet, mô hình và hai hàm arithmetic của ứng dụng được giữ nguyên.

### Chạy lại

Chạy từ `C:\Project\Web_badminton`, cần Python 3, GCC/gcov portable hiện có.
API runner dùng Java 17, Maven, mysql CLI và các JAR đã có trên máy; đường dẫn
công cụ được khai báo rõ trong file, không thay PATH hệ thống.

```powershell
python -B software_security_fuzz/test_generator.py
python -B software_security_fuzz/fuzz_runner.py --iterations 500 --seconds 60 --seeds 1 7 42
```

Sau khi chiến dịch C đạt, dùng đúng binary trong thư mục `regression` của chiến dịch:

```powershell
python -B software_security_fuzz/api_fuzz.py --run-isolated --simulator C:/Project/Web_badminton/backend/target/software-security-fuzz/20261015-124739-faca951a/regression/stock_simulator.exe --iterations 20
```

API runner từ chối nếu hash backend không còn khớp đặc tả, binary thuộc đặc tả cũ,
hoặc cổng 18080 đang bận. Không tự chuyển sang server web hiện tại. Mỗi lần chạy
tạo một database thử mới, không xóa database sau test. Chỉ dùng đơn COD và dữ liệu
giả lập. URL provider bị trỏ về loopback, không sử dụng PayOS thật.

Backend thử được biên dịch bằng javac với `-parameters` vào thư mục kết quả riêng,
dùng dependency từ JAR đã build. Không dùng các `.class` cũ của IDE. Những lần thử
ban đầu gặp bytecode cũ và thiếu tên tham số của bản build thử được giữ nguyên;
không phân loại các lỗi môi trường này thành lỗ hổng sản phẩm.

### Bằng chứng mới và giới hạn

Tất cả đường dẫn kết quả sau nằm dưới
`C:\Project\Web_badminton\backend\target\software-security-fuzz\`:

- `20261015-124739-faca951a`: chiến dịch đủ 500 lượt/chế độ/seed, tổng 3.000 lượt.
- `20261015-124958-507184fc`: kiểm tra thêm với runner hiện tại, 2.861 lượt; một
  chiến dịch dừng ở 361 lượt do chạm ngân sách 60 giây, không phải timeout của
  tiến trình mục tiêu. C sinh ra của hai chiến dịch có cùng SHA-256
  `a939d50d027da0a421272b0ca46374d25239cd5653e26f715d282fbf425e9362`.
  Snapshot đặc tả, bộ sinh và adapter tái sinh đúng cùng nội dung C; hash runner
  khớp. Không dùng lượt kiểm tra này để tuyên bố đủ 3.000 lượt hoặc so thời gian
  trong điều kiện tải máy giống nhau.
- `api-fuzz_stock_0aa67d3960ad/summary.json`: 90 ca API PASS, 8 ca validation PASS,
  thông tin fixture, hash binary/backend và coverage hai service.
- `api-fuzz_stock_0aa67d3960ad/coverage-html/index.html`, `coverage.xml`, `api.exec`:
  JaCoCo từ chính backend thử được gọi qua HTTP.

Coverage Java theo toàn lớp, không chỉ hàm tồn kho:

| Lớp | Dòng đã chạy / tổng | Nhánh đã chạy / tổng |
|---|---|---|
| OrderService | 211/296 | 84/204 |
| ProductVariantService | 25/183 | 22/234 |

API fuzz là sinh đầu vào theo biên và seed với đối chiếu trạng thái, không phải
fuzzer HTTP có cơ chế dùng coverage để dẫn hướng. White-box coverage-guided nằm
ở chiến dịch C. JaCoCo đo độ phủ API, không tự biến API runner thành white-box.
Fixture INT_MAX được chèn trực tiếp vào database thử, không khẳng định người
dùng đạt được trạng thái đó qua API quản trị hợp lệ. Chưa kiểm tra tranh chấp
đồng thời, nhiều biến thể, thanh toán PayOS, voucher, giá và giao diện web.

Không ghi nhận bất thường mới trong các chiến dịch đạt. Hai cảnh báo CWE-190
của GUI trước đây là phép cộng arithmetic thiếu guard, không phải lỗi backend
đã tái hiện. Không có CVE được xác nhận cho dự án. Không thêm lỗi giả để có kết quả.

Các database thử đã tạo và giữ lại: `fuzz_stock_31b6aac5c57b`,
`fuzz_stock_2e694d6b2a34`, `fuzz_stock_4fd0f69be049`, `fuzz_stock_0aa67d3960ad`.
Hai database đầu thuộc lượt chưa đạt; database thứ ba đạt nghiệp vụ nhưng runner
cũ lỗi mã hóa khi in kết thúc; database cuối thuộc lượt chạy kết thúc thành công.

### Việc còn lại để chốt bước 6

Trong Spec Verification Lab, chọn **Nạp từ file Excel khác**, mở
`C:\Project\Web_badminton\software_security_fuzz\badminton_spec.xlsx`, rồi chọn
**Chạy TOÀN BỘ Pipeline**. Kiểm tra nạp đúng `badminton_stock`, 6 test case và
không có lỗi đọc đặc tả. Giữ lại nội dung kết quả để đối chiếu trước khi ghi PASS.
GUI vẫn chỉ sinh hai hàm arithmetic và có thể để trống fuzz Chương 4 vì không có
target Python; không đánh đồng phần đó với chiến dịch C đã chạy bên ngoài.
Lần này công cụ Windows trả `FrameArrived timed out` và `window capture timed out`;
cây truy cập chỉ có pane không nhãn, nên không tiếp tục bấm theo tọa độ suy đoán.

## Lịch sử trước khi bổ sung bộ sinh và kiểm thử API

Nội dung dưới đây mô tả thực nghiệm cũ, không thay thế trạng thái cập nhật ở trên.

### Phạm vi và trạng thái cũ

Mục tiêu là `stock_simulator.c`, runner là `fuzz_runner.py`. Không chạy frontend,
Spring Boot, MySQL hay PayOS. Bộ này không sửa mã nghiệp vụ web.

Đã chạy C thực tế với GCC/gcov 16.2.0 portable: 25/25 ca hồi quy và 3.000 lượt
fuzz đầu vào có cấu trúc, không ghi nhận crash/timeout/lệch oracle. Kết quả chi tiết
ở cuối tài liệu. Phong đã nạp Excel và cung cấp kết quả GUI chạy thành công;
phạm vi nghiệm thu được ghi ở mục Excel bên dưới. Không coi kết quả
simulator là bằng chứng website không còn lỗ hổng.

Nguồn nghiệp vụ: `backend/src/main/java/com/sports/service/OrderService.java`
(validateRequestedItems, validateProductForOrder, reserveItems, settleReservedStock)
và `ProductVariantService.java` (reserve, settle, refreshTotals), đọc ngày 15/10/2026.
Mỗi lần chạy thành công runner lưu SHA-256 của cả hai file trong metadata.json.
Nếu backend thay đổi, phải đối chiếu simulator trước khi dùng số liệu.

Mốc nguồn khi viết mô hình:

- OrderService.java SHA-256: `7c40dc928498fcd79af6bb278f8ce4a0f4b759f1efe76b3af94a99ef9caea53d`.
- ProductVariantService.java SHA-256: `d19b7c8e5271a2cc005df62b172a773ddeb8655935cd0ff88a1e1c5a0648f6d7`.

Mô phỏng một dòng hàng, một sản phẩm và tùy chọn một biến thể; miền kho ban đầu
không âm, nếu có biến thể thì kho tổng bằng kho biến thể. Số lượng 1–100,
thiếu kho bị từ chối, tăng giữ chỗ có kiểm tra int32, hoàn/tất toán một lần.
Rollback được mô hình hóa bằng phục hồi trạng thái khi bị từ chối; đây không
phải bằng chứng kiểm thử transaction Java. Không mô phỏng nhiều dòng hàng,
admin điều chỉnh kho giữa chừng, tổng nhiều SKU, tranh chấp khóa, HTTP, giá,
voucher, điểm thưởng, chủ sở hữu, hạn thanh toán hoặc gateway.

## Cách chạy khi có GCC/gcov đầy đủ

Python 3.10+ dùng thư viện chuẩn; GCC/gcov phải cùng bộ phiên bản.
Runner tự tìm bộ portable tại `backend/target/software-security-fuzz/toolchain/mingw64/bin`.
Đã tải từ release WinLibs chính thức, đối chiếu SHA-256; thông tin nguồn và hash
nằm trong `toolchain/download-info.txt`. Không đổi PATH hệ thống.
Từ `C:\Project\Web_badminton`:

```powershell
python software_security_fuzz/fuzz_runner.py --iterations 500 --seconds 60 --seeds 1 7 42
```

Nếu compiler không có trên PATH, truyền đường dẫn tuyệt đối qua `--gcc` và
`--gcov`. Không thêm PATH hệ thống tự động. Runner kiểm tra công cụ trước chạy;
thiếu công cụ hoặc lỗi biên dịch trả mã 2, không ghi nhận là không tìm thấy lỗi.

Mỗi lượt tạo thư mục riêng bên trong `backend/target/software-security-fuzz`;
không xóa hoặc ghi đè chiến dịch trước. Kết quả gồm compile.log, metadata.json,
regression.json, events.csv từng seed/chế độ, summary.json và summary.csv.
Mỗi lần thử lưu input có tên riêng để tránh ghi đè file đang bị khóa; giữ các
đầu vào này làm bằng chứng, không xóa tự động.
CSV mở bằng Excel để đọc kết quả; không nạp CSV kết quả vào Spec Verification Lab.

## Phương pháp thực nghiệm

Tùy chỉnh nguyên lý từ ATPM `python/atpm/ch4_dynamic_analysis/fuzzing.py` của thầy:
black-box cấp byte ngẫu nhiên; coverage-guided giữ mutant làm tăng coverage.
Đây là runner viết lại cho simulator, không phải bản chép nguyên công cụ thầy.
Coverage-guided là white-box theo cách đơn giản hóa trong module của thầy,
không phải symbolic/concolic và không giải HMAC/checksum của PayOS.

Hai chế độ có cùng target C, miền đầu vào, seed RNG, ngân sách số lượt
và thời gian. Black-box không dùng phản hồi để chọn dữ liệu. Coverage được thu
ở cả hai để đo lường nhưng chỉ chế độ guided dùng nó để giữ corpus. Corpus đầu
guided là fixture rỗng (header hợp lệ, kho/số lượng/action bằng 0) trong chế độ
structured; trong chế độ raw là 28 byte 0. Không đưa ca hồi quy/đầu vào mục tiêu vào corpus.
Mặc định `--input-mode structured`: biết định dạng envelope; hai chế độ cùng
dùng tập giá trị biên [0,1,2,99,100,101,INT_MAX-100,INT_MAX-1,INT_MAX] và action
0–15. Black-box chọn lại toàn bộ a/r/q/action độc lập mỗi lượt, không dùng
coverage để chọn mẫu. Guided chọn một mẫu corpus và thay một trường; chỉ giữ
khi coverage tăng. Cả hai giữ kho sản phẩm/biến thể bằng nhau cho fixture một
biến thể. Đây là miền thử có chủ đích, không đại diện mọi số int32 hay dữ liệu web.

`--input-mode raw` dùng byte ngẫu nhiên hoặc mutation một byte để thử parser;
không gộp số liệu raw với structured. Chưa chạy chiến dịch raw trong bảng dưới.
Mỗi seed/chế độ biên dịch riêng, không chia sẻ gcda; seed không đảm bảo hai thuật
toán sinh cùng dãy dữ liệu. Báo cáo cả lượt thực tế và thời gian vì có thể dừng
sớm do ngân sách. Không tìm được mục tiêu được ghi `first_target=null`, không
gán thành 0 lần hay suy ra thuật toán không thể tìm được.

Envelope BDMN là định dạng test **tự thiết kế**, không phải payload API thật:
4 byte BDMN, 5 số int32 little-endian (available, reserved, variant available,
variant reserved, quantity), rồi uint32 action. Bits 0–1: 0 giữ, 1 hoàn,
2/3 tất toán; bit 2: gửi lại thao tác; bit 3: có biến thể. Prefix được kiểm tra
từng byte để có nhánh parser cho thực nghiệm. Mục tiêu chung là đạt được một
lần giữ rồi hoàn thành công (state=2), không phải lỗi cài bí mật.
Với structured, header đã hợp lệ ở cả hai chế độ; không dùng việc vượt magic
header để tuyên bố guided tốt hơn. Với raw, khác biệt có thể chủ yếu đến từ parser.

Oracle Python tính với số nguyên không giới hạn và so kết quả C. Từ chối hợp lệ
không tính là crash. Timeout, lỗi bất biến, lệch oracle và crash được tách riêng;
returncode Windows ngoại lệ được nhận diện. Bất thường dừng chiến dịch và lưu
đầu vào để tái hiện; lỗi môi trường dừng với mã 2. Chưa sử dụng sanitizer.
Độ phủ dòng/nhánh là của **simulator C**, không phải coverage Java hoặc cả web.
gcov tích lũy trong mỗi chiến dịch; nhánh mới làm tăng tổng được dùng chọn corpus.

Để replay, chạy binary trong thư mục chiến dịch với đường dẫn đầy đủ tới file
`*-<iteration>.bin` hoặc `target-input.bin`; capture stdout/stderr và exit code.
Đối chiếu với Oracle và backend trước khi kết luận lỗi web.

## Excel và ứng dụng của thầy

Nạp `badminton_spec.xlsx` bằng nút **Nạp từ file Excel khác**, rồi chạy pipeline.
Có đúng 10 sheet và tên cột của mẫu; không thêm sheet kết quả vào đặc tả.
Mô hình là trừu tượng tuần tự. Nhánh `reserved -> reserved` thể hiện việc chưa
nhận thao tác cuối, nên không tuyên bố mọi đường đi luôn kết thúc. CTL kiểm tra
an toàn trạng thái và khả đạt; không chứng minh đồng thời database.

HamSinhMa chỉ khai báo C arithmetic cho hai biểu thức cộng. Mã ứng dụng sinh
không phải toàn bộ stock_simulator.c và không chứa các guard của backend.
Kết quả GUI do Phong cung cấp xác nhận Chương 1/3 có kết quả; không có target
Python nên Chương 4 trống, không có thực nghiệm fuzz trong GUI ở lượt này.
Không đổi `NgonNgu=c` cho `magic_value` để giả vờ ứng dụng hỗ trợ fuzz C.

DieuKien và BieuThucTran được ứng dụng giải độc lập: phản ví dụ int32 tự do
không chứng minh backend có lỗi với q=1–100. TestCase được liệt kê chứ không
tự động chạy; các ca thực thi nằm trong hồi quy runner. Các chỉ tiêu NFR là
cấu hình thử, không phải số đo hiệu năng website.

Đặc tả này chưa đạt checklist mở rộng trong PDF mới (5 dòng mọi sheet,
4 lỗi bộ nhớ C và 2 target Python, cụm khóa cố ý sai). Không bịa lỗi hoặc thêm
chức năng không có trong web để đạt số dòng. Cần thống nhất với thầy nếu checklist
đó bắt buộc cho nhóm; phạm vi thuần C đã chốt xung đột với các target Python
được yêu cầu trong checklist. Giữ rõ giới hạn này trong báo cáo.

## CWE/CVE và báo cáo

REQ-3 và phép cộng hoàn kho liên quan nhóm nguy cơ CWE-190; hành vi lặp liên quan
quy tắc nghiệp vụ. Chỉ ghi lỗ hổng phát hiện khi có đầu vào, kết quả tái hiện và
nguyên nhân xác minh. SAT của biểu thức cộng trần không chứng minh code Java
đã bỏ kiểm tra. Không cài memory-leak/double-free rồi nhận là lỗi web.
Không gán CVE cho badminton; CVE ứng dụng minh họa là tham khảo sản phẩm khác.

Báo cáo cuối cần bảng từng seed, số lượt/thời gian tới cùng mục tiêu (hoặc chưa
tới trong ngân sách), line/branch hits và tổng, log lỗi/replay nếu có; kết quả
pipeline riêng; giải thích khác biệt/giới hạn; xác nhận môi trường và hash nguồn.
Chưa tìm thấy lỗi sau ngân sách hữu hạn không phải chứng minh web an toàn.

## Kết quả thực nghiệm ngày 15/10/2026

Thư mục chính: `backend/target/software-security-fuzz/20261015-031905-fefd47a5`.
Lệnh đúng như ví dụ 500 lượt/60 giây/seed; cả sáu lượt đều chạy đủ 500, không bị
cắt bởi ngân sách thời gian. GCC C11 -O0 --coverage, -Wall -Wextra -Werror đạt.
25 ca hồi quy ở thư mục regression đạt; không cộng vào 3.000 lượt fuzzer.

| Seed | Chế độ | Lượt đến mục tiêu | Giây đến mục tiêu | Tổng giây / 500 lượt |
|---|---|---:|---:|---:|
| 1 | Black-box | 13 | 0,575 | 18,964 |
| 1 | Coverage-guided | 143 | 4,940 | 18,099 |
| 7 | Black-box | 7 | 0,235 | 20,080 |
| 7 | Coverage-guided | 92 | 3,478 | 19,139 |
| 42 | Black-box | 26 | 0,886 | 17,907 |
| 42 | Coverage-guided | 142 | 4,893 | 17,371 |

Mọi lượt: 58/59 dòng (98,31%), 73/98 nhánh (74,49%). Không lấy trung bình phần
trăm để suy ra độ phủ web. Thiếu nhánh không được che bằng tỷ lệ dòng cao.
Mỗi lượt có target-input.bin; gcov annotated source và events.csv là bằng chứng
độ phủ, summary.json/CSV chứa số chưa làm tròn; runner snapshot và hash phục vụ
đối chiếu thuật toán. Có smoke run 20 lượt/seed trước đó, không cộng vào bảng này.

Black-box tìm nhánh mục tiêu nhanh hơn ở cả ba seed: chọn toàn bộ fixture từ
tập biên dễ tạo cấu hình hợp lệ hơn mutation một trường trên corpus ban đầu
toàn 0. Độ phủ cuối bằng nhau. Đây là kết quả của hai thuật toán và miền mẫu
được định nghĩa, không phải chứng minh black-box luôn tốt hơn white-box; ba seed
chưa đủ kết luận thống kê tổng quát. Tổng thời gian có cả gọi tiến trình/gcov/I/O.

Kết quả chỉ kiểm tra module trừu tượng tuần tự với dữ liệu tổng hợp. Không phát
hiện lỗi mới trong chiến dịch, nên không có CWE/CVE mới được xác nhận cho web.
Kết quả SAT trong ứng dụng là kiểm tra biểu thức cộng không có guard,
không được gộp thành phát hiện fuzz C hoặc lỗi đã khai thác ở backend.

## Nghiệm thu Excel qua kết quả GUI do Phong cung cấp

Nguồn bằng chứng là nội dung báo cáo và mã C Phong gửi trong hội thoại sau khi
nạp badminton_spec.xlsx. Không nhận đây là một lượt GUI do runner tự động chạy;
chưa lưu báo cáo PDF/DOCX xuất trực tiếp từ ứng dụng. Kết quả quan sát:

| Bước | Kết quả GUI | Ý nghĩa và giới hạn |
|---|---|---|
| Chương 1 | Không deadlock; 5/5 CTL đúng; mutual exclusion OK | Chỉ trên đồ thị trừu tượng. Nhãn violation không có trong đồ thị, nên AG(!violation) đúng một cách tầm thường; không chứng minh bất biến số lượng kho. |
| Chương 2 | Không phát hiện lỗi heuristic | Chỉ quét hai hàm cộng được sinh, không quét toàn bộ simulator hoặc backend. |
| Chương 3 | reserved_add SAT với r=2147483647,q=1; available_release SAT với a=2147483647,q=1 | Đây là giá trị thỏa điều kiện được khai báo, không phải kết quả chạy backend. |
| Kiểm tra overflow Chương 3 | SAT với r/a=1,q=2147483647 | Phép kiểm tra độc lập không áp dụng giới hạn q<=100 của DieuKien; không dùng mô hình này làm bằng chứng đầu vào mua hàng hợp lệ. |
| Chương 4 | Không có dòng kết quả fuzz | Không có target Python. Fuzz C được thực hiện riêng bằng runner, có log và số liệu ở thư mục chiến dịch. |
| Phân loại | Hai mục CWE-190, kèm CVE minh họa | Hai biểu thức nguy cơ, không phải hai lỗ hổng web được tái hiện. CVE không thuộc badminton. |
| TestCase | Liệt kê đúng 6 ca | Truy vết tài liệu; không chứng minh sáu ca được GUI chạy tự động. |

Mã ứng dụng sinh đúng hai hàm reserved_sum_expression/release_sum_expression,
đều là `int ...(int a, int b) { return a + b; }`. Không chứa logic kiểm tra q,
thiếu kho, biến thể, rollback hay thao tác lặp. Phải ghi rõ sự khác biệt này
khi trình bày chuỗi đặc tả -> sinh mã -> fuzzing.

## Truy vết yêu cầu tới thực nghiệm C

Số ca bên dưới là trường case trong regression/regression.json, không phải số
lượt fuzzer. Các ca đều thực thi simulator C và so với oracle; đây chưa phải
bộ test gọi Java để xác minh tương đương hành vi một cách tự động.

| Yêu cầu / test case Excel | Nguồn nghiệp vụ | Hàm C | Ca hồi quy và bằng chứng |
|---|---|---|---|
| REQ-1 / TC-1: số lượng 1–100 | OrderService.validateRequestedItems | reserve | 11,12,15 từ chối -1/0/101 và giữ kho không đổi; 13 chấp nhận 1 |
| REQ-2 / TC-2: không giữ khi thiếu kho | OrderService.validateProductForOrder | reserve | 17 từ chối kho 0, q=1; 16 chấp nhận kho 1, q=1 |
| REQ-3 / TC-3: tăng reserved không tràn | OrderService.validateProductForOrder; ProductVariantService.reserve | reserve | 18,20 từ chối cộng vượt INT_MAX; 19 chấp nhận sát biên |
| REQ-4 / TC-4: hoàn một lần | OrderService.cancelOrder/cancelPendingOrder | settle + state | 4 và 9 giữ 2, hoàn, gọi lại; kho khả dụng trở về 10 và reserved=0 |
| REQ-5 / TC-5: tất toán một lần | OrderService.handlePaymentSuccess/updateOrderStatus, ProductVariantService.settle | settle + state | 5 và 10 giữ 2, tất toán, gọi lại; khả dụng=8, reserved=0 |
| REQ-6 / TC-6: thiếu kho biến thể | ProductVariantService.reserve | reserve | 17 dùng fixture có biến thể nhưng bị chặn tại kiểm tra kho sản phẩm trước; chưa chứng minh nhánh kiểm tra biến thể độc lập |

Fuzz structured của cả hai chế độ bổ sung các tổ hợp biên và action; không dùng
3.000 lượt làm bằng chứng mọi nhánh đã được kiểm tra. Kho fixture có thể đạt
INT_MAX dù quy tắc tạo biến thể hiện tại giới hạn stock=1.000.000; chưa chứng
minh các fixture sát INT_MAX đạt được qua thao tác hợp lệ của người dùng.
Source Java được đọc để đối chiếu quy tắc, hash được kiểm tra giữ nguyên;
không chạy lại JUnit/backend hoặc database ở giai đoạn C này.

## Đối chiếu chuỗi thầy nhận xét và các phần còn thiếu

| Mục thầy ghi | Phần đã có | Phần còn thiếu hoặc cần xác nhận |
|---|---|---|
| Module | Giữ/hoàn/tất toán tồn kho một sản phẩm, một biến thể | Không phân tích toàn bộ đơn hàng hoặc tranh chấp đồng thời |
| Log | Log hồi quy C, events.csv, compile.log, gcov và số liệu chiến dịch | Chưa có log vận hành backend được dùng để suy ra yêu cầu; không coi log test là log nghiệp vụ có sẵn |
| Đặc tả -> req | Excel 10 sheet và bảng truy vết trên | Một số mục chỉ tài liệu hóa; chưa đạt checklist mở rộng 28 trang |
| Sinh C simulator | GUI sinh hai hàm C arithmetic; simulator C được viết thủ công từ quy tắc backend | Chưa có công cụ sinh toàn bộ simulator từ Excel; hai bộ mã khác nhau, không được gọi là một artifact tự động liên tục |
| Fuzzing | 25 ca hồi quy, 3.000 lượt, 3 seed, replay 6/6, so sánh cùng mục tiêu | Chỉ coverage-guided theo cách giản lược của toolkit; không concolic; nhánh chưa phủ còn tồn tại |
| Output CWE/CVE | GUI trả hai mục CWE-190; fuzz C chưa phát hiện lỗi mới | Chưa có lỗ hổng Java được tái hiện trong giai đoạn này, không có CVE của dự án |

Theo hướng dẫn bài tập lớn chung, đã có mô hình/kiểm chứng trong ứng dụng và
kiểm thử động C với bằng chứng định lượng trên phạm vi nhỏ. Tuy nhiên chưa
thể tự xác nhận đạt toàn bộ nhận xét riêng của thầy: cần xác nhận thầy chấp nhận
simulator viết thủ công và fuzz C chạy riêng. Nếu yêu cầu bắt buộc sinh toàn bộ
simulator từ Excel hoặc hiển thị fuzz C trong GUI, ứng dụng hiện chưa đáp ứng
luồng đó chỉ bằng việc sửa đặc tả.

Checklist mở rộng trong hướng dẫn Excel còn thiếu danh mục memory/liveness,
số dòng tối thiểu ở một số sheet, các lỗi C cài chủ đích, cụm khóa minh họa và
hai target Python. Không bổ sung các mục đó để giả thành tính năng/lỗi của web.
Cần chốt đây là yêu cầu bổ sung bắt buộc hay chỉ khuôn mẫu minh họa cho nhóm.

Nội dung có thể dùng trong báo cáo: nhóm xây mô hình trừu tượng tồn kho và
kiểm thử simulator C bằng black-box/coverage-guided; ba seed cho cùng nhánh
mục tiêu đều đạt, black-box tới mục tiêu sớm hơn, độ phủ cuối bằng nhau. Không
ghi nhận lỗi trong ngân sách thực nghiệm. Các cảnh báo CWE-190 của ứng dụng
thuộc biểu thức cộng không có guard, không xác nhận lỗ hổng backend. Phạm vi
và các khoảng trống ở bảng trên phải đi kèm kết luận.
