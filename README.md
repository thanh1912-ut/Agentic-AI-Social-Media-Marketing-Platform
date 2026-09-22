# Agentic AI Social Media Marketing Platform

Nền tảng marketing mạng xã hội ứng dụng Agentic AI: ingest tài liệu thương hiệu → research → strategy → content → review → publish → analytics → recommendation.

## Kiến trúc tổng quan

```
apps/web                 Next.js frontend
services/api             FastAPI backend (auth, campaigns, posts, approvals, exports, integrations)
services/ingestion       Xử lý PDF / Excel / Doc / Image / Video / URL
services/agents          LangGraph agents (orchestrator + 7 agent chuyên trách)
services/worker          Background jobs (publishing, monitoring, scheduled_jobs)
packages/contracts       Shared request/response schema
packages/prompts         Prompt templates
packages/shared          Constants / utilities
database                 migrations, seeds, schema
infra                    docker, docker-compose
tests                    integration, e2e
docs                     architecture, api-contracts, workflows
```

## Bắt đầu

```bash
cp .env.example .env
docker compose up -d
```

## Tài liệu

- [Kiến trúc](docs/architecture.md)
- [API contracts](docs/api-contracts.md)
- [Workflows](docs/workflows.md)
