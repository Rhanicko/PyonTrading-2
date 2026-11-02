from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.adapters.mt5 import MT5Adapter
from app.adapters.calendar import ForexFactoryCalendarAdapter
from app.adapters.official_macro import OfficialMacroScheduleAdapter
from app.api.routes import router
from app.config import PROJECT_ROOT, settings
from app.services.live import LiveService
from app.services.backtest import BacktestCoordinator
from app.services.research import ResearchCoordinator
from app.services.pipeline import ResearchPipeline
from app.services.cross_market import CrossMarketContextService, CrossMarketSymbols
from app.services.source_setup import SourceSetupService
from app.storage.database import initialize_database, read_settings


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database(settings.database_path)
    stored = read_settings(settings.database_path)
    app.state.database_path = settings.database_path
    adapter = MT5Adapter()
    launch_started, launch_status = adapter.start_terminal_at_startup()
    app.state.mt5_startup = {"launch_started": launch_started, "status": launch_status}
    if launch_started:
        logger.info("MT5 terminal launch requested at PyonTrading startup")
    elif launch_status not in {"MT5_TERMINAL_ALREADY_RUNNING", "MT5_AUTO_START_UNAVAILABLE"}:
        logger.warning("MT5 terminal was not started at PyonTrading startup: %s", launch_status)
    app.state.live_service = LiveService(adapter, stored.get("symbol") or settings.symbol, settings.database_path)
    app.state.calendar_service = ForexFactoryCalendarAdapter(settings.calendar_url, settings.calendar_ttl_seconds, settings.database_path)
    app.state.official_macro_service = OfficialMacroScheduleAdapter(ttl_seconds=settings.official_macro_ttl_seconds)
    app.state.cross_market_service = CrossMarketContextService(
        app.state.live_service.adapter,
        CrossMarketSymbols(
            dxy=stored["dxy_symbol"] if "dxy_symbol" in stored else settings.dxy_symbol,
            us10y=stored["us10y_symbol"] if "us10y_symbol" in stored else settings.us10y_symbol,
            wti=stored["wti_symbol"] if "wti_symbol" in stored else settings.wti_symbol,
            volatility=stored["volatility_symbol"] if "volatility_symbol" in stored else settings.volatility_symbol,
        ),
    )
    app.state.research_service = ResearchCoordinator(
        app.state.live_service.adapter, app.state.calendar_service, settings.database_path,
        app.state.official_macro_service, app.state.cross_market_service,
    )
    app.state.source_setup_service = SourceSetupService(
        app.state.live_service.adapter, app.state.calendar_service, settings.database_path,
        app.state.cross_market_service,
    )
    app.state.backtest_service = BacktestCoordinator(app.state.live_service.adapter, settings.database_path)
    app.state.research_pipeline = ResearchPipeline(
        app.state.live_service.adapter,
        app.state.calendar_service,
        app.state.research_service,
        settings.database_path,
        lambda: app.state.live_service.configured_symbol,
        app.state.official_macro_service,
    )
    await app.state.live_service.start()
    await app.state.research_pipeline.start()
    try:
        yield
    finally:
        try:
            await app.state.research_pipeline.stop()
        finally:
            await app.state.live_service.stop()


app = FastAPI(title="PyonTrading 2", version="0.1.0", lifespan=lifespan)
app.include_router(router)


@app.middleware("http")
async def prevent_api_caching(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.websocket("/ws/live")
async def live_socket(websocket: WebSocket):
    live = websocket.app.state.live_service
    await live.register(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        live.unregister(websocket)

if settings.frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=settings.frontend_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str):
        index = settings.frontend_dist / "index.html"
        return FileResponse(index)
else:
    @app.get("/", include_in_schema=False)
    async def missing_frontend():
        return {"message": "Frontend assets are not built. Run .\\setup.ps1 from the project root.", "project_root": str(PROJECT_ROOT)}

