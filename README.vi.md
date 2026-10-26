<div align="center">
  <img src="src/assets/icon.png" width="112" alt="FoxFlow logo" />
  <h1>FoxFlow</h1>
  <p><strong>Tự động hoá web tự host: ghi lại một lần, chạy lại trên bất kỳ profile trình duyệt nào</strong></p>
  <p>Workflow ghi và chạy lại có kiểm tra, thử lại, biến, điều kiện, vòng lặp và sinh chữ bằng AI · Profile trình duyệt tách biệt (Camoufox hoặc Chrome) · REST API và MCP cho script và AI agent · Giao diện tiếng Anh và tiếng Việt</p>

  <p>
    <a href="https://github.com/vitbau246/foxflow/actions/workflows/ci.yml"><img src="https://github.com/vitbau246/foxflow/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
    <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+" />
    <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey" alt="Windows | macOS | Linux" />
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License" /></a>
    <a href="https://github.com/chienbm98/foxprofile"><img src="https://img.shields.io/badge/based%20on-FoxProfile-orange" alt="Dựa trên FoxProfile" /></a>
  </p>

  <p><a href="README.md">English</a> · Tiếng Việt</p>
  <p>
    <a href="#bắt-đầu-nhanh">Bắt đầu nhanh</a> ·
    <a href="#workflow-ghi-lại-và-chạy-lại">Workflow</a> ·
    <a href="#mcp-cho-ai-điều-khiển-trình-duyệt">MCP</a> ·
    <a href="#rest-api">REST API</a> ·
    <a href="#dựa-trên-foxprofile">Nguồn gốc</a>
  </p>
</div>

![FoxFlow: bảng Tự động hoá](docs/images/automation.png)

FoxFlow tự động hoá những việc lặp đi lặp lại trên trình duyệt. Bạn làm một việc một lần trong khi FoxFlow ghi lại, chỉnh các bước, rồi cho chạy lại: mỗi bước đều được kiểm tra kết quả, bước lỗi được thử lại, lần chạy bị kẹt thì trình duyệt được khởi động lại và chạy lại từ đầu. Workflow đọc được chữ trên trang (bôi đen hoặc để chuột yên trên nó lúc ghi), điền biến, rẽ nhánh bằng nếu/ngược lại, lặp lại các bước, nối nhiều workflow trong một lần chạy và nhờ một model tương thích OpenAI viết chữ giúp bạn. Bạn chạy workflow từ app desktop, web panel, REST API, hoặc để AI agent (Claude, Cursor...) điều khiển trình duyệt qua MCP.

Mọi lần chạy diễn ra trong một **profile trình duyệt**: một trình duyệt tách biệt có cookie, phiên đăng nhập, proxy, timezone, locale và fingerprint thiết bị cố định của riêng nó, nên việc của các tài khoản hay khách hàng khác nhau không bao giờ dùng chung phiên. Profile chạy trên [Camoufox](https://github.com/daijro/camoufox) (Firefox) hoặc engine Chrome thử nghiệm dựa trên [fingerprint-chromium](https://github.com/adryfish/fingerprint-chromium), trên máy bạn hoặc VPS.

> [!NOTE]
> **FoxFlow dựa trên [FoxProfile](https://github.com/chienbm98/foxprofile) của [chienbm98](https://github.com/chienbm98)**, trình quản lý profile trình duyệt mã nguồn mở (MIT). FoxFlow giữ toàn bộ phần quản lý profile của FoxProfile và chuyển trọng tâm dự án sang tự động hoá web. Xem [Dựa trên FoxProfile](#dựa-trên-foxprofile).

## Mục lục

- [Tính năng](#tính-năng)
- [Yêu cầu](#yêu-cầu)
- [Bắt đầu nhanh](#bắt-đầu-nhanh)
- [Workflow: ghi lại và chạy lại](#workflow-ghi-lại-và-chạy-lại)
- [MCP: cho AI điều khiển trình duyệt](#mcp-cho-ai-điều-khiển-trình-duyệt)
- [Chế độ server và web panel](#chế-độ-server-và-web-panel)
- [Profile trình duyệt](#profile-trình-duyệt)
- [Cấu hình](#cấu-hình)
- [REST API](#rest-api)
- [Chuyển từ FoxProfile sang](#chuyển-từ-foxprofile-sang)
- [Phát triển](#phát-triển)
- [Đóng góp](#đóng-góp)
- [Lưu ý sử dụng](#lưu-ý-sử-dụng)
- [Dựa trên FoxProfile](#dựa-trên-foxprofile)
- [Giấy phép](#giấy-phép)
- [Ghi công](#ghi-công)

## Tính năng

**Tự động hoá**

- **Bảng điều khiển tự động hoá.** App mở ra với lần chạy hiện tại hoặc gần nhất của mọi profile (tiến độ theo bước, số lần thử, dấu trạng thái, lý do lỗi) và mọi workflow đã lưu kèm kết quả lần chạy gần nhất. Dừng, chạy lại hay xem log chỉ với một cú bấm.
- **Một workflow, nhiều profile.** Chạy một workflow trên bao nhiêu profile tuỳ chọn, điền biến cho lần chạy đó; profile đang tắt được mở trước.
- **Ghi và chạy lại workflow.** Mỗi click, gõ phím, chọn, bấm phím, cuộn và mở trang trong trình duyệt của profile thành một bước, mỗi phần tử kèm nhiều selector dự phòng.
- **Chạy lại tin cậy.** Mỗi bước được kiểm tra (ô đã có đúng chữ, ô đã được tích, click tới đúng trang như lúc ghi), lỗi thì thử lại, và nếu một bước cứ lỗi mãi thì cả lần chạy bắt đầu lại từ bước 1 trên trình duyệt mới.
- **Nhịp như người thật.** Mỗi bước giữ đúng khoảng dừng của bạn lúc ghi, bước gõ có tốc độ theo từng ký tự, và một mức tốc độ chung (x0.25 đến x5) cho cả workflow.
- **Biến, lấy chữ và AI.** `{{biến}}` trong giá trị, URL và selector; *Lấy chữ* đọc chữ trên trang vào biến (lọc được bằng regex), và lúc ghi, bôi đen chữ hoặc để chuột yên trên phần tử 3 giây sẽ được hỏi để thêm bước này; *Sinh bằng AI* gửi prompt tới API tương thích OpenAI và lưu câu trả lời.
- **Trigger.** Workflow tự chạy khi webhook được gọi, khi copy chữ, khi có file mới trong thư mục, hoặc theo lịch: mở profile, chạy workflow, đóng profile.
- **Điều kiện, vòng lặp và chuỗi.** Các bước *Nếu / Ngược lại*, *Lặp theo danh sách* (một số hoặc danh sách), *Lặp khi*, *Thoát vòng lặp* và *Gán biến*, với điều kiện trên biến hoặc trên trang; chạy nhiều workflow lần lượt trong một trình duyệt.
- **Menu hiện khi rê chuột.** Click vào phần tử chỉ hiện khi rê chuột được ghi kèm bước *Rê chuột vào trước*.
- **AI agent qua MCP.** Claude Code, Claude Desktop, Cursor, VS Code... tự mở profile, mở trang, đọc, click, gõ, chụp màn hình và chạy workflow bạn đã ghi.
- **REST API** có tài liệu Swagger cho mọi thao tác, để script hay bộ lập lịch bất kỳ khởi chạy và đọc log của lần chạy.
- **Chế độ server + web panel** cho VPS: trình duyệt chạy ẩn, web panel có token bảo vệ và màn hình xem từ xa bấm và gõ được.

**Profile trình duyệt** (kế thừa từ FoxProfile)

- **Phiên làm việc tách biệt.** Lịch sử, cookie và đăng nhập nằm trong thư mục của từng profile; các tab đang mở được mở lại ở lần khởi động sau.
- **Fingerprint thiết bị cố định cho từng profile**, sinh một lần rồi dùng lại, nên trang web luôn thấy cùng một thiết bị.
- **Hai engine.** Camoufox (Firefox, mặc định) hoặc Chrome (fingerprint-chromium, thử nghiệm), chọn khi tạo profile.
- **Mỗi profile một proxy riêng** (HTTP/HTTPS/SOCKS4/SOCKS5, có hoặc không có mật khẩu, cả dạng `host:port:user:pass`), nút kiểm tra proxy, và timezone/locale tự theo IP ra hoặc đặt cố định cho từng profile.
- **Xuất/nhập cookie** (JSON Cookie-Editor, `cookies.txt` Netscape), **xuất/nhập profile dạng ZIP**, và **nhân bản** profile tới 50 bản kèm workflow của nó.
- **Thao tác hàng loạt, lọc và tìm kiếm** trong bảng profile dễ quét, trên cả app desktop lẫn web panel.
- Giao diện **tiếng Anh** (mặc định) và tiếng Việt, đổi ngay trong app. Font đóng gói sẵn, không cần mạng.

## Yêu cầu

- Python 3.10 trở lên
- Windows, macOS hoặc Linux (CI chạy test trên cả ba)
- Vài trăm MB dung lượng trống cho Camoufox và cơ sở dữ liệu GeoIP, thêm ~140-190 MB nếu dùng engine Chrome

## Bắt đầu nhanh

```bash
git clone https://github.com/vitbau246/foxflow.git
cd foxflow

python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux/macOS

pip install -r requirements.txt
python -m camoufox fetch
```

`camoufox fetch` tải bản trình duyệt Camoufox (vài trăm MB) từ GitHub của dự án Camoufox. Lần mở profile đầu tiên sẽ tải thêm cơ sở dữ liệu GeoIP (~50 MB).

Chạy ứng dụng:

```bash
python -m src.main
```

Trên Windows có thể bấm đúp `run_foxflow.bat`. Ứng dụng mở cửa sổ chính và đồng thời chạy API tại `http://127.0.0.1:8000`; tài liệu API ở `http://127.0.0.1:8000/docs`. Đặt `FOXFLOW_LANG=vi` để dùng giao diện tiếng Việt.

Tự động hoá đầu tiên: tạo một profile, rồi ở **Tự động hoá** bấm **Ghi workflow** và chọn profile đó. Mở profile ngay trong hộp thoại, bấm **Bắt đầu ghi**, làm việc cần làm trong trình duyệt, rồi bấm **Dừng & lưu**. Bấm **Chạy** trên workflow mới để chạy lại trên một hoặc nhiều profile.

## Workflow: ghi lại và chạy lại

Workflow là một việc bạn đã làm một lần trong trình duyệt của profile, được lưu thành các bước để chạy lại trên bất kỳ profile nào.

### Bảng Tự động hoá

App desktop và web panel mở ra ở **Tự động hoá** (bấm **Profile** ở thanh bên trái để về bảng profile):

- **Lần chạy**: lần chạy hiện tại hoặc gần nhất của mọi profile, lần đang chạy lên đầu. Mỗi dòng cho thấy bước đang chạy kèm vạch tiến độ, số lần thử và khởi động lại, dấu trạng thái (đang chạy, đang mở, xong, lỗi, đã dừng) và lý do nếu lỗi. Dừng lần chạy, **Chạy lại**, mở **Log** (cập nhật trực tiếp khi đang chạy) hoặc xem màn hình của profile.
- **Workflow**: mọi workflow đã lưu, kèm profile đã ghi, số bước và kết quả lần chạy gần nhất. **Chạy** mở hộp thoại chạy; sửa và xoá nằm bên cạnh.
- **Hộp thoại chạy**: tick các profile sẽ chạy workflow (mỗi profile chạy một bản riêng; profile đang ghi hoặc đang chạy workflow khác bị làm mờ kèm lý do) và điền biến của workflow cho lần chạy này. Profile đang tắt được mở trước.
- Ở **Profile**, chọn các dòng rồi bấm **Chạy workflow** trên thanh thao tác hàng loạt để chạy một workflow trên tất cả.

Bảng tự cập nhật mỗi 1,5 giây khi có lần chạy đang chạy, còn lại mỗi 4 giây.

### Ghi, sửa, chạy

Mở workflow của một profile bằng nút **Workflow** trên dòng profile, hoặc bằng **Ghi workflow** ở Tự động hoá.

1. **Ghi.** Mở profile, bấm **Bắt đầu ghi**, rồi làm việc đó trong trình duyệt của nó: mỗi click, gõ phím, chọn, bấm phím (Enter, Escape, Tab...) và cuộn trang đều thành một bước, mở trang cũng vậy. Trên server thì thao tác qua **Xem màn hình**. Bấm **Dừng & lưu** và đặt tên. Nếu trình duyệt đóng khi đang ghi, các bước vẫn được giữ thành một bản ghi chưa lưu để lưu sau.
2. **Sửa.** Mỗi bước có **delay** riêng (thời gian chờ trước bước, lấy từ khoảng dừng thật của bạn lúc ghi) và với bước gõ thì có **tốc độ gõ** tính bằng ms mỗi ký tự (0 là điền ngay). **Tốc độ** chung của workflow chia mọi delay: x2 là nhanh gấp đôi. Có thể tắt, đổi thứ tự, thêm hoặc xoá bước; **Chi tiết** hiện các selector (thử lần lượt), giá trị, frame, thời gian chờ tối đa và URL mong đợi.
3. **Chạy.** Mặc định mọi bước đều được kiểm tra kết quả: ô vừa gõ phải chứa đúng chữ, ô tích phải được tích, một click lúc ghi đã chuyển trang thì lúc chạy phải tới đúng trang đó, và phần tử phải tìm thấy trong thời gian chờ của bước. Có thể đổi phần kiểm tra thành chờ một URL, tiêu đề, phần tử hoặc dòng chữ, hoặc tắt hẳn. Bước lỗi được thử lại sau thời gian chờ thử lại (mặc định **thử lại 2 lần**); vẫn lỗi thì trình duyệt bị tắt và workflow chạy lại **từ bước 1**, mặc định tối đa **3 lần khởi động lại**, sau đó lần chạy báo lỗi kèm lý do. Theo dõi lần chạy, log và dừng ngay trong hộp thoại đó.

Khi chạy, workflow chỉ để lại một tab trong profile (bắt đầu giống lúc ghi) và không chạy khi profile đang ghi. Dừng profile thì lần chạy cũng dừng. Workflow cũng chạy được từ REST API (`POST /workflows/{name}/run`) hoặc do AI agent gọi (`run_workflow`).

### Menu hiện khi rê chuột, biến, lấy chữ và AI

- **Rê chuột vào trước.** Có nút chỉ xuất hiện khi rê chuột vào chỗ khác: bảng cảm xúc hiện trên nút "Thích", menu mở khi rê chuột. Khi click rơi vào phần trang như vậy, bản ghi tự thêm **Rê chuột vào trước** cho bước đó (phần tử cần rê, rồi chờ, mặc định 800 ms). Nếu bản ghi bỏ sót, thêm tay ở **Chi tiết** của bước.
- **Biến.** Viết `{{tên}}` trong giá trị, URL hay selector của bước; nó được thay khi bước chạy. Đặt giá trị ban đầu ở mục **Biến** trong trình sửa, hoặc theo từng lần chạy qua API (`"variables": {...}`). `{{profile}}` luôn là tên profile đang chạy. Bước dùng biến không tồn tại bị từ chối khi lưu.
- **Lấy chữ** đọc chữ hiển thị của một phần tử (cả trang nếu không có selector), có thể lọc qua biểu thức chính quy (lấy nhóm đầu, ví dụ `#(\d+)`), rồi lưu vào biến. Bước báo lỗi khi không có chữ hoặc biểu thức không khớp.
- **Sinh bằng AI** gửi prompt (đã thay `{{biến}}`) tới API Chat Completions tương thích OpenAI và lưu câu trả lời vào biến. Ví dụ: *Lấy chữ* trang đơn hàng vào `{{order}}`, *Sinh bằng AI* "Viết một câu trả lời ngắn xác nhận đơn hàng này: {{order}}" vào `{{reply}}`, rồi *Gõ* `{{reply}}`. Cấu hình ở nút **Cấu hình AI** trong trình sửa: API key, base URL (mặc định OpenAI; dùng được cả Azure OpenAI, OpenRouter hay LLM chạy trên máy), model, system prompt và temperature, có nút **Thử**. AI tắt cho tới khi có key. Prompt, kể cả chữ lấy từ trang mà nó dùng, được gửi tới dịch vụ đó, từ tiến trình FoxFlow (không qua proxy của profile). Key lưu trong `ai_settings.json` cạnh `profiles.json`, hoặc lấy từ `FOXFLOW_OPENAI_API_KEY` (không bao giờ được ghi ra đĩa).

### Lấy text ngay lúc ghi

Trong lúc ghi, **bôi đen chữ** bằng chuột, hoặc **để chuột yên trên một phần tử 3 giây**: một khung nhỏ trong trang hỏi *Lấy text này?*, hiện đoạn chữ và gợi ý tên biến (`text1`, `text2`...). **Lấy text** thêm bước *Lấy chữ* cho phần tử đó; **Bỏ qua**, Escape hoặc click chỗ khác thì đóng lại, và phần tử đó không được hỏi lại cho tới khi chuột sang phần tử khác. Click và phím trong khung không bị ghi, kéo chuột để bôi đen không bị ghi thành click, và selector của bước không dựa vào chữ của phần tử (vì chữ đổi theo từng lần chạy).

### Điều kiện, vòng lặp và biến

Bước còn có thể điều khiển lần chạy. Các bước này chạy trong FoxFlow, xen giữa các bước trên trình duyệt:

| Bước | Tác dụng |
|---|---|
| **Gán biến** | Lưu một giá trị vào biến: chữ có `{{biến}}`, hoặc dấu `=` và biểu thức, ví dụ `= count + 1`, `= upper(name)`. |
| **Nếu** ... **Ngược lại** ... **Kết thúc khối** | Chạy các bước tới Ngược lại (hoặc Kết thúc khối) khi điều kiện đúng, ngược lại chạy các bước sau Ngược lại. |
| **Lặp theo danh sách** ... **Kết thúc khối** | Chạy các bước bên trong một lần cho mỗi mục: một số N (vòng 1 tới N), hoặc danh sách, mỗi dòng một mục hoặc cách nhau bằng dấu phẩy, ví dụ `{{names}}`. Mục hiện tại (hoặc số vòng) nằm trong biến của bước. |
| **Lặp khi** ... **Kết thúc khối** | Chạy các bước bên trong khi điều kiện còn đúng, nhiều nhất *Tối đa (vòng)* lần (mặc định 100). |
| **Thoát vòng lặp** | Rời vòng lặp trong cùng đang chứa nó. |

Điều kiện là **biểu thức trên biến**, ví dụ `price > 100 and status == "ok"`, `contains(title, "Sale")`, `len(code) == 6` (hai giá trị đọc được như số thì so như số; hàm: `len`, `int`, `num`, `str`, `lower`, `upper`, `trim`, `contains`, `startswith`, `endswith`, `matches`, `replace`), hoặc **điều kiện trên trang**: thấy phần tử, thấy chữ, URL chứa, tiêu đề chứa, có thể chờ tới timeout của bước. Tick *Vào khối khi điều kiện KHÔNG đúng* để đảo lại. Biểu thức chỉ được phân tích, không bao giờ chạy như code.

Trong trình sửa, các bước trong khối được thụt vào, nút **+** trên mỗi dòng chèn một bước bên dưới, và chọn Nếu hay Lặp thì tự thêm Kết thúc khối. Khi lưu, khối thiếu Kết thúc khối, Ngược lại nằm ngoài Nếu, và Thoát vòng lặp nằm ngoài vòng lặp đều bị từ chối.

### Chạy nhiều workflow trong một lần

Trong hộp thoại chạy, **Thêm workflow** nối thêm workflow: mỗi profile được chọn chạy lần lượt các workflow trong cùng một trình duyệt. Mỗi workflow giữ cài đặt riêng và khởi động lại từ bước đầu của chính nó; biến lưu ở workflow trước được dùng tiếp ở workflow sau (workflow sau cần có biến cùng tên để dùng); lần chạy dừng ở workflow đầu tiên bị lỗi. **Chạy lại** trên dòng lần chạy sẽ chạy lại cả chuỗi. Qua API: `POST /workflow-runs` với `{"profile": ..., "workflows": [...], "variables": {...}}`; qua MCP: `run_workflows`.

### Trigger: workflow tự chạy

Trigger theo dõi một sự kiện, rồi mở profile, chạy lần lượt các workflow và đóng profile. Tạo bằng **Tạo trigger** ở mục **Trigger** trong Tự động hoá:

| Khi | Kích hoạt |
|---|---|
| **Webhook** | Ứng dụng khác (Zapier, n8n, script, form) gọi URL của trigger bằng `POST` hoặc `GET`. URL mang key riêng của trigger (hoặc gửi qua header `X-FoxFlow-Key`); không cần API token, nên chia sẻ URL chứ không chia sẻ token. Body JSON điền vào các biến cùng tên của workflow, và trường `"text"` (hoặc `?text=`) thành `{{trigger_text}}`. |
| **Khi copy chữ** | Có chữ được copy trên máy này, có thể chỉ chữ khớp biểu thức chính quy (ví dụ `https?://` cho link). Chỉ theo dõi khi FoxFlow đang mở; chữ ở lại trên máy. |
| **File mới trong thư mục** | Có file mới trong thư mục (không tính thư mục con), có thể chỉ tên khớp mẫu như `*.csv`. File có sẵn không tính, và file chỉ kích hoạt khi đã ghi xong (không còn lớn lên). |
| **Lịch** | Mỗi N phút, và/hoặc hằng ngày vào các giờ đặt sẵn (`08:30, 17:00`). |

**Sau đó**: mọi profile được chọn cùng lúc chạy các workflow theo thứ tự (profile đang chạy workflow khác thì chờ). Bật *Đóng từng profile khi xong* thì profile do trigger mở sẽ được đóng khi chạy xong, dù thành công hay lỗi; profile đã mở sẵn từ trước thì giữ nguyên. Sự kiện đến trong lúc đang xử lý sự kiện trước sẽ xếp hàng chờ.

Workflow nhận thông tin sự kiện qua các biến có sẵn (trống khi chạy theo cách khác): `{{trigger_type}}` (`webhook`, `clipboard`, `file`, `schedule` hoặc `manual`), `{{trigger_text}}` (chữ của webhook, chữ được copy, hoặc nội dung file chữ nhỏ), `{{trigger_file}}` và `{{trigger_file_name}}` (file mới) và `{{trigger_time}}`. Mỗi dòng trigger cho thấy sự kiện gần nhất và kết quả; **Chạy ngay** kích hoạt bằng tay (kể cả khi đang tắt), công tắc để bật/tắt. Lần chạy do trigger khởi động ghi *qua <trigger>* trong bảng Lần chạy.

```bash
# Gọi một trigger webhook (URL nằm trong trình sửa trigger)
curl -X POST "http://127.0.0.1:8000/api/v1/hooks/<id>?key=<key>" \
  -H "Content-Type: application/json" -d '{"text": "đơn mới", "order": "A-17"}'
```

Trigger lưu trong `automations.json` cạnh `profiles.json`, kèm key của từng webhook: giữ kín file này. Qua API: `/automations`; qua MCP: `list_triggers` và `fire_trigger`.

Workflow là các file JSON trong `workflows/`, mỗi workflow một file, sửa được cả qua REST API (`PUT /workflows/{name}`). File chứa những gì bạn đã gõ lúc ghi, **kể cả mật khẩu** (ô mật khẩu chỉ được ẩn trên giao diện), nên hãy giữ thư mục này cẩn thận như `camoufox_data/`. Khi chạy lại, trang được điều khiển qua Playwright: trang web chặn tự động hoá có thể nhận ra.

## MCP: cho AI điều khiển trình duyệt

FoxFlow có sẵn MCP server, để Claude Code, Claude Desktop, Cursor, VS Code... tự quản lý profile, thao tác trên trang (mở URL, đọc trang, click, gõ, chụp màn hình) và chạy các workflow bạn đã ghi.

**Cách nhanh nhất:** bấm **Kết nối AI (MCP)** ở thanh bên trái của app desktop hoặc web panel. Hộp thoại sinh sẵn cấu hình cho từng ứng dụng AI, đúng địa chỉ và token của bạn, chỉ cần bấm Sao chép rồi dán.

![Kết nối AI (MCP)](docs/images/mcp-guide.png)

MCP được phục vụ qua HTTP tại `/mcp`, ngay trên cổng của FoxFlow, nên dùng được cả khi FoxFlow chạy trên VPS:

```bash
# Claude Code
claude mcp add --transport http foxflow http://127.0.0.1:8000/mcp
# Server có token:
claude mcp add --transport http foxflow https://vps.cua-ban.com/mcp --header "Authorization: Bearer <token>"
```

```jsonc
// Cursor: ~/.cursor/mcp.json
{ "mcpServers": { "foxflow": { "url": "http://127.0.0.1:8000/mcp" } } }
```

Claude Desktop chỉ chạy được server MCP cục bộ: dùng `foxflow_mcp.py` (cùng máy) hoặc cầu nối `npx mcp-remote` (máy khác). Hộp thoại "Kết nối AI" sinh sẵn cả hai.

Sau đó chỉ cần nhắn AI, ví dụ: *"Mở profile work-01, vào example.com và chụp màn hình cho tôi"* hoặc *"Chạy workflow daily-report trên profile work-01 và báo tôi nếu nó lỗi"*.

| Nhóm | Tool |
| --- | --- |
| Profile | `list_profiles`, `get_profile`, `create_profile`, `update_profile`, `clone_profile`, `launch_profile`, `stop_profile`, `running_profiles` |
| Cookie & fingerprint | `export_cookies`, `import_cookies`, `get_fingerprint`, `reset_fingerprint`, `check_proxy`, `check_profile_ip` |
| Trang | `browser_navigate`, `browser_back`, `browser_snapshot`, `browser_get_text`, `browser_click`, `browser_click_at`, `browser_type`, `browser_press`, `browser_wait_for`, `browser_screenshot`, `browser_evaluate` |
| Tab | `browser_tabs`, `browser_tab_new`, `browser_tab_select`, `browser_tab_close` |
| Workflow | `list_workflows`, `get_workflow`, `run_workflow`, `run_workflows`, `workflow_run_status`, `stop_workflow_run`, `list_triggers`, `fire_trigger` |

MCP **không** có tool xóa profile, để AI không thể vô tình xóa cookie của tài khoản. Trang chỉ mở được `http`, `https` và `about:blank`; `file://` và `about:config` bị chặn.

## Chế độ server và web panel

Không cần cửa sổ desktop: chỉ chạy API và web panel, trình duyệt chạy ẩn. Phù hợp với VPS chạy workflow suốt ngày đêm.

```bash
python -m src.server                     # http://127.0.0.1:8000
python -m src.server --host 0.0.0.0      # mở ra mạng: BẮT BUỘC đặt token
```

Mở `http://<địa-chỉ>:8000/` để vào **web panel**: cùng bảng profile, bộ lọc, thao tác hàng loạt và hộp thoại workflow như app desktop, thêm **màn hình xem từ xa**. Bạn có thể bấm thẳng lên ảnh màn hình và gõ phím để ghi workflow, đăng nhập hay giải captcha, kể cả khi trình duyệt đang chạy ẩn trên server.

| Web panel | Xem màn hình từ xa |
| --- | --- |
| ![Web panel](docs/images/panel.png) | ![Xem màn hình từ xa](docs/images/panel-viewer.png) |

**Bảo mật:** khi nghe ngoài `127.0.0.1`, server **từ chối khởi động** nếu chưa đặt `FOXFLOW_API_TOKEN` (tối thiểu 24 ký tự). Web panel, REST API và MCP đều dùng chung token này.

```bash
# Tạo token ngẫu nhiên
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Khi đưa lên VPS, nên đặt server sau reverse proxy có HTTPS (Caddy, Nginx) để token không bị gửi đi dưới dạng chữ thường. Trên Linux không có màn hình, đặt `FOXFLOW_HEADLESS=virtual` (cần cài `xvfb`) để trình duyệt chạy trên màn hình ảo, hoạt động giống trình duyệt desktop bình thường hơn chế độ headless thường.

Hướng dẫn triển khai đầy đủ (Ubuntu, systemd, nginx, HTTPS): [docs/DEPLOY.md](docs/DEPLOY.md).

## Profile trình duyệt

Profile là một trình duyệt tách biệt: thư mục dữ liệu riêng (cookie, đăng nhập, lịch sử), proxy, timezone, locale và fingerprint thiết bị. Workflow và AI agent luôn thao tác bên trong một profile.

![Hộp thoại tạo profile](docs/images/profile-dialog.png)

### Timezone, locale và Kiểm tra IP

Mặc định, mỗi lần mở profile Camoufox tra IP đi ra (qua proxy của profile) và đặt timezone, locale, toạ độ và IP WebRTC theo IP đó. Có ba điều nên biết:

- **Locale tự động được chọn ngẫu nhiên ở mỗi lần mở**, theo tỷ lệ người nói từng ngôn ngữ ở quốc gia của IP. Ví dụ IP Pháp cho `fr-FR` khoảng 60% số lần, còn lại là `en-FR`, `es-FR`… Hãy đặt cố định locale cho profile khi trang web cần thấy cùng một ngôn ngữ ở mọi phiên.
- **Các cơ sở dữ liệu GeoIP không phải lúc nào cũng thống nhất.** Cùng một IP có thể được Cloudflare xếp vào nước này, Google vào nước khác; Camoufox cũng có thể chọn một timezone cùng giờ nhưng khác tên (ví dụ IP Việt Nam ra `Asia/Bangkok` thay vì `Asia/Ho_Chi_Minh`).
- **IP datacenter hay bị bắt captcha** ở nhiều trang bất kể cấu hình trình duyệt, làm hỏng các lần chạy không người trông.

Trong hộp thoại tạo/sửa profile có hai ô **Timezone** (tên IANA, ví dụ `Asia/Ho_Chi_Minh`) và **Locale** (dạng `vi-VN`); để trống là tự động theo IP. Nút **Kiểm tra IP** lấy IP đi ra qua proxy, đối chiếu với Cloudflare, ipinfo và ip-api, rồi cảnh báo khi lệch quốc gia hoặc timezone, khi IP bị gắn datacenter, khi proxy ra Internet bằng IPv4 và IPv6 khác nhau, và khi locale đang để ngẫu nhiên.

### Engine Chrome (thử nghiệm)

Ngoài Camoufox (Firefox), profile có thể chạy trên engine **Chrome**: một bản Chromium đã vá fingerprint ở tầng C++ ([fingerprint-chromium](https://github.com/adryfish/fingerprint-chromium), giấy phép BSD-3). Chọn ở ô **Engine** khi tạo profile; không đổi được sau khi tạo. Bản trình duyệt (~140-190 MB tuỳ hệ điều hành, tải từ GitHub của fingerprint-chromium và kiểm tra SHA-256) được tự tải ở nền ngay khi tạo profile Chrome đầu tiên, hoặc lúc mở profile nếu chưa có; tiến độ hiện trong log. Muốn tải trước bằng tay: `python -m chrome_engine fetch`.

Nên chọn đúng hệ điều hành của máy đang chạy FoxFlow: persona khác hệ điều hành sẽ lộ font của máy, và persona Linux trên Windows/macOS bị từ chối vì WebGL lộ GPU thật. Hỗ trợ Windows x64, macOS Apple Silicon và Linux x64 (chưa kiểm chứng). Chi tiết và kết quả kiểm thử: [chrome_engine/README.md](chrome_engine/README.md).

### Cookie, fingerprint và nhân bản

![Cookie & fingerprint](docs/images/cookies.png)

Bấm nút cookie trên dòng profile để mở hộp thoại **Cookie & fingerprint**. Các thao tác này cần trình duyệt của profile đang tắt, vì FoxFlow mở profile ở chế độ headless để đọc và ghi cookie; nếu profile đang chạy, FoxFlow sẽ hỏi rồi dừng giúp. Đổi tên, xoá và nhân bản kèm dữ liệu cũng vậy.

- Cookie xuất/nhập dạng JSON Cookie-Editor / EditThisCookie và `cookies.txt` Netscape (yt-dlp, curl, wget). Cookie phiên (session) khi nhập vào sẽ được đặt hạn 1 năm; nếu không, trình duyệt sẽ xóa chúng ngay khi đóng.
- "Tạo fingerprint mới" xóa fingerprint đã lưu; lần mở sau profile sẽ là một thiết bị khác. Đổi hệ điều hành của profile cũng tự sinh fingerprint mới.
- **Nhân bản** (nút sao chép trên dòng profile) tạo profile mới cùng cài đặt: đặt **Số bản** để tạo nhiều bản một lần, đặt tên theo tên gốc thêm -1, -2... (bỏ qua số đã dùng). Mỗi bản sao luôn có fingerprint mới. Ở mục **Chép thêm**, tick những gì đi kèm: **cookie** (phiên đăng nhập), **lịch sử và bookmark**, **dữ liệu trang web** (localStorage, IndexedDB, quyền của trang), **mật khẩu đã lưu**, **các tab đang mở** (các mục này cần profile đang tắt), và **workflow của profile**: mỗi bản sao có workflow riêng, tên `<workflow>-<profile mới>`. Cache, file khoá, các cài đặt khác và bản ghi chưa lưu không bao giờ được chép. Khi chép cookie, trang web thấy cùng các phiên đăng nhập trên một thiết bị mới, có trang sẽ coi là đăng nhập mới.
- **Xuất/nhập cả profile** ra file ZIP, có hoặc không kèm dữ liệu trình duyệt, để chuyển sang máy khác. Fingerprint luôn đi kèm.

## Cấu hình

Mọi cấu hình đều không bắt buộc. Muốn đổi thì sao chép `.env.example` thành `.env`.

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `FOXFLOW_LANG` | `en` | Ngôn ngữ giao diện: `en` hoặc `vi` |
| `FOXFLOW_PROFILES_FILE` | `profiles.json` | File lưu danh sách profile |
| `FOXFLOW_DATA_DIR` | `camoufox_data` | Thư mục dữ liệu, mỗi profile một thư mục con |
| `FOXFLOW_LOG_DIR` | `logs` | Thư mục log |
| `FOXFLOW_LOG_LEVEL` | `INFO` | Mức log |
| `FOXFLOW_PROXY_TIMEOUT` | `10` | Thời gian chờ khi kiểm tra proxy (giây) |
| `FOXFLOW_LAUNCH_TIMEOUT` | `90` | Thời gian API chờ trình duyệt mở xong (giây) |
| `FOXFLOW_HEADLESS` | `false` (`true` ở chế độ server) | Chạy trình duyệt ẩn: `true`, `false` hoặc `virtual` (Linux + Xvfb) |
| `FOXFLOW_RESTORE_TABS` | `true` | Mở lại các tab của lần chạy trước |
| `FOXFLOW_WORKFLOWS_DIR` | `workflows` | Các workflow đã lưu, mỗi workflow một file JSON |
| `FOXFLOW_AUTOMATIONS_FILE` | `automations.json` | Các trigger đã lưu, kèm key webhook |
| `FOXFLOW_OPENAI_API_KEY` | *(trống)* | Key cho bước Sinh bằng AI; được ưu tiên hơn key trong Cấu hình AI và không bao giờ được lưu |
| `FOXFLOW_OPENAI_BASE_URL` | `https://api.openai.com/v1` | Base URL mặc định của API tương thích OpenAI |
| `FOXFLOW_OPENAI_MODEL` | `gpt-4o-mini` | Model mặc định |
| `FOXFLOW_AI_SETTINGS_FILE` | `ai_settings.json` | Nơi lưu cấu hình AI (kèm key) |
| `FOXFLOW_HTTP_PROXY` | *(trống: đi thẳng)* | Proxy cho các request ra Internet của chính FoxFlow, ví dụ `http://host:port` hoặc `http://user:pass@host:port`. Xem [Mạng và proxy](#mạng-và-proxy) |
| `FOXFLOW_API_TOKEN` | *(trống)* | Token cho API, web panel và MCP. Bắt buộc khi API nghe ngoài `127.0.0.1` |
| `FOXFLOW_API_HOST` | `127.0.0.1` | Địa chỉ API |
| `FOXFLOW_API_PORT` | `8000` | Cổng API |

Tên cũ `FOXPROFILE_*` vẫn dùng được; nếu đặt cả hai thì biến `FOXFLOW_*` được ưu tiên.

### Mạng và proxy

Các request ra Internet của chính FoxFlow gồm: bước Sinh bằng AI, tải engine Chrome và cơ sở dữ liệu GeoIP, và việc tra IP ra / **Kiểm tra IP** của profile không có proxy riêng. Chúng **đi thẳng** trừ khi bạn đặt `FOXFLOW_HTTP_PROXY`; proxy hệ thống và `HTTP(S)_PROXY` bị bỏ qua. Request tới API của chính FoxFlow và tới các trình duyệt trên `127.0.0.1` không bao giờ đi qua proxy.

Nếu máy này chỉ vào được Internet qua proxy (ví dụ mạng công ty), thêm proxy vào `.env` rồi khởi động lại FoxFlow:

```bash
FOXFLOW_HTTP_PROXY=http://host:port
# hoặc có đăng nhập
FOXFLOW_HTTP_PROXY=http://user:pass@host:port
```

Dấu hiệu cần đặt: log lúc khởi động báo *"Internet requests go direct"*, và bước AI, tải engine Chrome, Kiểm tra IP hay mở profile không có proxy báo lỗi *"no internet connection"* hoặc *"Cannot reach..."*. Các lỗi này kèm lời nhắc đặt `FOXFLOW_HTTP_PROXY`, và hộp thoại **Cấu hình AI** cho biết đang đi đường nào. `python -m camoufox fetch` không thuộc FoxFlow: nếu máy cần proxy, chạy lệnh đó với `HTTPS_PROXY` đặt trong cửa sổ terminal.

Cài đặt này không đổi đường đi của trình duyệt: lưu lượng của mỗi profile đi qua proxy riêng của profile đó.

### Định dạng proxy

`host:port`, `http://host:port`, `https://...`, `socks4://...`, `socks5://...`, có thể kèm `user:pass@`. Dạng `host:port:user:pass` mà nhà cung cấp proxy hay đưa cũng dùng được. Để trống nghĩa là kết nối trực tiếp.

### Dữ liệu được lưu ở đâu

```text
profiles.json                                     danh sách profile (tên, engine, proxy, hệ điều hành, timezone, locale)
camoufox_data/<tên-profile>/                      dữ liệu trình duyệt: cookie, lịch sử, localStorage
camoufox_data/<tên-profile>/fingerprint.json      fingerprint thiết bị (engine Camoufox)
camoufox_data/<tên-profile>/chrome_persona.json   fingerprint thiết bị (engine Chrome)
camoufox_data/<tên-profile>/tabs.json             các tab sẽ được mở lại
camoufox_data/<tên-profile>/recording.json        các bước của bản ghi đang ghi hoặc chưa lưu
workflows/<tên-workflow>.json                     workflow đã lưu: bước, delay, kiểm tra, thử lại
ai_settings.json                                  cấu hình AI cho bước Sinh bằng AI, kèm API key
automations.json                                  các trigger, kèm key webhook
logs/foxflow_YYYYMMDD.log                         log theo ngày
```

> [!WARNING]
> `camoufox_data/` chứa cookie đăng nhập của mọi tài khoản, còn `workflows/` chứa những gì đã gõ lúc ghi, kể cả mật khẩu. Không commit, không chia sẻ các thư mục này.

## REST API

Tiền tố: `/api/v1`. Xem đầy đủ tại `/docs` khi ứng dụng đang chạy.

| Method | Đường dẫn | Mô tả |
| --- | --- | --- |
| `GET` | `/health` | Kiểm tra API |
| `POST` | `/browser/{name}/record/start` · `/record/stop` | Bắt đầu ghi; dừng ghi, lưu thành workflow với `{"save_as": "tên"}` hoặc bỏ đi với `{"discard": true}` |
| `GET` | `/browser/{name}/record` · `/recordings` | Trạng thái ghi của một profile (`draft` = đã ghi nhưng chưa lưu) / của mọi profile |
| `GET` / `POST` | `/workflows` | Danh sách / tạo workflow |
| `GET` / `PUT` / `DELETE` | `/workflows/{name}` | Xem / lưu (bước, delay, tốc độ gõ, kiểm tra, thử lại) / xoá workflow |
| `POST` | `/workflows/{name}/run` | Chạy lại trên một profile: `{"profile": "tên", "variables": {}}`, tự mở trình duyệt nếu cần (202) |
| `POST` | `/workflow-runs` | Chạy lần lượt nhiều workflow trên một profile: `{"profile": "tên", "workflows": ["a", "b"], "variables": {}}` (202) |
| `GET` / `POST` | `/workflow-runs` · `/workflow-runs/{profile}` · `/workflow-runs/{profile}/stop` | Các lần chạy (`?log=false` bỏ phần log); lần chạy hiện tại hoặc gần nhất của một profile (trạng thái, bước, lần thử, số lần khởi động lại, log); dừng nó |
| `GET` / `POST` | `/automations` | Các trigger kèm sự kiện gần đây / tạo trigger: `{"name": ..., "trigger": {"type": "webhook"}, "profiles": [...], "workflows": [...]}` |
| `GET` / `PUT` / `DELETE` | `/automations/{id hoặc tên}` | Đọc / lưu / xoá một trigger |
| `POST` | `/automations/{id hoặc tên}/fire` | Chạy ngay: `{"text": "", "variables": {}}` (202) |
| `GET` / `POST` | `/hooks/{id}?key=...` | Webhook của trigger: không cần API token, chỉ cần key của nó (202) |
| `GET` / `PUT` | `/ai/settings` | Cấu hình AI (key chỉ hiện gợi ý) / lưu cấu hình (bỏ `api_key` thì giữ key cũ, `""` thì xoá) |
| `POST` | `/ai/test` | Gửi thử một prompt với cấu hình AI đã lưu |
| `POST` | `/browser/{name}/page/navigate` · `back` | Mở URL trong tab đang chọn, quay lại trang trước |
| `GET` | `/browser/{name}/page/snapshot` · `text` | Cây accessibility của trang (để chọn selector), chữ trên trang |
| `POST` | `/browser/{name}/page/click` · `type` · `press` · `wait` | Click, gõ, bấm phím, chờ phần tử (selector Playwright) |
| `POST` | `/browser/{name}/page/click-at` · `keyboard` | Click theo tọa độ, gõ vào ô đang chọn |
| `GET` | `/browser/{name}/page/screenshot` | Ảnh PNG của tab (`?format=json` để nhận base64) |
| `POST` | `/browser/{name}/page/evaluate` | Chạy JavaScript |
| `GET` / `POST` | `/browser/{name}/page/tabs` | Liệt kê / mở tab mới |
| `POST` / `DELETE` | `/browser/{name}/page/tabs/{index}/select` · `/page/tabs/{index}` | Chọn / đóng tab |
| `GET` | `/browser` | Danh sách profile đang chạy |
| `GET` | `/browser/{name}/status` | Profile có đang chạy không |
| `POST` | `/browser/{name}/launch` | Mở trình duyệt, chờ đến khi mở xong hoặc lỗi (409 nếu đang chạy hoặc đang bận) |
| `POST` | `/browser/{name}/stop` | Đóng trình duyệt |
| `GET` / `POST` | `/profiles` | Liệt kê / tạo profile |
| `GET` / `PATCH` / `DELETE` | `/profiles/{name}` | Xem / sửa / xóa profile (không đổi được `engine`) |
| `POST` | `/profiles/{name}/clone` | Nhân bản: `{"name": "tên-mới", "count": 1, "copy": ["cookies", "workflows"]}`; `count` > 1 (tối đa 50) thì tên là `tên-mới-1`, `tên-mới-2`...; `copy` nhận `cookies`, `history`, `site_data`, `passwords`, `tabs` (profile phải tắt) và `workflows`; mỗi bản sao có fingerprint mới |
| `GET` | `/profiles/{name}/data-dir` | Đường dẫn thư mục dữ liệu của profile |
| `POST` | `/profiles/{name}/export` | Xuất profile ra ZIP |
| `POST` | `/profiles/import` | Nhập profile từ ZIP |
| `GET` | `/profiles/{name}/cookies?format=json\|netscape` | Xuất cookie |
| `POST` | `/profiles/{name}/cookies` | Nhập cookie (`{"content": "<JSON hoặc cookies.txt>"}`) |
| `GET` / `DELETE` | `/profiles/{name}/fingerprint` | Xem / tạo fingerprint mới |
| `GET` | `/profiles/{name}/ip-check` | Kiểm tra IP ra của profile: quốc gia, timezone theo Cloudflare/ipinfo/ip-api, cảnh báo lệch |
| `POST` | `/proxy/check` | Kiểm tra proxy |
| `POST` | `/proxy/geo-check` | Như `ip-check` cho tổ hợp `{proxy, timezone, locale}` chưa lưu |
| `GET` | `/mcp/setup?base_url=...` | Cấu hình MCP cho từng ứng dụng AI (dùng bởi hộp thoại Kết nối AI) |

Khi có `FOXFLOW_API_TOKEN`, mọi request (trừ `/health` và `/info`) phải gửi header `Authorization: Bearer <token>`.

Ví dụ:

```bash
# Tạo profile có proxy. "engine": "chrome" để dùng engine Chrome (mặc định "camoufox").
curl -X POST http://127.0.0.1:8000/api/v1/profiles \
  -H "Content-Type: application/json" \
  -d '{"name": "work-01", "os_type": "windows", "proxy": "socks5://user:pass@203.0.113.10:1080"}'

# Chạy lại một workflow đã ghi trên profile đó (tự mở trình duyệt nếu cần)
curl -X POST http://127.0.0.1:8000/api/v1/workflows/daily-report/run \
  -H "Content-Type: application/json" \
  -d '{"profile": "work-01", "variables": {"date": "2026-10-26"}}'

# Theo dõi lần chạy: trạng thái, bước hiện tại, số lần thử và log
curl http://127.0.0.1:8000/api/v1/workflow-runs/work-01
```

## Chuyển từ FoxProfile sang

FoxFlow đọc nguyên trạng một bản cài FoxProfile: chạy từ cùng thư mục là có đủ profile, cookie, fingerprint và workflow.

- **Dữ liệu giữ nguyên**: `profiles.json`, `camoufox_data/`, `workflows/` và `ai_settings.json` không đổi tên, không đổi định dạng.
- **Biến môi trường** giờ là `FOXFLOW_*`. `FOXPROFILE_*` trong `.env` cũ vẫn được đọc nên không có gì bị hỏng; đổi tên khi tiện.
- **Engine Chrome** dùng lại bản trình duyệt FoxProfile đã tải, không tải lại.
- **Mạng**: FoxFlow không còn tự dùng proxy hệ thống cho các request của chính nó. Nếu cần proxy, đặt `FOXFLOW_HTTP_PROXY` (xem [Mạng và proxy](#mạng-và-proxy)).
- **MCP**: server giờ tên là `foxflow`, file chạy qua stdio là `foxflow_mcp.py`. Thêm lại vào các ứng dụng AI (hộp thoại Kết nối AI sinh sẵn cấu hình mới).
- **File đổi tên**: `run_foxflow.bat`, `deploy/foxflow.service`, `deploy/nginx-foxflow.conf`, và log ghi vào `logs/foxflow_YYYYMMDD.log`.
- **Web panel**: ngôn ngữ và token đã lưu được giữ lại, không phải đăng nhập lại. Panel giờ mở ra ở Tự động hoá; bảng profile nằm ở **Profile**.

## Phát triển

```bash
pip install -r requirements-dev.txt
ruff check src tests chrome_engine
ruff format --check src tests chrome_engine
pytest                  # test cần trình duyệt thật sẽ tự bỏ qua nếu chưa tải
```

Cấu trúc thư mục, quy ước code và quy trình gửi PR nằm trong [CONTRIBUTING.md](CONTRIBUTING.md). Thay đổi giao diện theo [DESIGN.md](DESIGN.md) và sửa cả app desktop lẫn web panel. Lịch sử thay đổi: [CHANGELOG.md](CHANGELOG.md).

## Đóng góp

Mọi đóng góp đều được chào đón: báo lỗi, đề xuất tính năng, sửa tài liệu, dịch thuật hay viết code.

- Báo lỗi hoặc đề xuất: mở [issue](https://github.com/vitbau246/foxflow/issues/new/choose) theo mẫu.
- Gửi code: đọc [CONTRIBUTING.md](CONTRIBUTING.md) trước khi mở Pull Request.
- Lỗ hổng bảo mật: **không** mở issue công khai, xem [SECURITY.md](SECURITY.md).
- Mọi người tham gia cần tuân theo [Quy tắc ứng xử](CODE_OF_CONDUCT.md).

Thay đổi liên quan tới phần code gốc của FoxProfile cũng nên gửi ngược về [chienbm98/foxprofile](https://github.com/chienbm98/foxprofile).

## Lưu ý sử dụng

Chỉ tự động hoá những gì bạn được phép. Nhiều trang web cấm bot, cào dữ liệu hoặc dùng nhiều tài khoản trong điều khoản sử dụng, và dùng nhiều tài khoản trên cùng một nền tảng có thể vi phạm điều khoản của Facebook, TikTok, Google, Shopee... Hãy tôn trọng giới hạn tần suất và dữ liệu của người khác. Bạn tự chịu trách nhiệm về cách mình sử dụng phần mềm này.

## Dựa trên FoxProfile

FoxFlow là bản fork của **[FoxProfile](https://github.com/chienbm98/foxprofile)**, do **[chienbm98](https://github.com/chienbm98)** tạo ra và phát hành theo giấy phép MIT. FoxProfile xây nền móng mà FoxFlow đứng trên đó: profile trình duyệt với fingerprint cố định, hai engine Camoufox và Chrome, proxy và Kiểm tra IP, công cụ cookie, REST API, MCP server, chế độ server kèm web panel, app desktop và hệ thống thiết kế của nó.

FoxFlow đổi tên dự án, chuyển trọng tâm sang tự động hoá web (ghi và chạy lại workflow, biến, bước sinh chữ bằng AI) và tiếp tục phát triển. Các phiên bản tới 2.3.1 trong [lịch sử thay đổi](CHANGELOG.md) là bản phát hành của FoxProfile. Nếu FoxProfile có ích với bạn, hãy tặng [repo gốc](https://github.com/chienbm98/foxprofile) một ⭐ hoặc [mời tác giả một ly cà phê](https://buymeacoffee.com/chienbm98).

## Giấy phép

Phát hành theo [giấy phép MIT](LICENSE). Copyright (c) 2026 chienbm98 (FoxProfile) và 2026 vitbau246 (FoxFlow).

## Ghi công

- [FoxProfile](https://github.com/chienbm98/foxprofile) của chienbm98, dự án gốc của FoxFlow.
- Trình duyệt [Camoufox](https://github.com/daijro/camoufox) của daijro.
- [fingerprint-chromium](https://github.com/adryfish/fingerprint-chromium) của adryfish cho engine Chrome (BSD-3).
- [Playwright](https://github.com/microsoft/playwright-python), điều khiển trình duyệt khi chạy lại workflow.
- Font [Be Vietnam Pro](https://github.com/bettergui/BeVietnamPro) và [JetBrains Mono](https://github.com/JetBrains/JetBrainsMono), giấy phép SIL Open Font License (`src/assets/fonts/`).
