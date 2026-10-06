<h1 align="center">LiveCap</h1>

<p align="center"><a href="README.md">English</a> · Tiếng Việt</p>

<p align="center">Phụ đề song ngữ trực tiếp. Phòng chia sẻ. Bản ghi để lưu lại.</p>

<p align="center">
  <a href="https://livecap.logantai.com/app">Mở ứng dụng</a> ·
  <a href="docs/as-deployed-architecture.md">Kiến trúc</a> ·
  <a href="docs/benchmark-phase5-results.md">Benchmark thực tế</a> ·
  <a href="docs/README.md">Tài liệu</a>
</p>

<p align="center">
  <img alt="React + TypeScript" src="https://img.shields.io/badge/React-TypeScript-61DAFB?style=flat&amp;logo=react&amp;logoColor=61DAFB&amp;labelColor=16243a" />
  <img alt="FastAPI + WebSocket" src="https://img.shields.io/badge/FastAPI-WebSocket-54CC99?style=flat&amp;logo=fastapi&amp;logoColor=54CC99&amp;labelColor=16243a" />
  <img alt="AWS ECS Fargate" src="https://img.shields.io/badge/AWS-ECS_Fargate-FF9900?style=flat&amp;labelColor=16243a" />
</p>

LiveCap chuyển lời nói tiếng Việt và tiếng Anh thành phụ đề song ngữ trực tiếp.
Người chủ trì có thể chia sẻ phòng để người xem theo dõi phụ đề đã chốt trên
thiết bị riêng, rồi lưu bản ghi sau phiên.

![Demo LiveCap](docs/livecap-demo-small.gif)

[Demo có độ phân giải cao hơn](docs/livecap-demo.gif)

## Tính năng

| Phụ đề song ngữ | Phòng người xem | Xuất bản ghi |
|---|---|---|
| Chuyển âm thanh từ micro hoặc tab được chia sẻ thành phụ đề tiếng Việt và tiếng Anh trực tiếp. | Chia sẻ liên kết, mã phòng hoặc mã QR để người xem theo dõi phụ đề đã chốt trên thiết bị riêng. | Lưu bản ghi TXT riêng tư sau khi cuộc trò chuyện kết thúc. |

GIF minh họa giao diện ứng dụng; báo cáo benchmark được liên kết ở trên sử dụng
một tệp âm thanh thu sẵn riêng biệt.

## Cách hoạt động

Trình duyệt truyền âm thanh qua WebSocket. Transcribe và Translate tạo phụ đề
song ngữ rồi trả về qua cùng kết nối. Cognito xử lý đăng nhập; một hàm Lambda
đánh thức backend khi số task đã giảm về 0 do không hoạt động.
**Ứng dụng không lưu âm thanh gốc.**

Xem [kiến trúc đang triển khai](docs/as-deployed-architecture.md) để tìm hiểu
luồng yêu cầu và các ranh giới bảo mật.

## Chạy cục bộ

Frontend dùng React, TypeScript và Vite; backend dùng Python và FastAPI.
Làm theo [hướng dẫn chạy cục bộ](docs/run-local.md) để cài đặt và cấu hình AWS.
[Mục lục tài liệu](docs/README.md) có hướng dẫn demo, kiến trúc và ghi chú vận hành.

Các tài liệu kỹ thuật được liên kết hiện viết bằng tiếng Anh.
