#!/usr/bin/env python3
"""Auto-open Lichess and play moves automatically.

This script is intended for casual play vs the built-in computer only.
Do not use it in rated games or where automation is prohibited.
"""

from __future__ import annotations

import argparse
import random
import time
from dataclasses import dataclass

import chess
from playwright.sync_api import BrowserContext, Page, sync_playwright


FILES = "abcdefgh"
RANKS = "12345678"


@dataclass
class BotConfig:
    level: int = 1
    move_delay: float = 1.2
    think_spread: float = 0.8
    headless: bool = False
    cdp_url: str | None = None


def square_to_coord(square: chess.Square, orientation_white: bool = True) -> tuple[float, float]:
    file_idx = chess.square_file(square)
    rank_idx = chess.square_rank(square)
    if orientation_white:
        x = file_idx + 0.5
        y = 7.5 - rank_idx
    else:
        x = 7.5 - file_idx
        y = rank_idx + 0.5
    return x, y


def uci_from_san_list(san_moves: list[str]) -> chess.Board:
    board = chess.Board()
    for san in san_moves:
        san = san.strip()
        if not san:
            continue
        try:
            board.push_san(san)
        except ValueError:
            # Ignore temporary / malformed entries while the UI is updating.
            pass
    return board


def fetch_san_moves(page: Page) -> list[str]:
    script = """
    () => {
      const nodes = Array.from(document.querySelectorAll('.vertical-move-list san, kwdb san'));
      return nodes.map(n => (n.textContent || '').trim()).filter(Boolean);
    }
    """
    return page.evaluate(script)


def detect_bot_color(page: Page) -> chess.Color:
    script = """
    () => {
      const board = document.querySelector('cg-board');
      if (!board) return 'white';
      const cls = board.className || '';
      return cls.includes('orientation-black') ? 'black' : 'white';
    }
    """
    return chess.BLACK if page.evaluate(script) == "black" else chess.WHITE


def click_square(page: Page, square: chess.Square, orientation_white: bool) -> None:
    board = page.locator("cg-board")
    box = board.bounding_box()
    if not box:
        raise RuntimeError("Could not locate chess board.")

    x_unit, y_unit = square_to_coord(square, orientation_white=orientation_white)
    x = box["x"] + box["width"] * (x_unit / 8)
    y = box["y"] + box["height"] * (y_unit / 8)
    page.mouse.click(x, y, delay=30)


def play_move(page: Page, move: chess.Move, orientation_white: bool) -> None:
    click_square(page, move.from_square, orientation_white)
    time.sleep(0.05)
    click_square(page, move.to_square, orientation_white)


def choose_move(board: chess.Board) -> chess.Move:
    # Lightweight policy: prefer captures/checks to look less random.
    legal = list(board.legal_moves)
    random.shuffle(legal)

    tactical: list[chess.Move] = []
    for mv in legal:
        if board.is_capture(mv):
            tactical.append(mv)
            continue
        board.push(mv)
        gives_check = board.is_check()
        board.pop()
        if gives_check:
            tactical.append(mv)

    pool = tactical or legal
    return random.choice(pool)


def wait_for_board(page: Page) -> None:
    page.wait_for_selector("cg-board", timeout=30_000)


def open_vs_ai(context: BrowserContext, level: int) -> Page:
    page = context.new_page()
    page.goto("https://lichess.org/?any#ai", wait_until="domcontentloaded")

    # Start from lobby fallback if direct hash route changes.
    if "lichess.org" not in page.url:
        page.goto("https://lichess.org/", wait_until="domcontentloaded")

    try:
        page.get_by_role("link", name="Play with the computer").click(timeout=10_000)
    except Exception:
        page.goto("https://lichess.org/?any#ai", wait_until="domcontentloaded")

    # Set AI level if control exists.
    try:
        slider = page.locator("input[type='range']").first
        if slider.is_visible(timeout=3_000):
            slider.fill(str(level))
    except Exception:
        pass

    # Start game.
    for label in ["Start game", "Play", "开始游戏"]:
        try:
            page.get_by_role("button", name=label).click(timeout=2_000)
            break
        except Exception:
            continue

    wait_for_board(page)
    return page


def bot_loop(page: Page, cfg: BotConfig) -> None:
    orientation_white = detect_bot_color(page) == chess.WHITE
    my_color = chess.WHITE if orientation_white else chess.BLACK

    print(f"Bot color: {'white' if my_color == chess.WHITE else 'black'}")
    print("Press Ctrl+C to stop.")

    seen_fen = ""
    while True:
        san_moves = fetch_san_moves(page)
        board = uci_from_san_list(san_moves)

        if board.is_game_over():
            print("Game over:", board.result(claim_draw=True))
            return

        if board.turn != my_color:
            time.sleep(0.2)
            continue

        fen = board.fen()
        if fen == seen_fen:
            time.sleep(0.1)
            continue

        move = choose_move(board)
        think = cfg.move_delay + random.uniform(0, cfg.think_spread)
        time.sleep(think)
        play_move(page, move, orientation_white=orientation_white)
        seen_fen = fen


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-play Lichess vs computer")
    parser.add_argument("--level", type=int, default=1, choices=range(1, 9), help="AI level 1-8")
    parser.add_argument("--headless", action="store_true", help="Run browser headless")
    parser.add_argument("--delay", type=float, default=1.2, help="Base move delay seconds")
    parser.add_argument(
        "--cdp-url",
        type=str,
        default=None,
        help="Connect to an existing Chrome via CDP, e.g. http://127.0.0.1:9222",
    )
    args = parser.parse_args()

    cfg = BotConfig(level=args.level, move_delay=args.delay, headless=args.headless, cdp_url=args.cdp_url)

    with sync_playwright() as p:
        if cfg.cdp_url:
            browser = p.chromium.connect_over_cdp(cfg.cdp_url)
            context = browser.contexts[0] if browser.contexts else browser.new_context(viewport={"width": 1366, "height": 900})
        else:
            browser = p.chromium.launch(headless=cfg.headless)
            context = browser.new_context(viewport={"width": 1366, "height": 900})

        page = open_vs_ai(context, cfg.level)

        try:
            bot_loop(page, cfg)
        except KeyboardInterrupt:
            print("Stopped by user.")
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
