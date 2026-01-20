import sys
import asyncio

# FIX: Windows requires ProactorEventLoop for subprocess support (needed by Playwright)
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from src.api.routes import router
import uvicorn

app = FastAPI(title="InsightX API")

# API Routes
app.include_router(router, prefix="/api")

# Static Files (Frontend)
# Mount static files to root "/" to serve index.html by default
app.mount("/", StaticFiles(directory="src/static", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
