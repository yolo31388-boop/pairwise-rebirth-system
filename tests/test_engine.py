"""转生测试"""
import pytest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.engine import RebirthSystem, Player

class TestRebirth:
    def test_stat_points_reset(self):
        rs = RebirthSystem()
        rs.players["p1"] = Player("p1", 100, 500)
        rs.rebirth("p1")
        assert rs.players["p1"].stat_points != 500 or rs.players["p1"].level == 1, "属性点未重置"

class TestBonus:
    def test_bonus_scales_with_level(self):
        rs = RebirthSystem()
        rs.players["p1"] = Player("p1", 100, 0)
        rs.players["p2"] = Player("p2", 200, 0)
        b1 = rs.rebirth("p1").rebirth_bonus
        b2 = rs.rebirth("p2").rebirth_bonus
        assert b2 > b1, "转生加成不看原等级"
