# Changelog

Định dạng theo [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/); phiên bản theo [Semantic Versioning](https://semver.org/lang/vi/).

FoxFlow là bản fork của [FoxProfile](https://github.com/chienbm98/foxprofile) (chienbm98). Các phiên bản từ 2.3.1 trở về trước là bản phát hành của FoxProfile.

## [Unreleased]

### Thêm
- **Trigger** trong bảng Tự động hoá (app desktop và web panel): khi **webhook** được gọi, khi **copy chữ** (lọc được bằng regex), khi có **file mới trong thư mục** (lọc theo mẫu tên), hoặc **theo lịch** (mỗi N phút / giờ cố định hằng ngày), FoxFlow tự mở các profile đã chọn, chạy lần lượt các workflow rồi đóng profile do nó mở. Thông tin sự kiện đến workflow qua `{{trigger_type}}`, `{{trigger_text}}`, `{{trigger_file}}`, `{{trigger_file_name}}`, `{{trigger_time}}`. Mỗi trigger có công tắc bật/tắt, nút Chạy ngay và kết quả gần nhất; sự kiện đến dồn sẽ xếp hàng. REST `/automations`, webhook `/hooks/{id}?key=...` (không cần API token, chỉ cần key riêng), MCP `list_triggers`, `fire_trigger`; lưu ở `automations.json` (`FOXFLOW_AUTOMATIONS_FILE`).
- Workflow: **lấy text ngay lúc ghi.** Bôi đen chữ hoặc để chuột yên trên một phần tử 3 giây, một khung nhỏ trong trang hỏi có lấy text đó không (kèm tên biến gợi ý `text1`, `text2`...); đồng ý là thêm bước *Lấy chữ*. Kéo chuột để bôi đen không còn bị ghi thành click.
- Workflow: bước **Gán biến**, **Nếu / Ngược lại**, **Lặp theo danh sách** (một số N hoặc danh sách), **Lặp khi**, **Thoát vòng lặp** và **Kết thúc khối**, với điều kiện là biểu thức trên biến (`price > 100 and status == "ok"`, hàm `contains`, `len`, `matches`...) hoặc trên trang (thấy phần tử, thấy chữ, URL / tiêu đề chứa). Trình sửa thụt lề các bước trong khối, có nút chèn bước bên dưới và tự thêm Kết thúc khối.
- **Chạy nhiều workflow trong một lần**: hộp thoại chạy có **Thêm workflow**; mỗi profile chạy lần lượt các workflow trong cùng một trình duyệt, biến được dùng tiếp sang workflow sau. REST `POST /workflow-runs`, MCP `run_workflows`.
- **Bảng Tự động hoá** trên app desktop và web panel, là màn hình mở đầu: bảng **Lần chạy** (lần chạy hiện tại hoặc gần nhất của mỗi profile: bước đang chạy và vạch tiến độ, số lần thử và khởi động lại, dấu trạng thái, lý do lỗi; Dừng, Chạy lại, Log trực tiếp, Xem màn hình) và bảng **Workflow** (profile đã ghi, số bước, kết quả lần chạy gần nhất; Chạy, sửa, xoá). Thanh bên có công tắc **Tự động hoá / Profile**; nút chính đổi thành **Ghi workflow** (chọn profile rồi ghi).
- **Chạy một workflow trên nhiều profile** cùng lúc qua hộp thoại chạy (tick profile, điền biến cho lần chạy) hoặc nút **Chạy workflow** trên thanh thao tác hàng loạt của bảng profile. Profile đang ghi hoặc đang chạy workflow khác bị làm mờ kèm lý do.
- **`FOXFLOW_HTTP_PROXY`** trong `.env`: proxy cho các request ra Internet của chính FoxFlow (AI, tải engine Chrome và GeoIP, tra IP ra và Kiểm tra IP của profile không có proxy riêng). Không đặt thì đi thẳng: proxy hệ thống và `HTTP(S)_PROXY` không còn được dùng ngầm. Log khởi động cho biết đang đi đường nào, hộp thoại Cấu hình AI hiện proxy đang dùng, và lỗi mất mạng kèm hướng dẫn đặt proxy. Trình duyệt không bị ảnh hưởng.
- `GET /workflow-runs?log=false` bỏ phần log để bảng điều khiển tải nhẹ hơn; web panel tự cập nhật mỗi 1,5 giây khi có lần chạy, 4 giây khi rảnh, và chỉ tải fingerprint khi đang xem bảng profile.
- Bớt các bước "làm X trước" phải tự quay lại làm, trên cả app desktop và web panel:
  - **Ghi workflow** mở luôn profile đang tắt rồi tự bắt đầu ghi. Chưa có profile thì tạo xong là ghi ngay.
  - **Cookie & fingerprint**, **đổi tên**, **xoá** (kể cả xoá hàng loạt) một profile đang chạy: hỏi lại rồi tự dừng trình duyệt, thay vì từ chối.
  - **Nhân bản** có nút **Dừng trình duyệt** ngay trong hộp thoại để chép được dữ liệu.
  - **Chạy workflow** khi chưa có workflow nào: chuyển sang ghi workflow.
  - Workflow có bước Sinh bằng AI mà chưa có API key: mở luôn Cấu hình AI thay vì báo lỗi.
  - Hộp thoại Workflow của profile đang tắt có nút **Mở**.
- **Workflow: ghi lại và chạy lại thao tác.** Nút **Workflow** trên mỗi dòng profile (app desktop và web panel) ghi mọi click, gõ phím, chọn, bấm phím, cuộn và mở trang trong trình duyệt của profile thành các bước, mỗi phần tử kèm nhiều selector dự phòng. Mỗi bước có delay riêng (lấy từ nhịp thật lúc ghi) và tốc độ gõ (ms/ký tự); workflow có tốc độ chung (x0.25–x5). Khi chạy, mọi bước được kiểm tra kết quả (ô đã gõ đúng chữ, ô tích đã tích, click tới đúng trang như lúc ghi, hoặc chờ URL/tiêu đề/phần tử/chữ tuỳ chọn); bước lỗi được thử lại 2 lần, vẫn lỗi thì tắt trình duyệt và chạy lại từ bước 1, tối đa 3 lần (đều chỉnh được). Bản ghi chưa lưu được giữ lại kể cả khi trình duyệt đóng. Dùng được với cả engine Camoufox và Chrome.
- **Nhân bản profile**: nút sao chép trên mỗi dòng profile (app desktop và web panel), `POST /profiles/{name}/clone` và MCP `clone_profile`, một bản hoặc tối đa 50 bản một lần (tên gốc thêm -1, -2...). Bản sao giữ proxy, hệ điều hành, engine, timezone, locale và luôn có fingerprint mới; tick để chép thêm từng phần: cookie, lịch sử và bookmark, dữ liệu trang web, mật khẩu đã lưu, các tab đang mở (profile phải đang tắt) và workflow của profile (mỗi bản sao có workflow riêng).
- Hộp thoại Workflow của một profile chỉ hiện workflow của profile đó, kèm nút hiện cả workflow của profile khác. Đổi tên profile thì workflow của nó đi theo tên mới.
- Workflow: **rê chuột rồi mới click** cho menu và thanh cảm xúc chỉ hiện khi rê chuột (ví dụ "Yêu thích" trên Facebook); bản ghi tự nhận ra trường hợp này, sửa tay được ở Chi tiết của bước.
- Workflow: **biến** `{{tên}}` trong giá trị, URL và selector của bước (giá trị ban đầu trong trình sửa hoặc theo từng lần chạy, có sẵn `{{profile}}`); bước **Lấy chữ** (lọc được bằng regex) và bước **Sinh bằng AI** lưu kết quả vào biến.
- **Cấu hình AI** (tuỳ chọn, tắt cho tới khi có API key): OpenAI hoặc API tương thích (Azure OpenAI, OpenRouter, LLM chạy trên máy), có nút Thử; REST `/ai/settings`, `/ai/test`; biến môi trường `FOXPROFILE_OPENAI_*`. Prompt và chữ lấy từ trang mà prompt dùng được gửi tới dịch vụ AI đã chọn.
- REST API cho workflow: `/browser/{name}/record/*`, `/recordings`, `/workflows`, `/workflows/{name}/run`, `/workflow-runs`; MCP thêm `list_workflows`, `get_workflow`, `run_workflow`, `workflow_run_status`, `stop_workflow_run`. Workflow lưu ở `workflows/` (`FOXPROFILE_WORKFLOWS_DIR`).

### Sửa
- Windows: **Dừng** một profile giờ tắt hẳn cả trình duyệt trước khi xong. Trước đây trình duyệt còn giữ thư mục dữ liệu thêm một lúc, nên đổi tên ngay sau khi dừng báo "Update failed (name conflict?)" và xoá có thể để sót file. Đổi tên và xoá cũng chờ thêm nếu Windows còn khoá file.
- Workflow, điều khiển trang và MCP không còn hỏng (`JSONDecodeError`) trên máy có cấu hình proxy hệ thống hoặc `HTTP(S)_PROXY`: các kết nối tới `127.0.0.1` (control server của trình duyệt, API của chính FoxFlow) giờ luôn đi thẳng, không qua proxy.
- App desktop: nút "Launch" không còn bị gãy chữ thành hai dòng khi dùng giao diện English.
- Proxy dạng `host:port:user:pass` có `@` hoặc `:` trong mật khẩu không còn bị bỏ qua (trước đây profile mở mà không qua proxy). Chấp nhận proxy IPv6 dạng `[2001:db8::1]`; host proxy tối đa 253 ký tự.
- Tên profile không phân biệt hoa thường: "Demo" và "demo" không còn tạo được hai profile dùng chung một thư mục dữ liệu trên Windows/macOS. Đổi tên chỉ khác hoa thường vẫn giữ nguyên dữ liệu; tên chứa ký tự điều khiển bị từ chối.
- Đổi tên profile sang tên có thư mục dữ liệu sót lại trả về lỗi 409 thay vì làm hỏng danh sách profile. `profiles.json` được ghi nguyên tử, và các thao tác đồng thời (API, MCP, app) không còn ghi đè lẫn nhau, gây lỗi 500 hay xoá nhầm thư mục của profile vừa tạo lại.
- Proxy không vào được mạng báo lỗi dễ hiểu ("no internet connection through proxy host:port") thay vì chuỗi lỗi nội bộ; chi tiết vẫn có trong log.
- MCP `update_profile(proxy="")` xoá được proxy.
- Điều khiển trang từ chối cả scheme bị mã hoá phần trăm (`%66ile:`) và URL hỏng như `[::1`.
- Web panel: xác nhận "New fingerprint" không còn đóng luôn hộp thoại cookie; Esc đóng màn hình xem trực tiếp và đúng hộp thoại trên cùng; hiện lỗi kèm nút Thử lại khi không kết nối được server thay vì trang trắng; nút Lưu và các thao tác cookie bị khoá khi đang chạy; lỗi 422 hiển thị dễ đọc.
- App desktop: hỏi xác nhận trước khi tạo fingerprint mới; ô chọn ở tiêu đề bảng không còn bỏ chọn các profile ở trang khác; rail hiện số profile và số trình duyệt đang chạy; hộp thoại xoá nói rõ cookie và dữ liệu sẽ mất vĩnh viễn.

### Thay đổi
- **Đổi tên thành FoxFlow** và chuyển trọng tâm sang tự động hoá web; ghi nguồn FoxProfile trong README, LICENSE và `pyproject.toml`. Biến môi trường đổi sang `FOXFLOW_*`, tên cũ `FOXPROFILE_*` vẫn được đọc. MCP server đổi tên thành `foxflow` (cần thêm lại vào ứng dụng AI), `foxprofile_mcp.py` thành `foxflow_mcp.py`, `run_foxprofile.bat` thành `run_foxflow.bat`, file trong `deploy/` và log `logs/foxflow_YYYYMMDD.log` cũng đổi tên. Dữ liệu (`profiles.json`, `camoufox_data/`, `workflows/`) giữ nguyên; engine Chrome dùng lại bản đã tải của FoxProfile; web panel giữ ngôn ngữ và token đã lưu.
- Ngôn ngữ giao diện mặc định của app desktop và web panel là English; đặt `FOXPROFILE_LANG=vi` (hoặc bấm "Tiếng Việt" trong app) để dùng tiếng Việt.

## [2.3.1] - 2026-10-09

### Sửa
- Web panel: bảng profile không còn tràn mất cột thao tác (Mở/Dừng) khi cửa sổ trình duyệt hẹp hơn khoảng 1460px; bảng giờ đổi bố cục theo bề rộng thực của chính nó.
- Profile không còn kẹt ở trạng thái "Đang mở" trên app desktop khi cùng lúc được mở qua API hoặc MCP; hai lệnh mở đồng thời cho cùng một profile không còn khởi chạy hai trình duyệt.

## [2.3.0] - 2026-10-09

### Thay đổi
- Thiết kế lại giao diện app desktop và web panel theo một hệ thống chung (xem `DESIGN.md`): nền giấy sáng, rail xanh, bảng profile thẳng cột với cột Thiết bị / Proxy / Timezone · Locale, và "dấu" trạng thái (đang chạy, đang mở, lỗi) phân biệt bằng cả hình dạng lẫn màu. Font Be Vietnam Pro và JetBrains Mono được đóng gói sẵn (OFL), chạy được không cần mạng.
- Thêm bộ lọc profile kèm số đếm (tất cả, đang chạy, có/không proxy, engine Chrome) trên cả hai giao diện; web panel có thêm thao tác hàng loạt và hộp thoại xác nhận riêng; app desktop đổi được Tiếng Việt / English ngay khi đang chạy.
- Thuật ngữ chuyên ngành giữ tiếng Anh trong giao diện tiếng Việt (fingerprint, engine, timezone, locale).

### Thêm
- Nhân **Chrome (thử nghiệm)** bên cạnh Camoufox, dựa trên fingerprint-chromium: chọn khi tạo profile trên app, web panel, REST API (`"engine": "chrome"`) và MCP (`create_profile(engine="chrome")`). Nhân cố định sau khi tạo. Cookie, fingerprint, điều khiển trang, mở lại tab và Kiểm tra IP dùng được như profile Camoufox. Bản trình duyệt được tự tải ở nền khi tạo profile Chrome đầu tiên, hoặc lúc mở profile nếu chưa có (cũng tải tay được bằng `python -m chrome_engine fetch`).
- Proxy dạng `host:port:user:pass` (định dạng thường gặp của nhà bán proxy) được chấp nhận ở mọi nơi nhập proxy, kể cả có tiền tố `socks5://`.
- Mở lại các tab đang mở khi profile được dừng (lưu vào `camoufox_data/<profile>/tabs.json` mỗi 2 giây khi tab thay đổi, chỉ `http`/`https`, tối đa 30 tab). Tắt bằng `FOXPROFILE_RESTORE_TABS=false`.

### Sửa
- Rò rỉ DNS khi dùng proxy `socks5://`/`socks4://`: việc tra IP đi ra lúc mở profile và nút **Kiểm tra IP** từng phân giải tên miền bằng DNS của máy (lộ nhà mạng thật). Nay chuyển sang `socks5h://`/`socks4a://` để proxy phân giải. Bản thân trình duyệt không bị ảnh hưởng.
- Chế độ `HEADLESS=virtual` (server Linux) không còn bỏ sót tiến trình Xvfb khi profile mở lỗi (ví dụ proxy không vào được) hoặc khi runner bị kill cứng/crash. Runner tự quản lý màn hình ảo và ghi lại Xvfb nó đã bật (theo PID và thời điểm khởi động, trong thư mục tạm riêng của user) để launcher, hoặc lần mở sau, tắt đúng Xvfb đó.

## [2.2.0] - 2026-10-08

### Thêm
- Đặt cố định múi giờ (IANA) và ngôn ngữ (`vi-VN`) cho từng profile; để trống vẫn tự động theo IP.
- Nút **Kiểm tra IP**: đối chiếu IP đi ra với Cloudflare, ipinfo và ip-api, cảnh báo lệch quốc gia/múi giờ, IP datacenter, proxy dual-stack và ngôn ngữ ngẫu nhiên. Có trên app, web panel, REST API (`GET /profiles/{name}/ip-check`, `POST /proxy/geo-check`) và MCP (`check_profile_ip`).
- Hướng dẫn triển khai lên server Linux (`docs/DEPLOY.md`, `deploy/`) và các script e2e thủ công (`tests/e2e/`).

## [2.1.0] - 2026-10-08

### Thêm
- MCP server (27 tool) cho AI agent, qua stdio và qua HTTP tại `/mcp`.
- Web panel có token bảo vệ, xem và điều khiển màn hình trình duyệt từ xa.
- Server mode chạy ẩn trình duyệt (`python -m src.server`).
- Hộp thoại hướng dẫn kết nối MCP cho Claude Code, Cursor, VS Code và Claude Desktop.

### Sửa
- Server mode đọc đúng `FOXPROFILE_HEADLESS` từ `.env`.

## [2.0.0] - 2026-10-08

Phát hành đầu tiên của FoxProfile: vân tay cố định theo profile, proxy riêng, xuất/nhập cookie (JSON và Netscape), REST API, giao diện tiếng Việt/tiếng Anh.

[Unreleased]: https://github.com/vitbau246/foxflow/compare/v2.3.1...HEAD
[2.3.1]: https://github.com/chienbm98/foxprofile/compare/v2.3.0...v2.3.1
[2.3.0]: https://github.com/chienbm98/foxprofile/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/chienbm98/foxprofile/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/chienbm98/foxprofile/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/chienbm98/foxprofile/releases/tag/v2.0.0
