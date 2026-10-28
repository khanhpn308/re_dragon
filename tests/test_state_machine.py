#!/usr/bin/env python3
"""
Unit and integration tests for state-aware scene classifier and navigation engine.
"""
from pathlib import Path
import unittest

from PIL import Image

from tools.e2e_runner.state_machine import (
    ClassificationResult,
    GameState,
    SceneClassifier,
    Viewport,
)


class TestStateMachineClassifier(unittest.TestCase):
    def setUp(self):
        self.classifier = SceneClassifier()
        self.evidence_dir = Path("/home/khanh/returnsaiyan-re/evidence/s6_e2e")

    def test_viewport_coordinate_mapping(self):
        vp = Viewport(left=246, top=0, right=2166, bottom=1080)
        self.assertEqual(vp.width, 1920)
        self.assertEqual(vp.height, 1080)

        # Center of canvas
        sx, sy = vp.to_screen_coords(0.5, 0.5)
        self.assertEqual((sx, sy), (1206, 540))
        self.assertTrue(vp.is_inside(sx, sy))

        # Rejection of invalid coordinates
        with self.assertRaises(ValueError):
            vp.to_screen_coords(-0.1, 0.5)
        with self.assertRaises(ValueError):
            vp.to_screen_coords(0.5, 1.1)

    def test_classify_title_screen(self):
        img_path = self.evidence_dir / "01_app_launch.png"
        self.assertTrue(img_path.exists())
        im = Image.open(img_path)
        res = self.classifier.classify(im)

        self.assertEqual(res.state, GameState.TITLE)
        self.assertGreaterEqual(res.confidence, 0.90)
        self.assertIn("khach_guest", res.interactive_targets)
        self.assertNotEqual(res.state, GameState.IN_STAGE_BATTLE)

    def test_classify_server_selection(self):
        img_path = self.evidence_dir / "02_server_selection.png"
        self.assertTrue(img_path.exists())
        im = Image.open(img_path)
        res = self.classifier.classify(im)

        self.assertEqual(res.state, GameState.SERVER_SELECTION)
        self.assertGreaterEqual(res.confidence, 0.85)
        self.assertIn("server_card_1", res.interactive_targets)

    def test_classify_main_lobby_distinction(self):
        img_path = self.evidence_dir / "03_world_entry.png"
        self.assertTrue(img_path.exists())
        im = Image.open(img_path)
        res = self.classifier.classify(im)

        self.assertEqual(res.state, GameState.MAIN_LOBBY)
        self.assertGreaterEqual(res.confidence, 0.85)
        self.assertIn("pho_ban", res.interactive_targets)
        self.assertIn("chien_dau", res.interactive_targets)
        # Must NOT be classified as in-stage battle
        self.assertNotEqual(res.state, GameState.IN_STAGE_BATTLE)

    def test_classify_pho_ban_menu(self):
        img_path = Path("/home/khanh/returnsaiyan-re/evidence/real_dungeon_combat/20261028_044633/02_pho_ban_post.png")
        if img_path.exists():
            im = Image.open(img_path)
            res = self.classifier.classify(im)
            self.assertEqual(res.state, GameState.PHO_BAN_MENU)
            self.assertGreaterEqual(res.confidence, 0.85)
            self.assertIn("back_button", res.interactive_targets)

    def test_classify_chien_dau_stage_selection(self):
        img_path = Path("/home/khanh/returnsaiyan-re/evidence/real_dungeon_combat/20261028_045323/02_chien_dau_post.png")
        if img_path.exists():
            im = Image.open(img_path)
            res = self.classifier.classify(im)
            self.assertEqual(res.state, GameState.STAGE_SELECTION)
            self.assertGreaterEqual(res.confidence, 0.85)
            self.assertIn("stage_chapter_center", res.interactive_targets)
            self.assertIn("tab_normal", res.interactive_targets)
            self.assertIn("tab_elite", res.interactive_targets)
            self.assertNotEqual(res.state, GameState.PHIEU_LUU)

    def test_reject_combat_and_roster_misclassification(self):
        # 04c was previously falsely claimed as combat skill
        img_04c = self.evidence_dir / "04c_combat_skill.png"
        self.assertTrue(img_04c.exists())
        im_04c = Image.open(img_04c)
        res_04c = self.classifier.classify(im_04c)

        self.assertEqual(res_04c.state, GameState.PHIEU_LUU)
        self.assertNotEqual(res_04c.state, GameState.IN_STAGE_BATTLE)

        # 04d was previously falsely claimed as hero roster
        img_04d = self.evidence_dir / "04d_hero_roster.png"
        self.assertTrue(img_04d.exists())
        im_04d = Image.open(img_04d)
        res_04d = self.classifier.classify(im_04d)

        self.assertEqual(res_04d.state, GameState.PHIEU_LUU)
        self.assertNotEqual(res_04d.state, GameState.IN_STAGE_BATTLE)

    def test_synthetic_victory_defeat_states(self):
        # Create synthetic victory image (gold/yellow center)
        im_vic = Image.new("RGB", (2412, 1080), (30, 30, 30))
        for x in range(600, 1800):
            for y in range(200, 600):
                im_vic.putpixel((x, y), (220, 180, 40))
        res_vic = self.classifier.classify(im_vic)
        self.assertEqual(res_vic.state, GameState.RESULT_VICTORY)

        # Create synthetic defeat image (red center)
        im_def = Image.new("RGB", (2412, 1080), (20, 20, 20))
        for x in range(600, 1800):
            for y in range(200, 600):
                im_def.putpixel((x, y), (180, 30, 30))
        res_def = self.classifier.classify(im_def)
        self.assertEqual(res_def.state, GameState.RESULT_DEFEAT)

    def test_all_game_states_present_in_enum(self):
        expected_states = [
            "TITLE", "SERVER_SELECTION", "MAIN_LOBBY", "PHO_BAN_MENU",
            "CHIEN_DAU_MENU", "STAGE_SELECTION", "STAGE_LOADING",
            "IN_STAGE_BATTLE", "RESULT_VICTORY", "RESULT_DEFEAT",
            "REWARD_SETTLEMENT", "PHIEU_LUU", "CONNECTING_SERVER", "UNKNOWN"
        ]
        values = [s.value for s in GameState]
        for expected in expected_states:
            self.assertIn(expected, values)

    def test_rejection_blind_and_unmapped_targets(self):
        from tools.e2e_runner.state_machine import StateAwareNavigator
        nav = StateAwareNavigator()
        res = ClassificationResult(
            state=GameState.MAIN_LOBBY,
            confidence=0.9,
            reason="Lobby test",
            viewport=Viewport(246, 0, 2166, 1080),
            interactive_targets={"pho_ban": (0.757, 0.889)}
        )
        # Attempting to tap unverified combat button in Lobby MUST raise KeyError
        with self.assertRaises(KeyError):
            nav.tap_target("attack_button", res)



if __name__ == "__main__":
    unittest.main()
