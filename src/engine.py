"""转生觉醒 - 带7个bug"""
from dataclasses import dataclass, field

@dataclass
class Player:
    pid: str
    level: int
    stat_points: int
    rebirth_count: int = 0
    rebirth_bonus: float = 0

class RebirthSystem:
    def __init__(self):
        self.players: dict[str, Player] = {}
        self.equipment = {}
        self.cooldown = {}  # bug7: 只看等级

    def can_rebirth(self, pid):
        p = self.players[pid]
        # bug7: 无冷却
        return p.level >= 100

    def rebirth(self, pid):
        p = self.players[pid]
        # bug1: 属性点不重置
        p.level = 1
        # bug2: 固定加成
        p.rebirth_bonus += 10
        p.rebirth_count += 1
        # bug3: 无次数上限
        # bug6: 装备不处理
        return p

    def get_exp_bonus(self, pid):
        p = self.players[pid]
        # bug5: 线性加成
        return 1 + p.rebirth_count * 0.1

    def unlock_awakening(self, pid):
        # bug4: 只看转生次数
        p = self.players[pid]
        return p.rebirth_count >= 1
