backend:
	cd backend && uvicorn app:app --reload --host 0.0.0.0 --port 8000
frontend:
	cd frontend && npm run dev
