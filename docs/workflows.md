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
| Đồng bộ metrics | mỗi giờ | Kéo số liệu từ các kênh |
| Quét lịch đăng | mỗi 5 phút | Publish post đến hạn |
| Tổng hợp tuần | hằng tuần | Báo cáo hiệu suất |
