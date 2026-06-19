# ✦ NoteFlow — AWS Edition

**The NoteFlow desktop app, fully migrated to AWS cloud infrastructure.**

A production-grade FastAPI backend running on ECS Fargate, backed by RDS PostgreSQL,
ElastiCache Redis, and S3 — deployed via Terraform with a full CI/CD pipeline.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                          AWS Cloud                               │
│                                                                  │
│   ┌──────────┐    ┌─────────────────────────────────────────┐   │
│   │  Route53 │───▶│          CloudFront (CDN)                │   │
│   └──────────┘    │    Static assets + attachment delivery   │   │
│                   └────────────────┬────────────────────────┘   │
│                                    │                             │
│   ┌────────────────────────────────▼────────────────────────┐   │
│   │          Application Load Balancer (HTTPS/443)           │   │
│   │              WAF rules + SSL termination                 │   │
│   └───────────────┬────────────────────────────────────────┘    │
│                   │                                              │
│   ┌───────────────▼────────────────────────────────────────┐    │
│   │                 ECS Fargate (Private Subnet)             │    │
│   │   ┌──────────┐  ┌──────────┐  ┌──────────┐            │    │
│   │   │ API Task │  │ API Task │  │ API Task │  (2–20)    │    │
│   │   │ FastAPI  │  │ FastAPI  │  │ FastAPI  │            │    │
│   │   │ Gunicorn │  │ Gunicorn │  │ Gunicorn │            │    │
│   │   └────┬─────┘  └────┬─────┘  └────┬─────┘            │    │
│   └────────┼─────────────┼─────────────┼───────────────────┘   │
│            │             │             │                         │
│   ┌────────▼─────────────▼─────────────▼─────────────────┐     │
│   │                  VPC Private Subnets                   │     │
│   │                                                        │     │
│   │   ┌──────────────────┐    ┌───────────────────────┐   │     │
│   │   │  RDS PostgreSQL  │    │  ElastiCache Redis     │   │     │
│   │   │  (Multi-AZ)      │    │  (cache + sessions)    │   │     │
│   │   └──────────────────┘    └───────────────────────┘   │     │
│   └───────────────────────────────────────────────────────┘     │
│                                                                  │
│   ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐  │
│   │  S3 (attach) │  │  S3 (export) │  │  Secrets Manager    │  │
│   │  + presigned │  │  + lifecycle │  │  DB/JWT/Redis creds  │  │
│   └──────────────┘  └──────────────┘  └─────────────────────┘  │
│                                                                  │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │  CloudWatch: Logs + Metrics + Alarms + Dashboard         │  │
│   └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Stack

| Layer            | Technology                              |
|------------------|-----------------------------------------|
| API Framework    | FastAPI + Uvicorn + Gunicorn            |
| Database         | RDS PostgreSQL 16 (Multi-AZ in prod)   |
| Cache / Sessions | ElastiCache Redis 7                     |
| File Storage     | S3 (presigned upload/download)          |
| CDN              | CloudFront                              |
| Container        | ECS Fargate (auto-scaling 2–20 tasks)  |
| Container Image  | ECR                                     |
| IaC              | Terraform 1.7+                         |
| CI/CD            | GitHub Actions                          |
| Secrets          | AWS Secrets Manager                     |
| Observability    | CloudWatch + Prometheus + Sentry        |
| Auth             | JWT (access) + refresh token rotation   |
| Migrations       | Alembic                                 |
| Search           | PostgreSQL FTS5 (tsvector)              |

---

## Project Structure

```
NoteFlow-AWS/
├── backend/
│   ├── app/
│   │   ├── api/routes/         # auth, notes, tasks, folders, search
│   │   ├── core/               # config, security, dependencies
│   │   ├── db/                 # async session, engine
│   │   ├── models/             # SQLAlchemy ORM models
│   │   ├── schemas/            # Pydantic request/response schemas
│   │   ├── services/           # note_service, s3_service
│   │   └── main.py             # FastAPI app factory
│   ├── migrations/             # Alembic migrations
│   │   └── versions/001_initial_schema.py
│   ├── tests/                  # pytest integration tests
│   ├── alembic.ini
│   ├── .env.example
│   └── requirements.txt
│
├── infrastructure/
│   ├── docker/
│   │   └── Dockerfile.api      # Multi-stage production image
│   └── terraform/
│       ├── modules/
│       │   ├── vpc/            # VPC, subnets, NAT, security groups
│       │   ├── rds/            # RDS PostgreSQL + ElastiCache Redis
│       │   ├── ecs/            # ECS cluster, ALB, task def, autoscaling
│       │   ├── s3_cloudfront/  # S3 buckets + CloudFront CDN
│       │   ├── secrets/        # Secrets Manager + KMS
│       │   └── monitoring/     # CloudWatch alarms + dashboard
│       └── environments/
│           ├── dev/            # Dev environment (minimal cost)
│           └── prod/           # Production (Multi-AZ, HA)
│
├── scripts/
│   ├── bootstrap-tfstate.sh    # One-time: creates S3 + DynamoDB for TF state
│   ├── deploy.sh               # Manual deploy helper
│   └── localstack-init.sh      # Creates local S3 buckets
│
├── .github/workflows/
│   └── deploy.yml              # CI: test → build → push → migrate → deploy
│
└── docker-compose.yml          # Local dev: API + Postgres + Redis + LocalStack
```

---

## Quick Start — Local Development

### Prerequisites
- Docker Desktop
- Python 3.12
- AWS CLI (for scripts)

### 1. Start local services

```bash
# Starts: API (hot-reload), PostgreSQL, Redis, LocalStack (S3)
docker compose up -d

# Check everything is healthy
docker compose ps
docker compose logs api -f
```

### 2. API is running at

| Service    | URL                              |
|------------|----------------------------------|
| API        | http://localhost:8000            |
| Docs       | http://localhost:8000/docs       |
| Health     | http://localhost:8000/health     |
| pgAdmin    | http://localhost:5050 (optional) |

To enable pgAdmin and Redis Commander:
```bash
docker compose --profile tools up -d
```

### 3. Run tests locally

```bash
cd backend
pip install -r requirements.txt pytest pytest-asyncio httpx aiosqlite
pytest tests/ -v
```

---

## AWS Deployment

### Prerequisites

- Terraform 1.7+
- AWS CLI configured (`aws configure`)
- A registered domain in Route53 (optional)
- An ACM certificate for your domain

### Step 1 — Bootstrap Terraform state backend

```bash
chmod +x scripts/*.sh
./scripts/bootstrap-tfstate.sh dev us-east-1
./scripts/bootstrap-tfstate.sh prod us-east-1
```

### Step 2 — Configure environment

```bash
# Copy and edit the tfvars file
cp infrastructure/terraform/environments/prod/terraform.tfvars.example \
   infrastructure/terraform/environments/prod/terraform.tfvars

# Edit with your values:
#   aws_account_id, domain_name, acm_certificate_arn, etc.
```

### Step 3 — Deploy infrastructure

```bash
cd infrastructure/terraform/environments/prod
terraform init
terraform plan  -out=tfplan
terraform apply tfplan
```

Terraform outputs the ECR URL, ALB DNS, and CloudFront domain.

### Step 4 — Build & push first image

```bash
chmod +x scripts/deploy.sh
./scripts/deploy.sh prod
```

### Step 5 — Set up CI/CD

Add these secrets to your GitHub repository:

| Secret                   | Value                              |
|--------------------------|------------------------------------|
| `AWS_ACCESS_KEY_ID`      | IAM user key for CI/CD             |
| `AWS_SECRET_ACCESS_KEY`  | IAM user secret                    |
| `AWS_ACCOUNT_ID_PROD`    | Your production AWS account ID     |
| `AWS_ACCOUNT_ID_DEV`     | Your dev AWS account ID            |
| `PRIVATE_SUBNET_IDS`     | Comma-separated private subnet IDs |
| `ECS_SG_ID`              | ECS security group ID              |
| `API_DOMAIN`             | Your API domain (api.noteflow.app) |

Push to `develop` → deploys to dev.
Push to `main` → deploys to production.

---

## API Reference

### Authentication

```
POST /api/v1/auth/register    Register new user
POST /api/v1/auth/login       Login → access + refresh tokens
POST /api/v1/auth/refresh     Rotate refresh token
POST /api/v1/auth/logout      Revoke refresh token
GET  /api/v1/auth/me          Current user profile
```

### Notes

```
GET    /api/v1/notes                List notes (folder, tag, archived filters)
POST   /api/v1/notes                Create note
GET    /api/v1/notes/search?q=      Full-text search
GET    /api/v1/notes/trash          Deleted notes
GET    /api/v1/notes/{id}           Get note with attachments + presigned URLs
PATCH  /api/v1/notes/{id}           Update (title, content, folder, color, pin)
DELETE /api/v1/notes/{id}           Soft delete (or ?permanent=true)
POST   /api/v1/notes/{id}/pin       Pin/unpin
POST   /api/v1/notes/{id}/archive   Archive/unarchive
POST   /api/v1/notes/{id}/tags/{name}  Add tag
DELETE /api/v1/notes/{id}/tags/{id}    Remove tag
POST   /api/v1/notes/{id}/attachments/presign  Get S3 presigned upload URL
GET    /api/v1/notes/{id}/export/{format}      Export (txt/md/pdf) → S3 URL
```

### Tasks

```
GET    /api/v1/tasks             List tasks (project, status, priority filters)
POST   /api/v1/tasks             Create task
GET    /api/v1/tasks/kanban      Board view grouped by column
GET    /api/v1/tasks/today       Today's tasks
GET    /api/v1/tasks/overdue     Overdue tasks
GET    /api/v1/tasks/{id}        Get task with subtasks
PATCH  /api/v1/tasks/{id}        Update task
POST   /api/v1/tasks/{id}/complete  Mark done + handle recurrence
POST   /api/v1/tasks/{id}/move?column=  Move on Kanban
DELETE /api/v1/tasks/{id}        Delete task + subtasks
```

### Other

```
GET/POST/PATCH/DELETE  /api/v1/folders/{id}
GET/POST/DELETE        /api/v1/tags/{id}
GET/POST/PATCH/DELETE  /api/v1/projects/{id}
GET                    /api/v1/search?q=       Global search (notes + tasks)
GET                    /api/v1/stats           User statistics
GET                    /health                 Full health check
GET                    /ready                  Readiness probe
```

---

## Key Design Decisions

### Security
- **JWT access tokens** (15-min to 24-hour expiry, configurable)
- **Refresh token rotation** — every refresh issues a new pair, old token revoked
- **All data scoped to user_id** — impossible to access another user's data
- **Passwords hashed with bcrypt** (cost factor 12)
- **Secrets in AWS Secrets Manager** — never in environment variables directly
- **S3 presigned URLs** — clients upload/download directly, API never proxies files

### Performance
- **Async SQLAlchemy** — non-blocking DB queries throughout
- **PostgreSQL FTS** — `tsvector` + `GIN` index, updated by trigger
- **Connection pooling** — 20 connections per ECS task, pre-ping enabled
- **Redis caching** — ready for session cache, rate limiting, hot data
- **Gzip middleware** — responses compressed automatically

### Reliability
- **RDS Multi-AZ** in production — automatic failover in < 60s
- **ECS deployment circuit breaker** — auto-rollback on failed deploy
- **ALB health checks** — unhealthy tasks replaced automatically
- **Alembic migrations** run as a separate ECS task before deploy
- **CloudWatch alarms** — SNS email alert on 5xx spike, high CPU, low disk

### Cost Optimisation (dev)
- Single-AZ RDS (`db.t4g.micro`)
- Single Redis node (`cache.t4g.micro`)
- 1 ECS task, FARGATE_SPOT eligible
- 7-day log retention
- Estimated dev cost: **~$45/month**

### Cost Optimisation (prod)
- Multi-AZ RDS (`db.t4g.medium`) + read replica optional
- Redis 1 replica (`cache.t4g.small`)
- 2 ECS tasks baseline, scales to 20
- Estimated prod cost: **~$120–200/month** at low traffic

---

## Environment Variables Reference

| Variable                | Description                          | Required |
|-------------------------|--------------------------------------|----------|
| `DATABASE_HOST`         | RDS endpoint                         | ✓        |
| `DATABASE_PASSWORD`     | DB password (from Secrets Manager)   | ✓        |
| `SECRET_KEY`            | JWT signing key (from Secrets Mgr)  | ✓        |
| `REDIS_HOST`            | ElastiCache endpoint                 | ✓        |
| `S3_BUCKET_ATTACHMENTS` | S3 bucket for file attachments       | ✓        |
| `S3_BUCKET_EXPORTS`     | S3 bucket for note exports           | ✓        |
| `AWS_REGION`            | AWS region                           | ✓        |
| `SECRETS_MANAGER_ARN`   | ARN to pull secrets from at startup  | prod     |
| `SENTRY_DSN`            | Sentry error tracking DSN            | optional |
| `SES_FROM_EMAIL`        | SES sender for email notifications   | optional |
| `ALLOWED_ORIGINS`       | JSON array of allowed CORS origins   | ✓        |
