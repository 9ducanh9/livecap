# LiveCap — Chốt kiến trúc AWS (theo 6 pillars Well-Architected)

Bản này tổng hợp toàn bộ kiến trúc **thực tế đang có trong repo** (Terraform +
backend boto3 calls), dùng làm nguồn để vẽ sơ đồ AWS. Region chính:
`ap-southeast-1`. CloudFront + WAF của nó là global (WAF quản qua `us-east-1`).

**Lưu ý (check trực tiếp AWS ngày 2026-07-24):** phần "preview" (2× CloudFront,
2× ECS service, 2× Lambda wake, 2× target group/listener rule) mới chỉ là
Terraform **đã viết nhưng chưa `apply`** — `aws ecs list-services` xác nhận
hiện tại chỉ có **1** ECS service (`livecap-target-service-dev`) đang chạy
thật. Các số "2×" bên dưới mô tả thiết kế trong code, không phải trạng thái
live hiện tại.

---

## 1. Đường đi request (để vẽ luồng chính)

```
Browser
  │  HTTPS + WSS
  ▼
CloudFront WAF (global, BLOCK rules + rate-limit)
  ▼
CloudFront distribution
  ├── /            → S3 frontend bucket (private, qua OAC)  [static React/Vite]
  ├── /api/wake    → Wake Lambda (Function URL, AWS_IAM, qua OAC SigV4)
  └── /api/*, /ws/*→ Regional ALB WAF → ALB (HTTPS, 2 AZ)
                        ▼  (chỉ nhận từ CloudFront prefix list)
                     ECS Fargate task (private subnet, no public IP, port 8000)
                        │
                        ├── Amazon Transcribe Streaming (vi + en, custom vocab)
                        ├── Amazon Translate
                        ├── Amazon Bedrock (Claude — meeting notes)
                        ├── Amazon Polly (TTS, English)
                        ├── Amazon Comprehend (sentiment/keywords, English)
                        ├── DynamoDB (sessions / transcript-history / usage)
                        ├── S3 transcript bucket (private, TXT export)
                        ├── Cognito IdP (validate token, admin actions)
                        └── (admin) ECS / CloudWatch / Cost Explorer / Stripe
```

Egress ra các dịch vụ AWS public từ task đi qua **NAT Gateway** (private subnet,
không có public IP).

---

## 2. Kiểm kê thành phần (nhóm theo tầng, để đặt icon)

**Edge / Global**
- CloudFront distribution (2 cái: production + preview)
- CloudFront WAFv2 Web ACL (BLOCK managed rules + rate-based)
- CloudFront Function (rewrite route SPA `/app`, `/admin` → `index.html`)
- 4 × Origin Access Control (S3 frontend, wake Lambda, …)

**Frontend hosting**
- S3 frontend bucket (private, versioning + SSE, public access block)

**Mạng (Custom VPC `10.20.0.0/16`, 2 AZ)**
- Internet Gateway
- 2 public subnet (`10.20.0.0/24` az-a, `10.20.1.0/24` az-b)
- 2 private subnet (`10.20.10.0/24` az-a, `10.20.11.0/24` az-b)
- 2 NAT Gateway + 2 EIP (multi-AZ egress)
- Route tables, security groups (ALB SG, task SG)
- VPC Flow Logs (ALL traffic → CloudWatch)

**Load balancing / compute**
- Application Load Balancer (internet-facing, HTTPS) + Regional WAFv2 Web ACL
- 2 × ALB target group, 2 listener, 1 listener rule (production + preview)
- ECS Cluster (Fargate) + capacity providers (on-demand, optional Spot)
- 2 × ECS Service + 2 × Task Definition (target + preview)
- Application Auto Scaling: target tracking CPU/memory, desired 0–1 hiện tại (`backend_max_capacity=1`), sẽ nâng sau load-test
- ECR repository (immutable Git-SHA tags) + lifecycle policy

**Wake / scale-to-zero**
- 2 × Lambda Function + Function URL (AWS_IAM) — wake backend (target + preview)
- Lambda chỉ có quyền `ecs:DescribeServices` + `ecs:UpdateService`

**Data stores**
- DynamoDB `livecap-sessions-dev` — active session registry, TTL (dùng chung khi >1 task)
- DynamoDB `livecap-transcript-history-dev` — lịch sử theo user, TTL 14 ngày
- DynamoDB `livecap-usage-dev` — quota theo tháng (pk=USER#, sk=MONTH# + PROFILE), TTL 90 ngày
- DynamoDB (thứ 4) — audit log admin (Phase 2 admin panel)
- S3 transcript bucket — export TXT, private, lifecycle 14 ngày, **không lưu audio thô**

**AI/ML managed services**
- Amazon Transcribe Streaming (+ 2 custom vocabulary vi/en)
- Amazon Translate
- Amazon Bedrock (Claude — meeting notes, gọi qua `us-east-1`)
- Amazon Polly (TTS)
- Amazon Comprehend (sentiment/keywords)

**Identity / billing**
- Cognito User Pool + App Client (PKCE, public) + Hosted UI domain + UI customization
- Cognito Identity Provider = Google (social login)
- Cognito User Group = `admin` (gate admin panel)
- Stripe (ngoài AWS) — Checkout, Customer Portal, webhook; secrets ở Secrets Manager
- Secrets Manager (2 secret: `stripe_secret_key`, `stripe_webhook_secret`)

**Observability**
- CloudWatch Logs (6 log group), Metrics, 1 Dashboard
- Container Insights (bật/tắt theo cờ), X-Ray tracing (sidecar)
- 6 CloudWatch Metric Alarm → SNS Topic (+ subscription email)
- EventBridge rule + target (GuardDuty findings → SNS)

**Security posture**
- 2 × WAFv2 Web ACL (CloudFront + ALB) + logging config
- GuardDuty detector
- Security Hub (Foundational Best Practices standard)
- VPC Flow Logs
- IAM: 5 role, 17 inline role-policy, 3 policy attachment (least-privilege)

**Cost**
- AWS Budget $50/tháng (cost guard)
- Cost Explorer (`ce`) — admin system-health cost estimate (gọi qua `us-east-1`)

---

## 3. Ánh xạ theo 6 pillars (phần chính m cần cho bài)

### Pillar 1 — Operational Excellence (Vận hành xuất sắc)
- **IaC toàn bộ bằng Terraform** — mọi resource khai báo trong `infrastructure/terraform/*.tf`, review `plan` trước khi `apply`, không deploy tay từ agent.
- **Immutable deployment**: image gắn tag Git-SHA bất biến trong ECR; rollback = trỏ lại tag cũ.
- **Observability**: CloudWatch Logs + Dashboard + Container Insights + X-Ray; 6 alarm → SNS báo email.
- **CI** (GitHub Actions): job backend test / frontend build / terraform validate / secret scan — CI không tự deploy (plan-gate thủ công).
- **COLLAB_LOG.md / HANDOFF.md**: worklog chung cho nhiều agent + người, runbook deploy.
- **Feature flags**: mọi tính năng mới mặc định OFF, bật qua biến Terraform → an toàn khi rollout.

### Pillar 2 — Security (Bảo mật)
- **Edge**: 2 lớp WAF (CloudFront + ALB) với managed BLOCK rules + rate-limit; GuardDuty + Security Hub + VPC Flow Logs.
- **Network isolation**: task chạy ở private subnet, `assign_public_ip=false`; ALB SG chỉ nhận HTTPS từ prefix list CloudFront; task SG chỉ nhận cổng 8000 từ ALB SG.
- **Private origin**: S3 frontend + transcript bucket chặn public access, truy cập qua CloudFront OAC; wake Lambda Function URL dùng `AWS_IAM` (không gọi công khai được).
- **Identity**: Cognito (email + Google OAuth, PKCE, client public không secret); token validate bằng `cognito-idp:GetUser`; admin panel gate bằng Cognito group `admin` (fail-closed).
- **Secrets**: Stripe keys ở Secrets Manager, inject vào task qua execution role — không nằm trong image/env plaintext/frontend.
- **Data**: không lưu audio thô; transcript TXT private + TTL; S3 SSE + versioning.
- **IAM least-privilege**: mỗi role có inline policy hẹp (vd wake Lambda chỉ Describe/UpdateService; admin role chỉ ListUsers/AdminListGroupsForUser + Scan + DescribeServices).

### Pillar 3 — Reliability (Độ tin cậy)
- **Multi-AZ**: VPC 2 AZ, ALB 2 public subnet, 2 NAT Gateway (egress không phụ thuộc 1 AZ), task đặt được ở cả 2 private subnet.
- **Self-healing**: ECS thay task khi fail; ALB chỉ route tới target healthy (health check `/api/health`).
- **Deployment circuit breaker + rollback** trên ECS service.
- **DynamoDB session registry** (thay in-memory) cho phép nhiều task chia sẻ trạng thái → mở đường scale >1.
- **Giới hạn hiện tại (ghi rõ để trung thực)**: khi `max=1`, WebSocket đang chạy sẽ mất nếu task bị thay — self-healing chứ chưa active-active. Nâng `backend_max_capacity` sau khi load-test.

### Pillar 4 — Performance Efficiency (Hiệu năng)
- **Serverless streaming AI**: Transcribe/Translate/Polly/Comprehend/Bedrock — managed, co giãn theo request, không tự quản node.
- **Edge caching**: CloudFront cache static React/Vite ở edge, giảm latency toàn cầu.
- **Auto Scaling** target-tracking theo CPU/memory; scale-to-zero + wake Lambda để không phí compute lúc rảnh.
- **Fargate**: chọn CPU/mem theo task; option Graviton (arm64, ~20% rẻ + hiệu năng/watt tốt) và Fargate Spot.
- **Right-sizing dữ liệu**: DynamoDB PAY_PER_REQUEST (on-demand) hợp workload bursty; TTL dọn dữ liệu cũ.

### Pillar 5 — Cost Optimization (Tối ưu chi phí)
- **Scale-to-zero**: ECS desired 0 khi không có session, wake Lambda đánh thức khi cần → không trả tiền compute lúc idle.
- **DynamoDB on-demand** + **TTL** (sessions/history 14 ngày, usage 90 ngày) → không phí lưu trữ thừa.
- **AWS Budget $50/tháng** + forecast alert; **Cost Explorer** hiển thị estimate trong admin panel.
- **CloudFront PriceClass** giới hạn edge; **S3 lifecycle** dọn transcript; **ECR lifecycle** dọn image cũ.
- **Container Insights tắt mặc định** (chỉ bật khi cần) để giảm phí metric.
- **Option Fargate Spot** cho môi trường dev/demo (rẻ tới ~70%).
- **Đánh đổi còn lại**: ALB + NAT + WAF vẫn phát sinh phí nền dù ECS ở zero.

### Pillar 6 — Sustainability (Bền vững)
- **Scale-to-zero** = không đốt compute khi rảnh → giảm năng lượng tiêu thụ trực tiếp.
- **Serverless managed AI** (Transcribe/Translate/Bedrock/Polly/Comprehend) chạy trên hạ tầng dùng chung, hiệu suất sử dụng cao hơn tự host.
- **Graviton (arm64)** option — hiệu năng trên watt tốt hơn x86.
- **TTL + lifecycle** giảm dữ liệu lưu trữ lâu dài → giảm tài nguyên lưu trữ.
- **Right-sizing** (Fargate CPU/mem nhỏ, DynamoDB on-demand) tránh cấp phát thừa.

---

## 4. Gợi ý bố cục sơ đồ (nếu vẽ 1 hình)

1. **Ngoài cùng trái**: user/browser → CloudFront WAF → CloudFront.
2. **Nhánh trên**: CloudFront → S3 frontend (OAC).
3. **Nhánh giữa**: CloudFront → Wake Lambda → ECS service (mũi tên UpdateService).
4. **Nhánh dưới (khối VPC)**: CloudFront → ALB WAF → ALB (2 public subnet) →
   Fargate task (2 private subnet) → NAT → nhóm AI services (Transcribe,
   Translate, Bedrock, Polly, Comprehend) + DynamoDB (×4) + S3 transcript.
5. **Bên phải/dưới (cross-cutting)**: Cognito, Secrets Manager, Stripe (ngoài
   AWS), CloudWatch/X-Ray/SNS, GuardDuty/SecurityHub/FlowLogs, Budget/Cost Explorer.
6. Ghi chú AZ-a / AZ-b để thể hiện multi-AZ.

> Lưu ý khi vẽ: Bedrock và Cost Explorer gọi qua **us-east-1**, phần còn lại ở
> **ap-southeast-1**; CloudFront + WAF của nó là **global**.
