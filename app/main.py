import pathlib
import time

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import models, query_loader
from .database import engine
from .routers import (
    cf_module_router,
    context_router,
    global_messages_router,
    onec_router,
    token_router,
    users_router,
)

load_dotenv(pathlib.Path(__file__).parent.parent / ".env", override=True)

models.Base.metadata.create_all(bind=engine)
query_loader.load_queries()

app = FastAPI(title="VPS API Confirmation Server", debug=True)

app.mount("/html", StaticFiles(directory="html", html=True), name="html")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _timing_middleware(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time"] = str(int((time.time() - t0) * 1000))
    return response


app.include_router(context_router.router)
app.include_router(token_router.router)
app.include_router(users_router.router)
app.include_router(onec_router.router)
app.include_router(global_messages_router.router)
app.include_router(cf_module_router.router)