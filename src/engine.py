"""转生与觉醒系统。

修复点:
1. 转生时等级/属性点/技能点/已分配属性全部重置, 按新等级重新分配。
2. 转生加成按转生前等级与实际战力(属性+装备)公式计算, 不再固定。
3. 转生次数有上限(MAX_REBIRTH_COUNT), 满后转为悟道修为养成线。
4. 觉醒技能必须完成觉醒任务链后逐段解锁, 不能只看转生次数。
5. 经验加成改为递减收益(等比衰减), 高阶转生收益越来越低。
6. 转生时自动卸下装备(进背包, 背包满则进邮件), 并重算属性。
7. 转生有冷却时间且必须重新达到随转生次数提升的等级条件。
"""
import time
from dataclasses import dataclass, field


BASE_REBIRTH_LEVEL = 100          # 首次转生所需等级
LEVEL_REQUIREMENT_STEP = 10       # 每次转生后, 下次转生多需要的等级
MAX_REBIRTH_COUNT = 10            # 转生次数上限
REBIRTH_COOLDOWN_SECONDS = 7 * 24 * 3600  # 转生冷却: 7 天
STAT_POINTS_PER_LEVEL = 5         # 每级获得的可分配属性点
SKILL_POINTS_PER_LEVELS = 10      # 每 10 级获得 1 点技能点
BACKPACK_CAPACITY = 20

# 第 n 次转生(n 从 1 开始)的经验加成基数, 按 0.7 等比衰减
EXP_BONUS_FIRST = 0.1
EXP_BONUS_DECAY = 0.7

# 觉醒任务链: (任务id, 所需转生次数, 完成后解锁的觉醒技能)
AWAKENING_CHAIN = [
    ("awaken_1", 1, "觉醒之心"),
    ("awaken_2", 2, "觉醒之瞳"),
    ("awaken_3", 3, "觉醒之魂"),
    ("awaken_4", 5, "觉醒之翼"),
    ("awaken_5", MAX_REBIRTH_COUNT, "觉醒之神"),
]


class RebirthError(Exception):
    """转生/觉醒操作不满足条件时抛出。"""


@dataclass
class Player:
    pid: str
    level: int
    stat_points: int
    rebirth_count: int = 0
    rebirth_bonus: float = 0.0
    # 已分配到具体属性上的点数, 如 {"str": 10}
    stats: dict = field(default_factory=dict)
    skill_points: int = 0
    learned_skills: list = field(default_factory=list)
    max_level: int = 0
    # 槽位 -> 装备 {"name", "req_level", "stats": {...}}
    equipment: dict = field(default_factory=dict)
    backpack: list = field(default_factory=list)
    mail: list = field(default_factory=list)
    awakened_skills: list = field(default_factory=list)
    awakening_tasks_done: list = field(default_factory=list)
    last_rebirth_ts: float = 0.0
    # 转生次数满后的替代养成线: 悟道修为
    dao_points: float = 0.0


class RebirthSystem:
    def __init__(self):
        self.players: dict[str, Player] = {}
        # 兼容旧接口的装备/冷却视图, 实际数据记录在 Player 上
        self.equipment = {}
        self.cooldown = {}
        self._now = time.time

    # ---- 通用工具 ----

    def rebirth_level_requirement(self, rebirth_count):
        """第 (rebirth_count+1) 次转生所需的等级。"""
        return BASE_REBIRTH_LEVEL + LEVEL_REQUIREMENT_STEP * rebirth_count

    def cooldown_remaining(self, pid):
        """距离下次可转生还剩多少秒, 无冷却记录时返回 0。"""
        p = self.players[pid]
        if p.last_rebirth_ts <= 0:
            return 0
        elapsed = self._now() - p.last_rebirth_ts
        return max(0.0, REBIRTH_COOLDOWN_SECONDS - elapsed)

    def _power(self, p):
        """当前战力: 未分配点数 + 已分配属性 + 装备属性。"""
        power = p.stat_points + sum(p.stats.values())
        for item in p.equipment.values():
            power += sum(item.get("stats", {}).values())
        return power

    # ---- 转生条件 ----

    def can_rebirth(self, pid):
        p = self.players[pid]
        if p.rebirth_count >= MAX_REBIRTH_COUNT:
            return False
        if p.level < self.rebirth_level_requirement(p.rebirth_count):
            return False
        if self.cooldown_remaining(pid) > 0:
            return False
        return True

    def rebirth(self, pid):
        p = self.players[pid]
        if p.rebirth_count >= MAX_REBIRTH_COUNT:
            raise RebirthError(
                f"已达{MAX_REBIRTH_COUNT}转上限, 请通过悟道修为继续养成(cultivate_dao)"
            )
        required = self.rebirth_level_requirement(p.rebirth_count)
        if p.level < required:
            raise RebirthError(f"等级不足, 第{p.rebirth_count + 1}次转生需要{required}级")
        remaining = self.cooldown_remaining(pid)
        if remaining > 0:
            raise RebirthError(f"转生冷却中, 还需等待{remaining / 86400:.1f}天")

        # 修复2: 加成 = 转生前等级 * 0.1 + 战力 * 2%, 高阶转生小幅衰减
        gain = p.level * 0.1 + self._power(p) * 0.02
        gain /= 1 + 0.05 * p.rebirth_count

        p.rebirth_count += 1
        p.rebirth_bonus = round(p.rebirth_bonus + gain, 2)

        self._reset_for_new_life(p)
        p.last_rebirth_ts = self._now()
        self.equipment[pid] = p.equipment
        self.cooldown[pid] = p.last_rebirth_ts
        return p

    def _reset_for_new_life(self, p):
        # 修复6: 装备全部卸下, 背包放不下的进邮件
        for slot in list(p.equipment):
            self._unequip(p, slot)
        # 修复1: 等级/属性点/技能点/已分配属性全部重置, 按 1 级重新分配
        p.level = 1
        p.max_level = max(p.max_level, 1)
        p.stats = {}
        p.stat_points = (p.level - 1) * STAT_POINTS_PER_LEVEL
        p.skill_points = (p.level - 1) // SKILL_POINTS_PER_LEVELS
        p.learned_skills = []

    def _unequip(self, p, slot):
        item = p.equipment.pop(slot, None)
        if item is None:
            return
        if len(p.backpack) < BACKPACK_CAPACITY:
            p.backpack.append(item)
        else:
            p.mail.append({"from": "rebirth", "reason": "backpack_full", "item": item})

    # ---- 升级与属性重算 ----

    def gain_exp(self, pid, exp):
        """按当前经验加成结算经验并升级, 升级补属性点/技能点。"""
        p = self.players[pid]
        gained = exp * self.get_exp_bonus(pid)
        new_level = max(p.level, 1 + int(gained // 100))
        self._apply_level(p, new_level)
        return gained

    def _apply_level(self, p, new_level):
        if new_level <= p.level:
            return
        old_level = p.level
        p.level = new_level
        p.max_level = max(p.max_level, new_level)
        # 可分配点数 = 等级应得总数 - 已分配
        p.stat_points = (new_level - 1) * STAT_POINTS_PER_LEVEL - sum(p.stats.values())
        used_skill = len([s for s in p.learned_skills if not s.startswith("awaken:")])
        p.skill_points = (new_level - 1) // SKILL_POINTS_PER_LEVELS - used_skill

    def allocate_stat(self, pid, stat, amount):
        p = self.players[pid]
        if amount <= 0 or amount > p.stat_points:
            raise RebirthError("可分配属性点不足")
        p.stat_points -= amount
        p.stats[stat] = p.stats.get(stat, 0) + amount

    def equip_item(self, pid, slot, item):
        p = self.players[pid]
        if item.get("req_level", 1) > p.level:
            raise RebirthError(f"等级不足, 无法装备{item.get('name')}")
        p.equipment[slot] = item
        self.equipment[pid] = p.equipment

    def recalc(self, pid):
        """重新计算玩家属性(升级/卸装后调用)。"""
        p = self.players[pid]
        p.stat_points = (p.level - 1) * STAT_POINTS_PER_LEVEL - sum(p.stats.values())
        return self._power(p)

    # ---- 经验加成(递减收益) ----

    def get_exp_bonus(self, pid):
        p = self.players[pid]
        # 修复5: 0.1 + 0.1*0.7 + 0.1*0.7^2 ... 替代线性叠加
        bonus = sum(
            EXP_BONUS_FIRST * EXP_BONUS_DECAY ** i for i in range(p.rebirth_count)
        )
        return round(1 + bonus, 4)

    # ---- 觉醒任务链 ----

    def complete_awakening_task(self, pid, task_id):
        """按任务链顺序完成觉醒任务, 完成即解锁对应觉醒技能。"""
        p = self.players[pid]
        chain_ids = [task for task, _, _ in AWAKENING_CHAIN]
        if task_id not in chain_ids:
            raise RebirthError(f"未知觉醒任务: {task_id}")
        index = chain_ids.index(task_id)
        if task_id in p.awakening_tasks_done:
            raise RebirthError("任务已完成")
        if index > 0 and AWAKENING_CHAIN[index - 1][0] not in p.awakening_tasks_done:
            raise RebirthError("必须先完成前置觉醒任务")
        required_rebirth = AWAKENING_CHAIN[index][1]
        if p.rebirth_count < required_rebirth:
            raise RebirthError(f"该任务需要{required_rebirth}转")
        skill = AWAKENING_CHAIN[index][2]
        p.awakening_tasks_done.append(task_id)
        p.awakened_skills.append(skill)
        p.learned_skills.append(f"awaken:{skill}")
        return skill

    def unlock_awakening(self, pid, skill=None):
        """觉醒技能只能由任务链解锁; 不看单纯的转生次数。"""
        p = self.players[pid]
        if skill is None:
            return bool(p.awakened_skills)
        return skill in p.awakened_skills

    # ---- 转生上限后的替代养成 ----

    def cultivate_dao(self, pid):
        """达到转生上限后转为悟道修为: 仍需等级条件, 但不再增加转生次数。"""
        p = self.players[pid]
        if p.rebirth_count < MAX_REBIRTH_COUNT:
            raise RebirthError("未满转生次数上限, 请继续转生")
        if p.level < BASE_REBIRTH_LEVEL:
            raise RebirthError(f"悟道需要{BASE_REBIRTH_LEVEL}级")
        if self.cooldown_remaining(pid) > 0:
            raise RebirthError("修为冷却中")
        gain = p.level * 0.05 + self._power(p) * 0.01
        p.dao_points = round(p.dao_points + gain, 2)
        self._reset_for_new_life(p)
        p.last_rebirth_ts = self._now()
        return p.dao_points
