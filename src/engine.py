"""转生觉醒系统"""
import time
from dataclasses import dataclass, field

MAX_REBIRTH_COUNT = 10
REBIRTH_LEVEL_REQUIREMENT = 100
REBIRTH_COOLDOWN_SECONDS = 7 * 24 * 3600  # 7天

BASE_STAT_POINTS = 5
BASE_SKILL_POINTS = 1
STAT_POINTS_PER_REBIRTH = 5
SKILL_POINTS_PER_REBIRTH = 1

EXP_BONUS_STEP = 0.1
EXP_BONUS_DECAY = 0.8  # 每转收益递减

INVENTORY_CAPACITY = 40

# 觉醒任务链: 阶位 -> 前置任务
AWAKENING_QUEST_CHAIN = {
    1: "quest_awaken_1",
    2: "quest_awaken_2",
    3: "quest_awaken_3",
}


@dataclass
class Player:
    pid: str
    level: int
    stat_points: int
    skill_points: int = 0
    rebirth_count: int = 0
    rebirth_bonus: float = 0.0
    highest_level: int = 0
    paragon_points: int = 0
    awakenings: set = field(default_factory=set)
    completed_quests: set = field(default_factory=set)
    last_rebirth_time: float = 0.0

    def __post_init__(self):
        self.highest_level = max(self.highest_level, self.level)


class RebirthSystem:
    def __init__(self):
        self.players: dict[str, Player] = {}
        self.equipment: dict[str, dict] = {}   # pid -> {slot: item}
        self.inventory: dict[str, list] = {}   # pid -> [item]
        self.mail: dict[str, list] = {}        # pid -> [item] 背包满时走邮件

    # ---- 转生条件: 等级达标 + 冷却结束 + 未达上限 ----
    def can_rebirth(self, pid, now=None):
        p = self.players[pid]
        if p.rebirth_count >= MAX_REBIRTH_COUNT:
            return False
        if p.level < REBIRTH_LEVEL_REQUIREMENT:
            return False
        now = time.time() if now is None else now
        return now - p.last_rebirth_time >= REBIRTH_COOLDOWN_SECONDS

    # ---- 转生加成: 按转生前最高等级与属性点计算 ----
    def _compute_bonus(self, p):
        return 10 * (p.highest_level / REBIRTH_LEVEL_REQUIREMENT) + p.stat_points * 0.02

    def rebirth(self, pid, now=None):
        p = self.players[pid]
        if not self.can_rebirth(pid, now):
            raise ValueError("不满足转生条件(等级/冷却/次数上限)")
        now = time.time() if now is None else now

        p.rebirth_bonus += self._compute_bonus(p)
        p.rebirth_count += 1
        p.last_rebirth_time = now

        # 等级/属性点/技能点全部重置, 按转生阶位重新分配
        p.level = 1
        p.stat_points = BASE_STAT_POINTS + p.rebirth_count * STAT_POINTS_PER_REBIRTH
        p.skill_points = BASE_SKILL_POINTS + p.rebirth_count * SKILL_POINTS_PER_REBIRTH

        self._unequip_invalid(pid)
        return p

    # ---- 达到上限后转为巅峰养成 ----
    def convert_to_paragon(self, pid):
        p = self.players[pid]
        if p.rebirth_count < MAX_REBIRTH_COUNT:
            raise ValueError("未达到转生上限, 不能转巅峰")
        if p.level < REBIRTH_LEVEL_REQUIREMENT:
            raise ValueError("等级不足")
        gained = p.level // REBIRTH_LEVEL_REQUIREMENT
        p.paragon_points += gained
        p.level = 1
        return gained

    # ---- 经验加成: 递减收益 ----
    def get_exp_bonus(self, pid):
        p = self.players[pid]
        return 1 + sum(EXP_BONUS_STEP * EXP_BONUS_DECAY ** i
                       for i in range(p.rebirth_count))

    # ---- 觉醒: 需完成对应任务链且按阶位顺序解锁 ----
    def complete_quest(self, pid, quest_id):
        self.players[pid].completed_quests.add(quest_id)

    def unlock_awakening(self, pid, tier=1):
        p = self.players[pid]
        if tier not in AWAKENING_QUEST_CHAIN:
            return False
        if p.rebirth_count < tier:
            return False
        if AWAKENING_QUEST_CHAIN[tier] not in p.completed_quests:
            return False
        if tier > 1 and (tier - 1) not in p.awakenings:
            return False
        p.awakenings.add(tier)
        return True

    # ---- 装备 ----
    def equip(self, pid, slot, item):
        p = self.players[pid]
        if item.get("req_level", 1) > p.level:
            raise ValueError("等级不足, 无法装备")
        self.equipment.setdefault(pid, {})[slot] = item

    def _unequip_invalid(self, pid):
        p = self.players[pid]
        equipped = self.equipment.get(pid, {})
        for slot, item in list(equipped.items()):
            if item.get("req_level", 1) > p.level:
                del equipped[slot]
                bag = self.inventory.setdefault(pid, [])
                if len(bag) < INVENTORY_CAPACITY:
                    bag.append(item)
                else:
                    self.mail.setdefault(pid, []).append(item)

    # ---- 属性重算: 基础 + 转生加成 + 当前装备 ----
    def recalc_stats(self, pid):
        p = self.players[pid]
        equip_stats = sum(
            item.get("attack", 0)
            for item in self.equipment.get(pid, {}).values()
        )
        return {
            "level": p.level,
            "stat_points": p.stat_points,
            "attack": p.stat_points + p.rebirth_bonus + equip_stats,
        }
