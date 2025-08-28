# app/main.py (верх)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import auth, items

app = FastAPI(title="Boilerplate API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # add your front domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(items.router)

@app.get("/health")
def health(): return {"status": "ok"}

