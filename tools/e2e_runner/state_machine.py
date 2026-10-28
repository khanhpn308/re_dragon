#!/usr/bin/env python3
"""
State-Aware Scene Classification and Navigation Engine for ReturnSaiyan E2E.
Eliminates blind coordinate taps by classifying the live Android screen into
discrete observable game states and navigating using state-validated actions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
from io import BytesIO
import json
import logging
import os
from pathlib import Path
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageChops, ImageStat

logger = logging.getLogger("state_machine")


class GameState(str, Enum):
    TITLE = "TITLE"
    SERVER_SELECTION = "SERVER_SELECTION"
    MAIN_LOBBY = "MAIN_LOBBY"
    PHO_BAN_MENU = "PHO_BAN_MENU"
    CHIEN_DAU_MENU = "CHIEN_DAU_MENU"
    STAGE_SELECTION = "STAGE_SELECTION"
    STAGE_LOADING = "STAGE_LOADING"
    IN_STAGE_BATTLE = "IN_STAGE_BATTLE"
    RESULT_VICTORY = "RESULT_VICTORY"
    RESULT_DEFEAT = "RESULT_DEFEAT"
    REWARD_SETTLEMENT = "REWARD_SETTLEMENT"
    PHIEU_LUU = "PHIEU_LUU"
    CONNECTING_SERVER = "CONNECTING_SERVER"
    UNKNOWN = "UNKNOWN"


@dataclass
class Viewport:
    left: int
    top: int
    right: int
    bottom: int
    design_width: int = 1920
    design_height: int = 1080

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def to_screen_coords(self, nx: float, ny: float) -> Tuple[int, int]:
        """Maps normalized canvas coords (0.0..1.0) into absolute screen pixels."""
        if not (0.0 <= nx <= 1.0 and 0.0 <= ny <= 1.0):
            raise ValueError(f"Normalized coordinates must be within [0.0, 1.0], got ({nx}, {ny})")
        sx = int(self.left + nx * self.width)
        sy = int(self.top + ny * self.height)
        return sx, sy

    def is_inside(self, sx: int, sy: int) -> bool:
        return self.left <= sx <= self.right and self.top <= sy <= self.bottom


@dataclass
class ClassificationResult:
    state: GameState
    confidence: float
    reason: str
    viewport: Viewport
    interactive_targets: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)


class SceneClassifier:
    """Robust image-based classifier for ReturnSaiyan game states."""

    def __init__(self, confidence_threshold: float = 0.60):
        self.confidence_threshold = confidence_threshold

    @staticmethod
    def detect_viewport(image: Image.Image) -> Viewport:
        """Detects active rendering viewport inside full screenshot (handles pillarboxing)."""
        img_rgb = image.convert("RGB")
        w, h = img_rgb.size

        # Find non-black borders on horizontal axis
        left = 0
        while left < w:
            col = img_rgb.crop((left, 0, left + 1, h))
            ext = col.getextrema()
            if max(ext[0][1], ext[1][1], ext[2][1]) > 12:
                break
            left += 1

        right = w - 1
        while right > 0:
            col = img_rgb.crop((right, 0, right + 1, h))
            ext = col.getextrema()
            if max(ext[0][1], ext[1][1], ext[2][1]) > 12:
                break
            right -= 1

        if right <= left or (right - left + 1) < 800:
            return Viewport(left=0, top=0, right=w, bottom=h)

        return Viewport(left=left, top=0, right=right + 1, bottom=h)

    def classify(self, image: Image.Image) -> ClassificationResult:
        """Classifies the given PIL image into one of the GameState categories."""
        viewport = self.detect_viewport(image)
        canvas = image.convert("RGB").crop((viewport.left, viewport.top, viewport.right, viewport.bottom))
        cw, ch = canvas.size

        stat_full = ImageStat.Stat(canvas)
        m = stat_full.mean

        # Regional slices (normalized to active 1920x1080 canvas)
        top_left = canvas.crop((0, 0, int(cw * 0.25), int(ch * 0.25)))
        tl = ImageStat.Stat(top_left).mean

        top_right = canvas.crop((int(cw * 0.75), 0, cw, int(ch * 0.25)))
        tr = ImageStat.Stat(top_right).mean

        center = canvas.crop((int(cw * 0.25), int(ch * 0.25), int(cw * 0.75), int(ch * 0.75)))
        c = ImageStat.Stat(center).mean

        bottom_left = canvas.crop((0, int(ch * 0.70), int(cw * 0.35), ch))
        bl = ImageStat.Stat(bottom_left).mean

        bottom_right = canvas.crop((int(cw * 0.75), int(ch * 0.75), cw, ch))
        br = ImageStat.Stat(bottom_right).mean

        bottom_menu = canvas.crop((int(cw * 0.25), int(ch * 0.85), int(cw * 0.75), ch))
        bm = ImageStat.Stat(bottom_menu).mean

        metrics = {
            "canvas_mean": [round(x, 1) for x in m],
            "tl_mean": [round(x, 1) for x in tl],
            "tr_mean": [round(x, 1) for x in tr],
            "c_mean": [round(x, 1) for x in c],
            "bl_mean": [round(x, 1) for x in bl],
            "br_mean": [round(x, 1) for x in br],
            "bm_mean": [round(x, 1) for x in bm],
            "viewport": (viewport.left, viewport.top, viewport.right, viewport.bottom),
        }

        # 1. SERVER_SELECTION: Dark slate blue / low luminance overall (including center)
        if m[0] < 75 and m[1] < 80 and m[2] < 80 and c[0] < 75 and c[1] < 75:
            targets = {
                "server_card_1": (0.445, 0.259),
                "server_card_recent": (0.445, 0.350),
                "btn_enter_game": (0.500, 0.750),
                "btn_ok": (0.590, 0.634),
            }
            return ClassificationResult(
                state=GameState.SERVER_SELECTION,
                confidence=0.92,
                reason="Dark server selection backdrop with server card panels",
                viewport=viewport,
                interactive_targets=targets,
                metrics=metrics,
            )

        # 2. TITLE: High Red/Warm tones, Title splash/modal dialog with Guest login
        if m[0] > m[2] + 25 and br[0] > 140:
            targets = {
                "khach_guest": (0.361, 0.773),
                "dang_nhap": (0.500, 0.773),
                "dang_ky": (0.639, 0.773),
            }
            return ClassificationResult(
                state=GameState.TITLE,
                confidence=0.95,
                reason="Title screen with Guest/Account login modal detected",
                viewport=viewport,
                interactive_targets=targets,
                metrics=metrics,
            )

        # 3. STAGE_SELECT: Stage / Level selection (guanqia_page: Trái Đất / Saiyan Invasion)
        # Blue Earth curvature at bottom (bm[2] > 200), mode tabs in bottom-right (br[0] > 80), no yellow cloud in BL (bl[0] < 120)
        if bm[2] > 200 and br[0] > 80 and bl[0] < 120 and m[2] > 130:
            targets = {
                "btn_home": (0.04, 0.06),
                "formation_radar": (0.88, 0.06),
                "stage_chapter_center": (0.50, 0.50),
                "star_badge": (0.50, 0.67),
                "tab_normal": (0.70, 0.95),
                "tab_elite": (0.85, 0.95),
            }
            return ClassificationResult(
                state=GameState.STAGE_SELECTION,
                confidence=0.94,
                reason="Main Stage/Level selection interface (guanqia_page) detected with Earth orbit and chapter badge",
                viewport=viewport,
                interactive_targets=targets,
                metrics=metrics,
            )

        # 4. PHIEU_LUU: Adventure mode (flying cloud Goku)
        # Dominant Blue channel across screen and in bottom-right sky
        if m[2] > 140 and br[2] > 95:
            targets = {
                "go_button": (0.85, 0.78),
                "quick_adventure": (0.85, 0.90),
                "close_or_back": (0.95, 0.10),
            }
            return ClassificationResult(
                state=GameState.PHIEU_LUU,
                confidence=0.94,
                reason="High blue channel sky/cloud backdrop with adventure cloud scene, NOT in-stage battle",
                viewport=viewport,
                interactive_targets=targets,
                metrics=metrics,
            )

        # 5. MAIN_LOBBY: Vibrant outdoor world, top-left avatar header, warm bottom-right UI buttons
        # Note: br[0] > br[2] + 15 distinguishes Main Lobby from sky-blue adventure mode
        if m[1] > 105 and br[0] > br[2] + 15:
            targets = {
                "avatar": (0.05, 0.08),
                "tui_do": (0.089, 0.926),
                "doi_hinh": (0.130, 0.926),
                "trieu_hoi": (0.219, 0.926),
                "so_tay": (0.292, 0.926),
                "android": (0.375, 0.926),
                "dong_doi": (0.458, 0.926),
                "tuong_roster": (0.458, 0.926),
                "manh_hon": (0.550, 0.926),
                "pho_ban": (0.824, 0.904),
                "chien_dau": (0.935, 0.925),
            }
            return ClassificationResult(
                state=GameState.MAIN_LOBBY,
                confidence=0.92,
                reason="Main Lobby detected with avatar header, bottom navigation bar, and Phó bản / Chiến đấu entries",
                viewport=viewport,
                interactive_targets=targets,
                metrics=metrics,
            )

        # 5. PHO_BAN_MENU: Dungeon instance list (fuben_zhujiemian)
        if c[0] > 110 and c[1] > 110 and abs(c[0] - c[2]) < 25 and tl[0] < 80 and tr[0] < 80 and br[0] < 75:
            targets = {
                "back_button": (0.04, 0.06),
                "chapter_card_center": (0.50, 0.50),
                "chapter_card_left": (0.25, 0.50),
                "chapter_card_right": (0.75, 0.50),
                "stage_1": (0.30, 0.65),
                "stage_2": (0.50, 0.65),
            }
            return ClassificationResult(
                state=GameState.PHO_BAN_MENU,
                confidence=0.92,
                reason="Phó bản main interface (fuben_zhujiemian) detected with instance cards and navigation header",
                viewport=viewport,
                interactive_targets=targets,
                metrics=metrics,
            )

        # 6. CHIEN_DAU_MENU: Arena / PvP battle modes
        if tl[0] > 80 and tr[0] > 80 and bm[0] > 70:
            targets = {
                "back_button": (0.04, 0.06),
                "mode_arena": (0.30, 0.50),
                "mode_trials": (0.60, 0.50),
            }
            return ClassificationResult(
                state=GameState.CHIEN_DAU_MENU,
                confidence=0.75,
                reason="Chiến đấu battle mode selection menu detected",
                viewport=viewport,
                interactive_targets=targets,
                metrics=metrics,
            )

        # 7. IN_STAGE_BATTLE: Combat HUD
        # Requires high-luminance skill cluster in BR and active virtual joystick in BL
        if tr[0] > 70 and br[0] > 110 and bl[0] > 90 and c[0] > 90:
            targets = {
                "joystick_center": (0.16, 0.78),
                "joystick_east": (0.22, 0.78),
                "joystick_north": (0.16, 0.68),
                "attack_button": (0.90, 0.85),
                "skill_1": (0.80, 0.88),
                "skill_2": (0.82, 0.74),
                "skill_3": (0.89, 0.68),
                "pause_button": (0.96, 0.06),
                "auto_button": (0.90, 0.06),
            }
            return ClassificationResult(
                state=GameState.IN_STAGE_BATTLE,
                confidence=0.80,
                reason="In-stage battle HUD with movement joystick and combat skill cluster",
                viewport=viewport,
                interactive_targets=targets,
                metrics=metrics,
            )

        # 8. RESULT_VICTORY: Bright golden banner in center
        if c[0] > 135 and c[1] > 110 and c[0] > c[2] + 40 and c[1] > c[2] + 30:
            targets = {
                "continue_tap": (0.50, 0.85),
                "btn_confirm": (0.50, 0.80),
            }
            return ClassificationResult(
                state=GameState.RESULT_VICTORY,
                confidence=0.88,
                reason="Golden victory banner with stars and settlement preview",
                viewport=viewport,
                interactive_targets=targets,
                metrics=metrics,
            )

        # 9. RESULT_DEFEAT: Red banner in center
        if c[0] > 110 and c[0] > c[1] + 35 and c[0] > c[2] + 35:
            targets = {
                "btn_retry": (0.40, 0.80),
                "btn_exit": (0.60, 0.80),
            }
            return ClassificationResult(
                state=GameState.RESULT_DEFEAT,
                confidence=0.88,
                reason="Red defeat banner with retry/exit options",
                viewport=viewport,
                interactive_targets=targets,
                metrics=metrics,
            )

        # 10. UNKNOWN: Fallback
        return ClassificationResult(
            state=GameState.UNKNOWN,
            confidence=0.30,
            reason="Scene visual signature did not match any known template",
            viewport=viewport,
            interactive_targets={"center": (0.50, 0.50), "back": (0.04, 0.06)},
            metrics=metrics,
        )


class StateAwareNavigator:
    """Device driver that navigates strictly via verified scene state transitions."""

    def __init__(
        self,
        device_id: str = "10b3139c",
        package_name: str = "com.tony.lzcen.arm64",
        activity_name: str = "com.tony.lzcen.arm64/.AppActivity",
    ):
        self.device_id = device_id
        self.package_name = package_name
        self.activity_name = activity_name
        self.classifier = SceneClassifier()

    def capture_screen(self) -> Tuple[Image.Image, bytes]:
        """Captures raw native PNG screenshot from physical device."""
        cmd = ["adb", "-s", self.device_id, "exec-out", "screencap", "-p"]
        raw = subprocess.check_output(cmd)
        img = Image.open(BytesIO(raw))
        return img, raw

    def inspect_state(self) -> ClassificationResult:
        """Captures screen and classifies current game state."""
        img, _ = self.capture_screen()
        return self.classifier.classify(img)

    def tap_target(self, target_name: str, current_res: ClassificationResult) -> Tuple[int, int]:
        """Taps a named interactive target on screen, validating it belongs to active scene."""
        if target_name not in current_res.interactive_targets:
            raise KeyError(
                f"Target '{target_name}' not available in state {current_res.state.value}. "
                f"Available: {list(current_res.interactive_targets.keys())}"
            )
        nx, ny = current_res.interactive_targets[target_name]
        sx, sy = current_res.viewport.to_screen_coords(nx, ny)

        logger.info(f"State [{current_res.state.value}] -> Tapping target '{target_name}' at screen ({sx}, {sy})")
        subprocess.check_call(["adb", "-s", self.device_id, "shell", "input", "tap", str(sx), str(sy)])
        return sx, sy

    def transition_to(
        self,
        expected_state: GameState,
        action_target: str,
        timeout_seconds: float = 12.0,
        interval_seconds: float = 1.0,
    ) -> ClassificationResult:
        """
        Executes a targeted navigation tap and polls for the expected destination state.
        Raises TimeoutError if destination state is not confirmed.
        """
        initial_res = self.inspect_state()
        self.tap_target(action_target, initial_res)

        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            time.sleep(interval_seconds)
            current_res = self.inspect_state()
            if current_res.state == expected_state:
                logger.info(f"Transition succeeded: Reached state {expected_state.value} ({current_res.reason})")
                return current_res

        last_res = self.inspect_state()
        raise TimeoutError(
            f"Failed to reach expected state {expected_state.value} within {timeout_seconds}s. "
            f"Last observed state: {last_res.state.value} ({last_res.reason})"
        )


if __name__ == "__main__":
    import sys

    classifier = SceneClassifier()
    for arg in sys.argv[1:]:
        p = Path(arg)
        if p.exists():
            im = Image.open(p)
            res = classifier.classify(im)
            print(f"{p.name}: State={res.state.value} (conf={res.confidence:.2f}) -> {res.reason}")
            print(f"  Viewport: ({res.viewport.left}, {res.viewport.top}) to ({res.viewport.right}, {res.viewport.bottom})")
            print(f"  Interactive targets: {res.interactive_targets}")
