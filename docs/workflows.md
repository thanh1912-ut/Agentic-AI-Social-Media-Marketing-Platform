# Workflows

## 1. Onboarding thương hiệu

```
Upload tài liệu → services/ingestion → brand knowledge base
```

## 2. Sinh chiến dịch (agentic)

```
orchestrator
  ├── research_agent      → insight thị trường / đối thủ
  ├── strategy_agent      → định vị, thông điệp, kênh
  ├── content_agent       → caption / script / asset brief
  ├── review_agent        → kiểm tra brand voice, compliance
  └── recommendation_agent→ gợi ý tối ưu
        ↓
      posts (draft) → approvals
```

## 3. Xuất bản & theo dõi

```
approvals (approved) → services/worker/publishing → kênh social
                     → services/worker/monitoring  → metrics
                     → analytics_agent             → báo cáo
```

## 4. Job định kỳ — `services/worker/scheduled_jobs`

| Job | Tần suất | Mô tả |
| --- | --- | --- |
| Đồng bộ metrics | theo mốc +1h,+6h,+12h,+24h,+3d,+7d rồi hằng ngày đến ngày 30 | Kéo số liệu từ các kênh khi capability cho phép; đây là lịch fetch, không cam kết realtime |
| Quét lịch đăng | mỗi phút | Publish post đến hạn sau khi worker kiểm lại approval/version/Page |
| Tìm nghiên cứu thị trường đến hạn | mỗi phút | Đọc `next_due_at` từ PostgreSQL; mỗi cycle lưu job/report và lịch kế tiếp 12 giờ, không đặt task chờ 12 giờ trong Redis |
| Tổng hợp tuần | hằng tuần | Báo cáo hiệu suất |

Scheduler quét PostgreSQL để khôi phục job quá lease; Redis restart không xoá lịch.
