import json
import os
import re
from collections import deque
from typing import List, Optional, Tuple

EMPTY = "."      # 空点
BLACK = "B"      # 黑子
WHITE = "W"      # 白子


# ───────────────────────────────────────────────
# 基础：棋盘 Board
# ───────────────────────────────────────────────
class Board:
    """棋盘类：保存棋盘状态，提供落子 / 撤子 / 显示等操作"""

    def __init__(self, size: int):
        if not 8 <= size <= 19:
            raise ValueError("棋盘大小必须在 8~19 之间")
        self.size = size
        self.grid: List[List[str]] = [[EMPTY for _ in range(size)]
                                      for _ in range(size)]
        self.history: deque = deque()  # (x, y, color, captured) 方便悔棋

    # ── 工具 ─────────────────────────────────────
    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.size and 0 <= y < self.size

    def get(self, x: int, y: int) -> str:
        return self.grid[y][x]

    def set(self, x: int, y: int, color: str):
        self.grid[y][x] = color

    # ── 基本操作 ─────────────────────────────────
    def place_stone(self, x: int, y: int, color: str) -> None:
        """在 (x,y) 放置颜色 color 的棋子（不检查合法性，由 Rule 决定）"""
        if not self.in_bounds(x, y):
            raise ValueError("坐标越界")
        if self.get(x, y) != EMPTY:
            raise ValueError("该位置已有棋子")
        self.set(x, y, color)

    def remove_stones(self, stones: List[Tuple[int, int]]) -> None:
        """批量移除棋子（提子）"""
        for (x, y) in stones:
            self.set(x, y, EMPTY)

    # ── 显示 ─────────────────────────────────────
    def display(self) -> None:
        """控制台打印棋盘"""
        header = "   " + " ".join(f"{i:2}" for i in range(self.size))
        print(header)
        for y in range(self.size):
            row = f"{y:2} " + " ".join(self.grid[y][x] for x in range(self.size))
            print(row)
        print()

    # ── 保存 / 读取 ───────────────────────────────
    def to_dict(self) -> dict:
        return {"size": self.size, "grid": self.grid,
                "history": list(self.history)}

    @staticmethod
    def from_dict(data: dict) -> "Board":
        board = Board(data["size"])
        board.grid = data["grid"]
        board.history = deque([tuple(h) for h in data["history"]])
        return board


# ───────────────────────────────────────────────
# 规则接口（策略）
# ───────────────────────────────────────────────
class Rule:
    """规则基类：不同游戏实现自己的合法性和胜负判定"""

    name = "abstract"

    def __init__(self, board: Board):
        self.board = board
        self.passes_in_row = 0  # 围棋用

    # ↓ 抽象接口 ↓
    def is_valid_move(self, x: int, y: int, color: str) -> bool:
        raise NotImplementedError

    def apply_move(self, x: int, y: int, color: str) -> bool:
        """执行落子，返回是否导致终局"""
        raise NotImplementedError

    def undo(self) -> None:
        """悔棋：回溯一步棋"""
        if not self.board.history:
            raise ValueError("无棋可悔")
        x, y, color, captured = self.board.history.pop()
        # 撤回当前落子
        self.board.set(x, y, EMPTY)
        # 恢复被提掉的棋子
        for cx, cy in captured:
            self.board.set(cx, cy, self.opposite(color))

    def opposite(self, color: str) -> str:
        return BLACK if color == WHITE else WHITE


# ───────────────────────────────────────────────
# 五子棋规则
# ───────────────────────────────────────────────
class GomokuRule(Rule):
    name = "gomoku"

    def is_valid_move(self, x, y, color):
        # 仅需检查落点为空
        return self.board.in_bounds(x, y) and self.board.get(x, y) == EMPTY

    def apply_move(self, x, y, color):
        self.board.place_stone(x, y, color)
        self.board.history.append((x, y, color, []))  # 五子棋无提子
        # 判断是否连成 5
        if self._five_in_a_row(x, y, color):
            print(f"✪ {color} 方连成五子！获胜！")
            return True
        # 平局
        if all(self.board.get(i, j) != EMPTY
               for i in range(self.board.size)
               for j in range(self.board.size)):
            print("棋盘已满，平局！")
            return True
        return False

    def _five_in_a_row(self, x, y, color):
        """检查 4 个方向是否存在连续 5 子"""
        directions = [(1, 0), (0, 1), (1, 1), (1, -1)]
        for dx, dy in directions:
            cnt = 1
            # 正方向
            i, j = x + dx, y + dy
            while self.board.in_bounds(i, j) and self.board.get(i, j) == color:
                cnt += 1
                i += dx
                j += dy
            # 反方向
            i, j = x - dx, y - dy
            while self.board.in_bounds(i, j) and self.board.get(i, j) == color:
                cnt += 1
                i -= dx
                j -= dy
            if cnt >= 5:
                return True
        return False


# ───────────────────────────────────────────────
# 围棋规则（简化，无劫判、无眼活死判断，只提气尽的子）
# ───────────────────────────────────────────────
class GoRule(Rule):
    name = "go"

    def is_valid_move(self, x, y, color):
        # 坐标合法 & 为空
        if not (self.board.in_bounds(x, y) and self.board.get(x, y) == EMPTY):
            return False
        # 检查自杀：如果落子后本方无气且没有提子，则不合法
        self.board.place_stone(x, y, color)
        captured = self._capture_opponents(x, y, color, pretend=True)
        if self._group_has_liberty(x, y, color) or captured:
            self.board.set(x, y, EMPTY)  # 还原
            return True
        self.board.set(x, y, EMPTY)
        return False

    def apply_move(self, x, y, color):
        if x == -1 and y == -1:  # pass
            self.passes_in_row += 1
            print(f"{color} 方选择 Pass（{self.passes_in_row} 连 pass）")
            # 连续两次 pass 判终局
            return self.passes_in_row >= 2
        else:
            self.passes_in_row = 0  # 重置 pass 计数

        self.board.place_stone(x, y, color)
        captured = self._capture_opponents(x, y, color, pretend=False)
        self.board.history.append((x, y, color, captured))
        return False  # 围棋终局由 pass 或投降等决定

    # ── 私有工具 ────────────────────────────────
    def _neighbors(self, x, y):
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            nx, ny = x + dx, y + dy
            if self.board.in_bounds(nx, ny):
                yield nx, ny

    def _group_dfs(self, x, y, color):
        """返回与 (x,y) 同色连通块 & 其气"""
        stack = [(x, y)]
        visited = set()
        liberties = set()
        group = []
        while stack:
            cx, cy = stack.pop()
            if (cx, cy) in visited:
                continue
            visited.add((cx, cy))
            group.append((cx, cy))
            for nx, ny in self._neighbors(cx, cy):
                if self.board.get(nx, ny) == color:
                    stack.append((nx, ny))
                elif self.board.get(nx, ny) == EMPTY:
                    liberties.add((nx, ny))
        return group, liberties

    def _group_has_liberty(self, x, y, color):
        _, libs = self._group_dfs(x, y, color)
        return len(libs) > 0

    def _capture_opponents(self, x, y, color, pretend=False):
        """提掉邻近无气的对方棋子，返回被提子的列表"""
        opponent = self.opposite(color)
        captured = []
        for nx, ny in self._neighbors(x, y):
            if self.board.get(nx, ny) == opponent:
                group, libs = self._group_dfs(nx, ny, opponent)
                if len(libs) == 0:  # 无气，提子
                    captured.extend(group)
        if not pretend and captured:
            self.board.remove_stones(captured)
        return captured

    # 终局点击 pass 两次即可，胜负判断采用极简“地+子”：
    def score(self):
        black, white = 0, 0
        for y in range(self.board.size):
            for x in range(self.board.size):
                stone = self.board.get(x, y)
                if stone == BLACK:
                    black += 1
                elif stone == WHITE:
                    white += 1
        return black, white


# ───────────────────────────────────────────────
# 玩家
# ───────────────────────────────────────────────
class Player:
    def __init__(self, name: str, color: str):
        self.name = name
        self.color = color  # "B" or "W"


# ───────────────────────────────────────────────
# 游戏控制器 GameController
# ───────────────────────────────────────────────
class GameController:
    """负责解析指令并调用 Board / Rule"""

    def __init__(self):
        self.board: Optional[Board] = None
        self.rule: Optional[Rule] = None
        self.players: List[Player] = []
        self.current_idx: int = 0  # 当前轮到的玩家索引

    # ── 高层 API ────────────────────────────────
    def start_game(self):
        game_type = input("请选择游戏类型（gomoku/go）：").strip().lower()
        size = int(input("请输入棋盘大小（8-19）：").strip())
        self.board = Board(size)
        if game_type == "gomoku":
            self.rule = GomokuRule(self.board)
        elif game_type == "go":
            self.rule = GoRule(self.board)
        else:
            raise ValueError("未知游戏类型")
        # 创建玩家
        self.players = [Player("黑方", BLACK), Player("白方", WHITE)]
        self.current_idx = 0
        self.board.display()

    def switch_player(self):
        self.current_idx = 1 - self.current_idx

    @property
    def current_player(self) -> Player:
        return self.players[self.current_idx]

    # ── 指令解析 ────────────────────────────────
    def run(self):
        print("输入 'help' 查看指令列表")
        while True:
            try:
                cmd = input("> ").strip()
                if cmd == "help":
                    self.print_help()
                elif cmd == "start":
                    self.start_game()
                elif cmd.startswith("move"):
                    self.command_move(cmd)
                elif cmd == "pass":
                    self.command_pass()
                elif cmd == "undo":
                    self.command_undo()
                elif cmd == "resign":
                    print(f"{self.current_player.name} 认输，对局结束")
                    break
                elif cmd.startswith("save"):
                    self.command_save(cmd)
                elif cmd.startswith("load"):
                    self.command_load(cmd)
                elif cmd == "exit":
                    print("再见！")
                    break
                else:
                    print("无效指令，输入 'help' 获取帮助")
            except Exception as e:
                print(f"错误：{e}")

    # ─────────────────────────────────────────
    # 各指令实现
    # ─────────────────────────────────────────
    def command_move(self, cmd: str):
        if self.board is None:
            print("请先 start 开始游戏")
            return
        match = re.match(r"move\s+(\d+)\s+(\d+)", cmd)
        if not match:
            print("格式：move x y")
            return
        x, y = map(int, match.groups())
        color = self.current_player.color
        if not self.rule.is_valid_move(x, y, color):
            print("该位置不可落子")
            return
        game_over = self.rule.apply_move(x, y, color)
        self.board.display()
        if game_over:
            print("对局结束")
            exit()
        self.switch_player()

    def command_pass(self):
        if self.board is None or self.rule.name != "go":
            print("仅围棋支持 pass")
            return
        game_over = self.rule.apply_move(-1, -1, self.current_player.color)
        self.switch_player()
        if game_over:
            black, white = self.rule.score()
            print(f"终局：黑 {black} 目，白 {white} 目")
            print("黑胜" if black > white else "白胜" if white > black else "平局")
            exit()

    def command_undo(self):
        if self.board is None:
            print("尚未开始游戏")
            return
        try:
            self.rule.undo()
            self.switch_player()
            self.board.display()
            print("悔棋成功")
        except ValueError as ve:
            print(ve)

    def command_save(self, cmd: str):
        if self.board is None:
            print("尚未开始游戏")
            return
        match = re.match(r"save\s+(\S+)", cmd)
        if not match:
            print("格式：save filename")
            return
        filename = match.group(1)
        data = {
            "rule": self.rule.name,
            "board": self.board.to_dict(),
            "current": self.current_idx
        }
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f)
        print(f"已保存到 {filename}")

    def command_load(self, cmd: str):
        match = re.match(r"load\s+(\S+)", cmd)
        if not match:
            print("格式：load filename")
            return
        filename = match.group(1)
        if not os.path.exists(filename):
            print("文件不存在")
            return
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 还原棋盘和规则
        self.board = Board.from_dict(data["board"])
        rule_name = data["rule"]
        self.rule = GomokuRule(self.board) if rule_name == "gomoku" else GoRule(self.board)
        self.current_idx = data["current"]
        self.players = [Player("黑方", BLACK), Player("白方", WHITE)]
        print("载入成功，当前棋盘：")
        self.board.display()

    @staticmethod
    def print_help():
        print("""指令列表:
start                 - 开始新游戏
move x y              - 在 (x,y) 落子
pass                  - 围棋虚着
undo                  - 悔棋一步
resign                - 投子认负
save filename         - 保存局面
load filename         - 读取局面
help                  - 显示帮助
exit                  - 退出 """)


