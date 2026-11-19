"""FastAPI server for CardForge."""

from __future__ import annotations

import random
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agents import simulate
from .generator import (
    DEFAULT_THEME,
    LLMConfig,
    balance_cards,
    balance_cards_with_llm,
    generate_art_prompts,
    generate_cards,
    save_card_set,
)
from .models import CardSet
from .run import Run

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = PROJECT_ROOT / "web"
CARD_DIR = PROJECT_ROOT / "data" / "cards"

app = FastAPI(title="CardForge", version="0.2.0")
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.middleware("http")
async def disable_frontend_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


class AppState:
    def __init__(self) -> None:
        self.card_set: CardSet = generate_cards(DEFAULT_THEME, count=24, allow_llm=False, seed=7)
        self.run: Run | None = None
        self.last_stats: dict[str, Any] | None = None
        self.new_run()

    def new_run(self) -> Run:
        self.run = Run(self.card_set.cards, seed=random.randint(0, 10**9))
        return self.run

    def state(self) -> dict[str, Any]:
        if self.run is None:
            self.new_run()
        assert self.run is not None
        return {"card_set": self.card_set.model_dump(), **self.run.state()}


STATE = AppState()


class GenerateRequest(BaseModel):
    theme: str = Field(default=DEFAULT_THEME, min_length=1, max_length=120)
    count: int = Field(default=24, ge=8, le=40)
    allow_llm: bool = True


class PlayRequest(BaseModel):
    index: int = Field(ge=0, le=20)


class RewardRequest(BaseModel):
    index: int = Field(ge=-1, le=2)


class ScarfRequest(BaseModel):
    index: int = Field(ge=0, le=2)


class BoonRequest(BaseModel):
    index: int = Field(ge=0, le=2)


class UpgradeRequest(BaseModel):
    index: int = Field(ge=0, le=40)


class MapRequest(BaseModel):
    index: int = Field(ge=0, le=2)


class RestRequest(BaseModel):
    index: int = Field(ge=0, le=1)


class ShopRequest(BaseModel):
    index: int = Field(ge=0, le=20)


class RemoveRequest(BaseModel):
    index: int = Field(ge=0, le=40)


class PotionRequest(BaseModel):
    index: int = Field(ge=0, le=1)


class EventRequest(BaseModel):
    index: int = Field(ge=0, le=2)


class ArtPromptRequest(BaseModel):
    use_llm: bool = True


class SimulateRequest(BaseModel):
    games: int = Field(default=200, ge=10, le=5000)
    agent: str = Field(default="heuristic", pattern="^(random|heuristic)$")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "theme": STATE.card_set.theme, "source": STATE.card_set.source}


@app.get("/api/cards")
def cards() -> dict[str, Any]:
    return STATE.card_set.model_dump()


@app.get("/api/state")
def state() -> dict[str, Any]:
    return STATE.state()


@app.post("/api/generate")
def generate(request: GenerateRequest) -> dict[str, Any]:
    card_set = generate_cards(
        request.theme,
        count=request.count,
        allow_llm=request.allow_llm,
        seed=random.randint(0, 10**9),
    )
    STATE.card_set = card_set
    STATE.last_stats = None
    STATE.new_run()
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff_-]+", "_", request.theme)[:40] or "card_set"
    save_card_set(card_set, CARD_DIR / f"{slug}.json")
    return STATE.state()


@app.post("/api/new_game")
def new_game() -> dict[str, Any]:
    STATE.new_run()
    return STATE.state()


@app.post("/api/play")
def play(request: PlayRequest) -> dict[str, Any]:
    run = STATE.run
    if run is None or run.game is None:
        raise HTTPException(status_code=400, detail="no active run")
    if run.phase != "battle":
        raise HTTPException(status_code=400, detail=f"current phase is {run.phase}")
    try:
        run.game.play_card("player", request.index)
        run.after_player_action()
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return STATE.state()


@app.post("/api/end_turn")
def end_turn() -> dict[str, Any]:
    run = STATE.run
    if run is None or run.game is None:
        raise HTTPException(status_code=400, detail="no active run")
    if run.phase != "battle":
        raise HTTPException(status_code=400, detail=f"current phase is {run.phase}")
    try:
        if not run.game.winner:
            run.game.end_turn("player")
            run.game.enemy_take_turn()
        run.after_player_action()
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return STATE.state()


@app.post("/api/run/scarf")
def choose_scarf(request: ScarfRequest) -> dict[str, Any]:
    run = STATE.run
    if run is None:
        raise HTTPException(status_code=400, detail="no active run")
    try:
        run.choose_scarf(request.index)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return STATE.state()


@app.post("/api/run/boon")
def choose_boon(request: BoonRequest) -> dict[str, Any]:
    run = STATE.run
    if run is None:
        raise HTTPException(status_code=400, detail="no active run")
    try:
        run.choose_boon(request.index)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return STATE.state()


@app.post("/api/run/map")
def choose_map(request: MapRequest) -> dict[str, Any]:
    run = STATE.run
    if run is None:
        raise HTTPException(status_code=400, detail="no active run")
    try:
        run.choose_map(request.index)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return STATE.state()


@app.post("/api/run/rest")
def choose_rest(request: RestRequest) -> dict[str, Any]:
    run = STATE.run
    if run is None:
        raise HTTPException(status_code=400, detail="no active run")
    try:
        run.choose_rest(request.index)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return STATE.state()


@app.post("/api/run/shop")
def buy_shop(request: ShopRequest) -> dict[str, Any]:
    run = STATE.run
    if run is None:
        raise HTTPException(status_code=400, detail="no active run")
    try:
        run.choose_shop(request.index)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return STATE.state()


@app.post("/api/run/potion")
def use_potion(request: PotionRequest) -> dict[str, Any]:
    run = STATE.run
    if run is None:
        raise HTTPException(status_code=400, detail="no active run")
    try:
        run.use_potion(request.index)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return STATE.state()


@app.post("/api/run/shop/reroll")
def reroll_shop() -> dict[str, Any]:
    run = STATE.run
    if run is None:
        raise HTTPException(status_code=400, detail="no active run")
    try:
        run.reroll_shop()
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return STATE.state()


@app.post("/api/run/shop/leave")
def leave_shop() -> dict[str, Any]:
    run = STATE.run
    if run is None:
        raise HTTPException(status_code=400, detail="no active run")
    try:
        run.leave_shop()
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return STATE.state()


@app.post("/api/run/remove")
def choose_remove(request: RemoveRequest) -> dict[str, Any]:
    run = STATE.run
    if run is None:
        raise HTTPException(status_code=400, detail="no active run")
    try:
        run.choose_remove(request.index)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return STATE.state()


@app.post("/api/run/event")
def choose_event(request: EventRequest) -> dict[str, Any]:
    run = STATE.run
    if run is None:
        raise HTTPException(status_code=400, detail="no active run")
    try:
        run.choose_event(request.index)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return STATE.state()


@app.post("/api/run/upgrade")
def choose_upgrade(request: UpgradeRequest) -> dict[str, Any]:
    run = STATE.run
    if run is None:
        raise HTTPException(status_code=400, detail="no active run")
    try:
        run.choose_upgrade(request.index)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return STATE.state()


@app.post("/api/run/reward")
def choose_reward(request: RewardRequest) -> dict[str, Any]:
    run = STATE.run
    if run is None:
        raise HTTPException(status_code=400, detail="no active run")
    try:
        run.choose_reward(request.index)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return STATE.state()


@app.post("/api/simulate")
def simulate_games(request: SimulateRequest) -> dict[str, Any]:
    stats = simulate(STATE.card_set.cards, games=request.games, agent=request.agent)
    STATE.last_stats = stats
    return stats


@app.post("/api/balance")
def balance() -> dict[str, Any]:
    if STATE.last_stats is None:
        raise HTTPException(status_code=400, detail="run /api/simulate first")
    balanced = None
    if LLMConfig().configured:
        balanced = balance_cards_with_llm(STATE.card_set, STATE.last_stats)
    source = "llm" if balanced is not None else "rule"
    STATE.card_set = balanced or balance_cards(STATE.card_set, STATE.last_stats)
    STATE.new_run()
    save_card_set(STATE.card_set, CARD_DIR / "balanced_latest.json")
    payload = STATE.state()
    payload["balance_source"] = source
    return payload


@app.post("/api/art-prompts")
def art_prompts(request: ArtPromptRequest) -> dict[str, Any]:
    prompts = generate_art_prompts(STATE.card_set, use_llm=request.use_llm)
    path = CARD_DIR / "art_prompts.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    import json

    path.write_text(json.dumps(prompts, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"theme": STATE.card_set.theme, "prompts": prompts, "path": str(path)}
