# LiveCap — Đánh giá & Roadmap nâng cấp

> Tài liệu này đánh giá hiện trạng LiveCap (nhánh hiện tại, xác minh 2026-07-14) và
> đề xuất lộ trình nâng cấp lên mức "cao hơn" cho 4 nhóm mục tiêu: **AI/ML**,
> **HA & scale**, **Ops & bảo mật**, **Chi phí & CI/CD**. Chưa thay đổi code —
> đây là bản kế hoạch để review trước khi triển khai.
>
> Nguyên tắc: giữ thay đổi nhỏ, có test, không tự ý deploy / apply / destroy.

---

## 1. Hiện trạng — chấm điểm

LiveCap đã ở mức gần production và vượt xa yêu cầu tối thiểu của workshop (≥3 dịch
vụ AWS, có kiến trúc, test, đo lường, tối ưu chi phí, clean-up). Bảng dưới chấm
theo đúng các trục mà rubric workshop quan tâm.

| Trục đánh giá | Điểm | Nhận xét |
|---|:--:|---|
| Kiến trúc AWS | 9/10 | CloudFront+OAC, WAF 2 lớp, VPC 2-AZ, ECS Fargate private, wake Lambda, scale-to-zero. Rất bài bản. Trừ điểm vì single-task và 1 NAT. |
| Chất lượng code | 9/10 | Backend ~3.5k dòng, 208 test; frontend 14 test; type-safe, docstring kỹ, tách service rõ ràng. |
| Bảo mật | 8/10 | IAM least-privilege, bucket private, IAM_AUTH cho wake, HTTPS/WSS, không hard-code key. Thiếu auth người dùng và một số guardrail chưa khép kín. |
| Đo lường / Observability | 6/10 | Có CloudWatch dashboard + logs. Thiếu alarm→SNS, X-Ray, Container Insights tắt, budget chưa có subscriber. |
| Tối ưu chi phí | 7/10 | Scale-to-zero, WAF rate-limit, budget $50. Còn amd64 (chưa Graviton/Spot), NAT baseline. |
| HA / Độ sẵn sàng | 4/10 | Tối đa 1 task, session in-memory → không active-active, mất session khi task chết. |
| Tính năng / Use-case | 7/10 | Real-time bilingual caption + speaker + export. Chỉ vi↔en, chưa có AI tầng cao (tóm tắt, action items). |
| Tài liệu | 10/10 | README, as-deployed, demo guide, design-flow — xuất sắc. |

**Tổng quan:** một dự án mạnh, đủ sức trình bày workshop ngay. "Nâng cấp cao hơn"
nên nhắm vào 3 khoảng trống lớn nhất theo thứ tự tác động: **HA thật**,
**AI/ML tầng cao (wow-factor)**, và **khép kín Ops/bảo mật** — kèm tối ưu chi phí
và CI/CD làm nền.

### Ghi chú kỹ thuật cần xử lý sớm
- Working tree đang hiện ~93 file "thay đổi" **chỉ do churn CRLF/LF**, không phải
  thay đổi nội dung (diff đối xứng 19902/19902, rỗng khi `--ignore-all-space`).
  Xử lý bằng `.gitattributes` (`* text=auto eol=lf`) rồi renormalize một lần, để
  tránh nhiễu review về sau. **Không commit** đống churn này.

---

## 2. Nguyên tắc & ràng buộc khi nâng cấp

- Mỗi hạng mục là một PR nhỏ, độc lập, có test, có thể rollback.
- Không phá vỡ đường request production hiện tại (blue/green nếu đụng hạ tầng).
- Không `terraform apply/destroy` hay xoá tài nguyên AWS từ CI.
- Ưu tiên thay đổi backward-compatible sau feature flag (dự án đã có sẵn pattern
  flag trong `config.py`, ví dụ `bilingual_dual_stream`, `enable_idle_scale_down`).
- Mọi hạng mục đều kèm phần **đo lường** và **clean-up** để giữ tinh thần workshop.

---

## 3. Roadmap theo 4 nhóm mục tiêu

Mỗi hạng mục ghi: **Ưu tiên** (P0 cao → P2 thấp), **Công sức** (S/M/L),
**Δ chi phí/tháng** ước tính (khu vực ap-southeast-1, mang tính tham khảo), và
**Rủi ro**.

### Nhóm A — AI/ML wow-factor (tăng chiều sâu use-case)

| # | Hạng mục | Ưu tiên | Công | Δ chi phí | Ghi chú |
|---|---|:--:|:--:|---|---|
| A1 | **Tóm tắt cuộc họp + action items bằng Amazon Bedrock** | P0 | M | ~$0.01–0.05/phiên (Claude Haiku on-demand) | Khi bấm Stop, gom transcript đã finalize → gọi Bedrock (Claude) sinh: tóm tắt, quyết định, action items, chủ đề. Hiển thị panel mới + kèm vào file export. Đây là điểm nhấn "AI/ML application" mạnh nhất. |
| A2 | **Đọc bản dịch bằng Amazon Polly (TTS / lồng tiếng)** | P2 | M | ~$4/1M ký tự (Neural) | Nút "phát" cho từng dòng dịch, hoặc auto-play. Tăng khả năng tiếp cận. Cần chú ý độ trễ real-time. |
| A3 | **Sentiment & keyword bằng Amazon Comprehend** | P2 | S | ~$0.0001/đơn vị | Gắn nhãn cảm xúc + trích từ khoá theo đoạn; hiển thị tag. Nhẹ, dễ demo. |
| A4 | **Dịch theo ngữ cảnh bằng Bedrock (tuỳ chọn thay Translate)** | P1 | M | cao hơn Translate | Dùng LLM để dịch mượt và giữ ngữ cảnh hội thoại tốt hơn Amazon Translate cho câu dài. Đặt sau feature flag, giữ Translate làm mặc định rẻ. |
| A5 | **Custom vocabulary cho Transcribe** | P1 | S | ~$0 | Cải thiện nhận dạng thuật ngữ chuyên ngành / tên riêng. Cấu hình qua Transcribe custom vocabulary. |

**Đo lường nhóm A:** log token/latency Bedrock, tỉ lệ lỗi gọi model, thời gian
sinh tóm tắt; alarm khi p95 latency vượt ngưỡng.

### Nhóm B — HA & scale thật (trưởng thành kiến trúc)

| # | Hạng mục | Ưu tiên | Công | Δ chi phí | Ghi chú |
|---|---|:--:|:--:|---|---|
| B1 | **Đưa session registry ra ngoài process** | P0 | L | DynamoDB ~$1–5 hoặc ElastiCache ~$12+ | Nút thắt chính. Thay `session_registry` in-memory bằng DynamoDB (on-demand, TTL) hoặc ElastiCache Redis. Mở đường cho >1 task. Bắt đầu bằng DynamoDB vì rẻ và serverless. |
| B2 | **Bỏ giới hạn max 1 task → auto-scaling ngang** | P0 | M | ~ theo task | Sau B1: đặt ECS desired>1, target tracking theo CPU/số session. Cập nhật per-IP/global limit để đọc từ store chung. |
| B3 | **NAT Gateway AZ thứ 2** | P1 | S | ~+$32 + data | Bỏ phụ thuộc single-AZ cho egress. Trade-off chi phí; có thể để sau flag môi trường "prod-ha". |
| B4 | **Giảm cold-start scale-to-zero** | P1 | M | thay đổi nhỏ | Lựa chọn: (a) giữ 1 task warm giờ cao điểm bằng scheduled scaling; (b) health check nhanh hơn + hình ảnh khởi động nhanh; (c) tối ưu image (xem D1 Graviton). Cân bằng chi phí vs trải nghiệm. |
| B5 | **Xử lý reconnect/session resume** | P2 | M | ~$0 | Khi task chết, cho client nối lại session cùng ID (dựa store B1) thay vì mất trắng. |

**Đo lường nhóm B:** verify wake 0→N, scale-out theo tải, task replacement không
mất session; đo p95 thời gian nối lại.

### Nhóm C — Ops & bảo mật khép kín

| # | Hạng mục | Ưu tiên | Công | Δ chi phí | Ghi chú |
|---|---|:--:|:--:|---|---|
| C1 | **Alarm → SNS (email/Slack)** cho 4xx/5xx, latency, CPU, error-rate | P0 | S | ~$0 | Hoàn thiện vòng cảnh báo. CloudWatch alarm publish vào SNS topic. |
| C2 | **Budget subscriber + cảnh báo chi phí** | P0 | S | ~$0 | Gắn subscriber email vào AWS Budget $50 hiện có (rubric yêu cầu). |
| C3 | **Retention cho log group Watchtower `livecap`** | P0 | S | giảm nhẹ | Đặt retention 14 ngày như các log group Terraform-managed khác. |
| C4 | **AWS X-Ray tracing** | P1 | M | ~$5/1M trace | Trace xuyên CloudFront→ALB→ECS→Transcribe/Translate/Bedrock để soi latency. |
| C5 | **Cognito auth + lịch sử transcript** | P1 | L | Cognito free tier rộng | Đăng nhập, lưu transcript theo user vào DynamoDB/S3, xem lại lịch sử. Nâng từ "demo" lên "sản phẩm". |
| C6 | **Secrets Manager cho cấu hình nhạy cảm** | P2 | S | ~$0.40/secret | Nếu phát sinh secret runtime (hiện đang dùng IAM role, tốt). |
| C7 | **Container Insights (bật có điều kiện)** | P2 | S | ~$ theo metric | Bật cho môi trường prod-ha để quan sát sâu; tắt ở dev để tiết kiệm. |

**Đo lường nhóm C:** trigger thử alarm, xác nhận nhận được thông báo; kiểm tra
trace xuất hiện trên X-Ray; xác minh retention áp dụng.

### Nhóm D — Chi phí & CI/CD

| # | Hạng mục | Ưu tiên | Công | Δ chi phí | Ghi chú |
|---|---|:--:|:--:|---|---|
| D1 | **Chuyển image sang Graviton (arm64)** | P1 | M | giảm ~20% compute | Build multi-arch, task definition arm64. Tiết kiệm bền vững, cải thiện cold-start. |
| D2 | **Fargate Spot cho task không critical** | P2 | S | giảm tới ~70% | Dùng capacity provider Spot có kiểm soát; cân nhắc vì session interupt. Hợp với môi trường dev/demo. |
| D3 | **S3 lifecycle & Intelligent-Tiering** | P2 | S | giảm nhẹ | Đảm bảo transcript có lifecycle (đã có 14 ngày) + tiering nếu giữ lâu hơn. |
| D4 | **CI/CD pipeline auto-deploy an toàn** | P1 | L | ~$0 (GitHub Actions) | Mở rộng `ci.yml`: build+push image immutable, `terraform plan` gate (không auto-apply), deploy có phê duyệt thủ công. Giữ nguyên tắc "không apply từ CI" mặc định. |
| D5 | **Ước tính & báo cáo chi phí tự động** | P2 | S | ~$0 | Cost Explorer tag + báo cáo định kỳ; phù hợp phần "đo lường chi phí" của workshop. |

**Đo lường nhóm D:** so sánh chi phí trước/sau Graviton; xác nhận pipeline chạy
plan mà không đụng tài nguyên runtime.

---

## 4. Lộ trình đề xuất (theo pha)

Sắp xếp để mỗi pha tạo giá trị demo được ngay và giảm rủi ro dần.

**Pha 0 — Dọn nền (0.5–1 ngày)**
C2, C3, và `.gitattributes` renormalize CRLF. Rẻ, nhanh, khép ngay vài guardrail
rubric yêu cầu.

**Pha 1 — Wow-factor AI/ML (2–4 ngày)**
A1 (tóm tắt + action items bằng Bedrock) + A5 (custom vocabulary). Đây là điểm
nhấn trình bày workshop mạnh nhất, đưa dự án vào đúng nhóm "AI/ML application".

**Pha 2 — Observability (1–2 ngày)**
C1 (alarm→SNS) + C4 (X-Ray). Hoàn thiện câu chuyện "đo lường & cảnh báo".

**Pha 3 — HA thật (4–7 ngày)**
B1 (session store ngoài) → B2 (scale ngang) → B3 (NAT AZ2) → B4 (giảm cold-start).
Pha nặng nhất về kiến trúc; làm sau khi đã có observability để verify an toàn.

**Pha 4 — Chi phí & CI/CD (2–4 ngày)**
D1 (Graviton) + D4 (pipeline plan-gate). Củng cố vận hành lâu dài.

**Pha 5 — Sản phẩm hoá (tuỳ chọn, 3–5 ngày)**
C5 (Cognito + lịch sử) + A2/A3/A4 (Polly, Comprehend, dịch bằng LLM). Nâng từ
demo lên hướng sản phẩm.

---

## 5. Kiến trúc mục tiêu (khác biệt so với hiện tại)

So với sơ đồ as-deployed hiện tại, bản nâng cấp thêm:

- **DynamoDB (session store)** — thay in-memory registry, bật multi-task.
- **Amazon Bedrock** — sinh tóm tắt/action items sau phiên (qua NAT hoặc VPC endpoint).
- **SNS + Alarms** — vòng cảnh báo chi phí/lỗi/latency.
- **X-Ray** — tracing xuyên tầng.
- **NAT Gateway AZ thứ 2** — egress multi-AZ.
- **(tuỳ chọn) Cognito** — auth + lịch sử transcript.
- **(tuỳ chọn) Polly / Comprehend** — TTS và phân tích văn bản.

Đường request nền tảng (CloudFront → ALB → ECS private → Transcribe/Translate)
giữ nguyên; các thành phần mới gắn thêm sau feature flag để không phá vỡ path hiện tại.

---

## 6. Bước tiếp theo đề xuất

Tôi đề nghị bắt đầu **Pha 0 + Pha 1** trước: dọn CRLF, gắn budget subscriber +
log retention, rồi làm tính năng tóm tắt cuộc họp bằng Bedrock (A1) — vừa an toàn,
vừa tạo điểm nhấn rõ nhất cho workshop. Nói tôi biết bạn muốn chốt pha nào để tôi
vẽ sơ đồ kiến trúc chi tiết và bắt tay implement (giữ thay đổi nhỏ, có test,
không deploy).
