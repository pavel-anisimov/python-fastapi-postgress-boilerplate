from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, items, users, admin

import os

app = FastAPI(title="Boilerplate API")

# from .env, comma-separated. example: CORS_ORIGINS=http://localhost:5173,https://your-frontend.app
origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(items.router)
app.include_router(users.router)
app.include_router(admin.router)

@app.get("/health")
def health(): return {"status": "ok"}