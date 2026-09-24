FRONTEND_DIR ?= frontend
FRONTEND_DIST ?= $(CURDIR)/backend/static

.PHONY: help frontend-build backend dev

help:
	@echo "make frontend-build  构建 Next.js 前端并复制到指定目录"
	@echo "make backend         启动后端"
	@echo "make dev             构建前端、准备静态文件并启动后端"
	@echo ""
	@echo "可覆盖变量："
	@echo "  FRONTEND_DIR=frontend"
	@echo "  FRONTEND_DIST=backend/static"

frontend-build:
	cd $(FRONTEND_DIR) && npm install && npm run build
	rm -rf $(FRONTEND_DIST)
	mkdir -p $(FRONTEND_DIST)
	cp -r $(FRONTEND_DIR)/out/. $(FRONTEND_DIST)/

backend:
	cd backend && uv run uvicorn app:app --host 0.0.0.0 --port 8000

dev: frontend-build backend
