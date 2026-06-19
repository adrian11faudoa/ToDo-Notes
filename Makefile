# NoteFlow AWS — Developer Makefile
# Usage: make <target>
# Run `make help` to see all available commands.

.PHONY: help up down logs shell test lint format migrate build push deploy-dev deploy-prod tf-init tf-plan tf-apply tf-destroy clean

SHELL       := /bin/bash
ENV         ?= dev
AWS_REGION  ?= us-east-1
IMAGE_TAG   ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo latest)

# Colours
GREEN  := \033[0;32m
YELLOW := \033[1;33m
RESET  := \033[0m

##@ Help

help: ## Show this help message
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} \
	/^[a-zA-Z_0-9-]+:.*?##/ { printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2 } \
	/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Local Development

up: ## Start full local stack (API + Postgres + Redis + LocalStack)
	@echo "$(GREEN)Starting local stack...$(RESET)"
	docker compose up -d
	@echo "$(GREEN)✓ Stack running at http://localhost:8000$(RESET)"
	@echo "  Docs: http://localhost:8000/docs"

up-tools: ## Start stack + pgAdmin + Redis Commander
	docker compose --profile tools up -d

down: ## Stop all local services
	docker compose down

logs: ## Tail API logs
	docker compose logs -f api

logs-all: ## Tail all service logs
	docker compose logs -f

shell: ## Open a shell inside the API container
	docker compose exec api bash

db-shell: ## Connect to local PostgreSQL
	docker compose exec postgres psql -U noteflow -d noteflow

redis-cli: ## Connect to local Redis
	docker compose exec redis redis-cli -a dev_redis_password

status: ## Show running containers and their health
	docker compose ps

restart: ## Restart the API container (picks up code changes without full rebuild)
	docker compose restart api

##@ Testing

test: ## Run all tests
	@echo "$(GREEN)Running tests...$(RESET)"
	cd backend && pytest tests/ -v

test-cov: ## Run tests with coverage report
	cd backend && pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=html
	@echo "$(GREEN)Coverage report: backend/htmlcov/index.html$(RESET)"

test-fast: ## Run tests excluding slow/integration tests
	cd backend && pytest tests/ -v -m "not slow and not integration"

test-watch: ## Run tests in watch mode (requires pytest-watch)
	cd backend && ptw tests/ -- -v

##@ Code Quality

lint: ## Run ruff linter
	cd backend && ruff check app/ tests/

lint-fix: ## Run ruff linter with auto-fix
	cd backend && ruff check --fix app/ tests/

format: ## Format code with ruff
	cd backend && ruff format app/ tests/

typecheck: ## Run mypy type checker
	cd backend && mypy app/

quality: lint typecheck ## Run all quality checks

##@ Database Migrations

migrate: ## Run pending Alembic migrations (local)
	cd backend && alembic upgrade head

migrate-down: ## Roll back last migration (local)
	cd backend && alembic downgrade -1

migrate-status: ## Show current migration status
	cd backend && alembic current

migrate-history: ## Show migration history
	cd backend && alembic history --verbose

migrate-new: ## Create a new migration (NAME=my_migration)
	@test -n "$(NAME)" || (echo "Usage: make migrate-new NAME=my_migration" && exit 1)
	cd backend && alembic revision --autogenerate -m "$(NAME)"

##@ Docker Build

build: ## Build the Docker image locally
	@echo "$(GREEN)Building Docker image (tag: $(IMAGE_TAG))...$(RESET)"
	docker build \
		--file infrastructure/docker/Dockerfile.api \
		--tag noteflow-api:$(IMAGE_TAG) \
		--tag noteflow-api:latest \
		--build-arg GIT_SHA=$(IMAGE_TAG) \
		backend/

build-no-cache: ## Build Docker image without cache
	docker build \
		--file infrastructure/docker/Dockerfile.api \
		--tag noteflow-api:$(IMAGE_TAG) \
		--no-cache \
		backend/

##@ AWS Deployment

ecr-login: ## Authenticate Docker to ECR
	@AWS_ACCOUNT_ID=$$(aws sts get-caller-identity --query Account --output text) && \
	aws ecr get-login-password --region $(AWS_REGION) | \
	  docker login --username AWS --password-stdin \
	  $${AWS_ACCOUNT_ID}.dkr.ecr.$(AWS_REGION).amazonaws.com
	@echo "$(GREEN)✓ ECR login successful$(RESET)"

push: ecr-login build ## Build and push image to ECR
	@AWS_ACCOUNT_ID=$$(aws sts get-caller-identity --query Account --output text) && \
	ECR_URL="$${AWS_ACCOUNT_ID}.dkr.ecr.$(AWS_REGION).amazonaws.com/noteflow-$(ENV)/api" && \
	docker tag noteflow-api:$(IMAGE_TAG) $${ECR_URL}:$(IMAGE_TAG) && \
	docker tag noteflow-api:$(IMAGE_TAG) $${ECR_URL}:latest && \
	docker push $${ECR_URL}:$(IMAGE_TAG) && \
	docker push $${ECR_URL}:latest && \
	echo "$(GREEN)✓ Pushed $${ECR_URL}:$(IMAGE_TAG)$(RESET)"

deploy-dev: ## Full deploy to dev environment
	@echo "$(YELLOW)Deploying to DEV...$(RESET)"
	ENV=dev ./scripts/deploy.sh dev

deploy-prod: ## Full deploy to production (requires confirmation)
	@echo "$(YELLOW)You are about to deploy to PRODUCTION.$(RESET)"
	@read -p "Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ] || (echo "Aborted." && exit 1)
	ENV=prod ./scripts/deploy.sh prod

##@ Terraform

tf-bootstrap: ## Create Terraform state backend (run once per account)
	./scripts/bootstrap-tfstate.sh $(ENV) $(AWS_REGION)

tf-init: ## Initialise Terraform for ENV
	cd infrastructure/terraform/environments/$(ENV) && terraform init

tf-plan: ## Plan Terraform changes for ENV
	cd infrastructure/terraform/environments/$(ENV) && \
	  terraform plan -var-file=terraform.tfvars -out=tfplan

tf-apply: ## Apply Terraform plan for ENV
	cd infrastructure/terraform/environments/$(ENV) && \
	  terraform apply tfplan

tf-apply-auto: ## Apply Terraform without interactive approval (CI use)
	cd infrastructure/terraform/environments/$(ENV) && \
	  terraform apply -var-file=terraform.tfvars -auto-approve

tf-destroy: ## DESTROY all resources for ENV (dangerous!)
	@echo "$(YELLOW)WARNING: This will DESTROY all $(ENV) infrastructure!$(RESET)"
	@read -p "Type 'destroy' to confirm: " confirm && [ "$$confirm" = "destroy" ] || (echo "Aborted." && exit 1)
	cd infrastructure/terraform/environments/$(ENV) && \
	  terraform destroy -var-file=terraform.tfvars

tf-output: ## Show Terraform outputs for ENV
	cd infrastructure/terraform/environments/$(ENV) && terraform output

tf-validate: ## Validate all Terraform modules
	@for dir in $$(find infrastructure/terraform -name "*.tf" -exec dirname {} \; | sort -u); do \
	  echo "Validating $$dir..."; \
	  terraform -chdir=$$dir validate 2>/dev/null || true; \
	done

tf-fmt: ## Format all Terraform files
	terraform fmt -recursive infrastructure/terraform/

##@ Utilities

secrets-view: ## View current app secrets from AWS Secrets Manager (ENV=dev|prod)
	@SECRET_ARN=$$(cd infrastructure/terraform/environments/$(ENV) && terraform output -raw secrets_arn 2>/dev/null) && \
	aws secretsmanager get-secret-value --secret-id "$$SECRET_ARN" --query SecretString --output text | jq .

secrets-rotate: ## Force rotation of app secrets in Secrets Manager
	@echo "Triggering secret rotation for $(ENV)..."
	@SECRET_ARN=$$(cd infrastructure/terraform/environments/$(ENV) && terraform output -raw secrets_arn 2>/dev/null) && \
	aws secretsmanager rotate-secret --secret-id "$$SECRET_ARN"

ecs-exec: ## Open a shell in a running ECS task (ENV=dev|prod)
	@CLUSTER=$$(cd infrastructure/terraform/environments/$(ENV) && terraform output -raw cluster_name 2>/dev/null || echo "noteflow-$(ENV)-cluster") && \
	TASK=$$(aws ecs list-tasks --cluster $$CLUSTER --query 'taskArns[0]' --output text) && \
	echo "Connecting to task $$TASK in cluster $$CLUSTER..." && \
	aws ecs execute-command \
	  --cluster $$CLUSTER \
	  --task $$TASK \
	  --container api \
	  --interactive \
	  --command "/bin/bash"

tail-logs: ## Tail ECS API logs from CloudWatch (ENV=dev|prod)
	aws logs tail "/ecs/noteflow-$(ENV)/api" --follow --format short

db-migrate-prod: ## Run migrations in production ECS (via run-task)
	@echo "$(YELLOW)Running migrations in PRODUCTION...$(RESET)"
	@read -p "Confirm? (yes/no): " c && [ "$$c" = "yes" ] || exit 1
	./scripts/deploy.sh prod migrate-only

install: ## Install backend dependencies locally
	pip install -r backend/requirements.txt
	pip install pytest pytest-asyncio pytest-cov httpx aiosqlite ruff mypy

clean: ## Remove all generated/temp files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -name "coverage.xml" -delete 2>/dev/null || true
	find . -name "tfplan" -delete 2>/dev/null || true
	@echo "$(GREEN)✓ Cleaned$(RESET)"
