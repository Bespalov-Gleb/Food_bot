from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles
from starlette.responses import HTMLResponse
import asyncio
from datetime import datetime, timedelta

from app.routers import restaurants, menu, cart, orders
from app.routers import config as config_router
from app.logging_config import setup_logging, get_logger
from app.routers import admin as admin_router
from app.routers import users as users_router
from app.routers import reviews as reviews_router
from app.routers import ra as ra_router
from app.routers import ra_menu as ra_menu_router
from app.routers import auth as auth_router
from app.routers import selections as selections_router
from app.routers import collections as collections_router
from app.routers import public as public_router
from app.db_init import init_db_and_seed


setup_logging()
logger = get_logger("main")
app = FastAPI(title="Yandex Eda TG MiniApp API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"https://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def root_index() -> str:
    logger.info("healthcheck")
    return "<html><body><h3>API is running</h3></body></html>"


app.include_router(restaurants.router, prefix="/api/restaurants", tags=["restaurants"]) 
app.include_router(menu.router, prefix="/api", tags=["menu"]) 
app.include_router(cart.router, prefix="/api/cart", tags=["cart"]) 
app.include_router(orders.router, prefix="/api/orders", tags=["orders"]) 
app.include_router(config_router.router, prefix="/api", tags=["config"])
app.include_router(admin_router.router, prefix="/api/admin", tags=["admin"])
app.include_router(users_router.router, prefix="/api", tags=["users"])
app.include_router(reviews_router.router, prefix="/api", tags=["reviews"])
app.include_router(ra_router.router, prefix="/api", tags=["ra"])
app.include_router(ra_menu_router.router, prefix="/api", tags=["ra-menu"])
app.include_router(selections_router.router, prefix="/api", tags=["selections"])
app.include_router(auth_router.router, prefix="/api", tags=["auth"])
app.include_router(collections_router.router, prefix="/api/collections", tags=["collections"])
app.include_router(public_router.router, prefix="/api/public", tags=["public"])

# static for mini app prototype (built later)
app.mount("/static", StaticFiles(directory="webapp/static"), name="static")

# static for uploaded images
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

from app.db import get_session
from app.models import Order as DBOrder


async def _delivery_watchdog():
    while True:
        now = datetime.utcnow()
        try:
            with get_session() as db:
                rows = db.query(DBOrder).filter(DBOrder.status == "accepted").all()
                changed = False
                for o in rows:
                    if o.accepted_at and o.eta_minutes:
                        if now >= o.accepted_at + timedelta(minutes=o.eta_minutes):
                            o.status = "delivered"
                            changed = True
                if changed:
                    db.commit()
        except Exception:
            pass
        await asyncio.sleep(10)


@app.on_event("startup")
async def _start_watchdog():
    # init DB and seed defaults (idempotent)
    try:
        init_db_and_seed()
    except Exception as exc:
        logger.exception("db init failed: %s", repr(exc))
    asyncio.create_task(_delivery_watchdog())

