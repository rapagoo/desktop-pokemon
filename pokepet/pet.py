"""포켓몬 한 마리: 창, 움직임(걷기·잠·낙하·드래그), 애니메이션, 말풍선, HP 바, 스탯."""
import math
import random
import tkinter as tk

from . import screen
from .config import (
    CAPTURE_GUARD,
    GRAVITY,
    HAPPY,
    HOLD_LAST,
    KEY,
    REGEN_FULL_MS,
    SPEED_RANGE,
    START_LEVEL,
    TICK,
)
from .util import calc_stat, chant, exp_for


class Pet:
    BUBBLE_H = 34

    def __init__(self, app, num, shiny, sprite, name, dex, wild=False,
                 level=START_LEVEL, exp=None, hp=None, friendship=0):
        self.app, self.num, self.shiny, self.sp, self.name = app, num, shiny, sprite, name
        self.dex, self.wild, self.level = dex, wild, level
        self.exp = exp if exp is not None else exp_for(level)
        self.hp = float(hp) if hp is not None else float(self.max_hp)
        self.cw = max(sprite.w, 120)
        self.ch = sprite.h + self.BUBBLE_H

        self.win = tk.Toplevel(app.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.config(bg=KEY)
        try:
            self.win.attributes("-transparentcolor", KEY)
        except tk.TclError:
            pass
        self.cv = tk.Canvas(self.win, width=self.cw, height=self.ch, bg=KEY,
                            highlightthickness=0, bd=0)
        self.cv.pack()
        self.img_id = self.cv.create_image(self.cw // 2, self.ch, anchor="s",
                                           image=sprite.anims["idle"].left[0])
        # HP 바는 머리 위, 말풍선은 그 위
        self.bar_y = max(self.BUBBLE_H - 8, self.BUBBLE_H + sprite.head_top - 10)
        self.bar_ids = []
        self.bubble_ids = []
        self.bubble_ttl = 0

        l, t, r, b = app.area
        self.vx = self.vy = 0.0
        self.facing = random.choice((-1, 1))
        self.anim_name, self.frame, self.frame_t, self.bob_t = "idle", 0, 0, 0
        self.action, self.action_done = None, None
        self.drag = None
        self.friendship = friendship  # 쓰다듬은 횟수 (친밀도 진화에 사용)
        self.cool = 0                 # 다른 포켓몬과 인사 쿨타임
        if wild:                      # 화면 가장자리 밖에서 걸어 들어옴
            self.facing = random.choice((-1, 1))
            self.x = l - self.cw if self.facing > 0 else r
            self.y = self.floor
            self.state, self.state_t = "approach", 0
        else:
            self.x = random.uniform(l, r - self.cw)
            self.y = t - self.ch          # 화면 위에서 떨어지며 등장
            self.state, self.state_t = "fall", 0

        self.cv.bind("<ButtonPress-1>", self.on_press)
        self.cv.bind("<B1-Motion>", self.on_motion)
        self.cv.bind("<ButtonRelease-1>", self.on_release)
        self.cv.bind("<Button-3>", self.on_menu)
        self.cv.bind("<Double-Button-1>", lambda e: app.open_manager())
        self.place()
        if CAPTURE_GUARD:                 # 창이 실제로 만들어진 뒤에 걸어야 적용됨
            self.win.update_idletasks()
            screen.exclude_from_capture(self.win)
        if shiny and not wild:
            self.say("✨ 색이 다르다!", 2500)

    # -------------------------------------------------- stats
    @property
    def display_name(self):
        return f"{'야생 ' if self.wild else ''}{'✨' if self.shiny else ''}{self.name} Lv.{self.level}"

    @property
    def max_hp(self):
        return calc_stat(self.dex["stats"]["hp"], self.level, is_hp=True)

    def stat(self, key):
        return calc_stat(self.dex["stats"][key], self.level)

    @property
    def cx(self):
        return self.x + self.cw / 2

    def gain_exp(self, amount):
        """경험치를 얻고 오른 레벨 수를 돌려준다."""
        self.exp += amount
        ups = 0
        while self.exp >= exp_for(self.level + 1) and self.level < 100:
            old = self.max_hp
            self.level += 1
            self.hp += self.max_hp - old
            ups += 1
        return ups

    # -------------------------------------------------- geometry
    @property
    def floor(self):
        return self.app.area[3] - self.ch + self.sp.pad_bottom

    def place(self):
        self.win.geometry(f"{self.cw}x{self.ch}+{int(self.x)}+{int(self.y)}")

    # -------------------------------------------------- speech bubble & HP bar
    def say(self, text, ms=1800):
        for i in self.bubble_ids:
            self.cv.delete(i)
        y = max(14, self.bar_y - 16)
        tid = self.cv.create_text(self.cw // 2, y, text=text, fill="#222",
                                  font=("맑은 고딕", 9, "bold"))
        x1, y1, x2, y2 = self.cv.bbox(tid)
        rid = self.cv.create_rectangle(x1 - 7, y1 - 3, x2 + 7, y2 + 3,
                                       fill="white", outline="#555")
        self.cv.tag_raise(tid)
        self.bubble_ids = [rid, tid]
        self.bubble_ttl = ms

    def clear_bubble(self):
        for i in self.bubble_ids:
            self.cv.delete(i)
        self.bubble_ids = []

    def draw_bar(self):
        show = self.wild or self.state in ("battle", "fainted") or self.hp < self.max_hp - 0.5
        key = (show, self.level, int(self.hp))
        if key == getattr(self, "_bar_key", None):
            return
        self._bar_key = key
        for i in self.bar_ids:
            self.cv.delete(i)
        self.bar_ids = []
        if not show:
            return
        w, x0, y = 56, self.cw // 2 - 20, self.bar_y
        ratio = max(0.0, self.hp / self.max_hp)
        color = "#3cb043" if ratio > .5 else "#f1c232" if ratio > .2 else "#e06666"
        # 글자는 흰 바탕 위에 (투명색 위에 바로 쓰면 가장자리가 분홍색으로 번짐)
        label = self.cv.create_text(x0 - 5, y + 2, text=f"Lv{self.level}", anchor="e", fill="#111",
                                    font=("맑은 고딕", 8, "bold"))
        lx1, ly1, lx2, ly2 = self.cv.bbox(label)
        self.bar_ids = [
            self.cv.create_rectangle(lx1 - 2, ly1, lx2 + 1, ly2, fill="white", outline="#111"),
            label,
            self.cv.create_rectangle(x0, y, x0 + w, y + 5, fill="#444", outline="#111"),
            self.cv.create_rectangle(x0 + 1, y + 1, x0 + 1 + int((w - 1) * ratio), y + 5,
                                     fill=color, outline=""),
        ]
        self.cv.tag_raise(label)
        for i in self.bubble_ids:
            self.cv.tag_raise(i)

    # -------------------------------------------------- AI
    def pick_speed(self, mult=1.0):
        """걷기 애니메이션에 맞는 이동 속도 (px/tick)."""
        if self.sp.walk_speed is None:
            return random.uniform(1.2, 2.4) * mult
        lo, hi = SPEED_RANGE
        return max(lo, min(hi, self.sp.walk_speed * TICK * random.uniform(.85, 1.0) * mult))

    def anim_rate(self):
        """걷는 중이면 실제 이동 속도에 맞춰 애니메이션을 빠르게/느리게 재생."""
        if self.anim_name != "walk" or not self.vx or self.sp.walk_speed is None:
            return 1.0
        return max(.4, min(2.0, abs(self.vx) / (self.sp.walk_speed * TICK)))

    def play(self, anim, on_done=None):
        """한 번만 재생하는 동작 (공격, 피격 등)."""
        self.action, self.action_done = anim, on_done
        self.anim_name, self.frame, self.frame_t = anim, 0, 0

    def set_state(self, s, duration=None):
        self.state = s
        self.state_t = duration if duration is not None else 0
        if s == "walk":
            self.facing = random.choice((-1, 1))
            self.vx = self.facing * self.pick_speed()
        elif s in ("idle", "battle", "fainted", "dazed"):
            self.vx = 0
        elif s == "sleep":
            self.vx = 0
            self.say("Zzz…", duration)
        elif s == "jump":
            self.vy = -random.uniform(9, 13)
            self.state = "fall"

    def choose_next(self):
        r = random.random()
        if r < 0.40:
            self.set_state("idle", random.randint(1500, 5000))
        elif r < 0.85:
            self.set_state("walk", random.randint(2000, 6000))
        elif r < 0.95:
            self.set_state("sleep", random.randint(6000, 15000))
        else:
            self.set_state("jump")
            if random.random() < 0.5:
                self.say(chant(self.name))

    def leave(self):
        """화면 밖으로 걸어 나간다 (야생 포켓몬)."""
        l, t, r, b = self.app.area
        self.state = "leave"
        speed = self.pick_speed(1.3)
        self.vx = -speed if self.cx < (l + r) / 2 else speed

    def arrive(self, order=0):
        """다른 PC에서 온 포켓몬: 화면 옆에서 걸어 들어온다. order번째일수록 더 뒤에서 출발."""
        l, t, r, b = self.app.area
        self.facing = random.choice((-1, 1))
        behind = order * 180
        self.x = l - self.cw - behind if self.facing > 0 else r + behind
        self.y = self.floor
        self.target_x = random.uniform(l + 40, r - self.cw - 40)
        self.vx = self.facing * self.pick_speed()
        self.state = "arrive"

    def land(self):
        if self.hp <= 0:
            self.set_state("dazed" if self.wild else "fainted", 5000 if self.wild else 20000)
        elif self.wild:
            self.state = "approach"
        else:
            self.choose_next()

    def tick(self, dt):
        l, t, r, b = self.app.area

        if self.state == "drag":
            pass
        elif self.state == "fall":
            self.vy += GRAVITY
            self.x += self.vx
            self.y += self.vy
            if self.y >= self.floor:
                self.y = self.floor
                if self.vy > 6:                      # 통통 튀기
                    self.vy = -self.vy * 0.35
                    self.vx *= 0.6
                else:
                    self.vy = 0
                    self.land()
        elif self.state in ("approach", "leave", "arrive"):
            self.y = self.floor
            self.x += self.vx
            if self.state == "leave" and (self.x + self.cw < l or self.x > r):
                self.app.wild_gone(self)
                return
            if self.state == "arrive" and (self.x - self.target_x) * self.vx >= 0:
                self.set_state("idle", 3000)
                self.app.on_arrived(self)
        elif self.state in ("battle",):
            self.y = self.floor
        elif self.state in ("fainted", "dazed"):
            self.y = self.floor
            self.state_t -= dt
            if self.state_t <= 0:
                if self.state == "fainted":
                    self.hp = self.max_hp
                    self.say("다시 힘이 났어!", 1800)
                    self.set_state("idle", 2000)
                else:
                    self.app.wild_escape(self)
        else:
            self.y = self.floor
            self.state_t -= dt
            if self.state == "walk":
                self.x += self.vx
            if self.state_t <= 0:
                if self.state == "sleep":
                    self.say("하암~", 1200)
                self.choose_next()

        # 평소엔 HP가 천천히 회복 (자면 더 빨리)
        if not self.wild and self.state not in ("battle", "fainted") and self.hp < self.max_hp:
            rate = 3 if self.state == "sleep" else 1
            self.hp = min(self.max_hp, self.hp + self.max_hp * dt * rate / REGEN_FULL_MS)

        # 벽에 부딪히면 반대로 (야생 포켓몬이 들어오고 나갈 때는 제외)
        if self.state not in ("approach", "leave", "arrive"):
            if self.x < l:
                self.x, self.vx = l, abs(self.vx)
            elif self.x > r - self.cw:
                self.x, self.vx = r - self.cw, -abs(self.vx)
        if self.vx:
            self.facing = 1 if self.vx > 0 else -1

        self.animate(dt)

        if self.bubble_ids:
            self.bubble_ttl -= dt
            if self.bubble_ttl <= 0:
                if self.state == "sleep":
                    self.say(random.choice(["Zzz…", "zZz…", "Zz…"]), 1500)
                else:
                    self.clear_bubble()
        self.draw_bar()
        self.cool = max(0, self.cool - dt)
        self.place()

    def animate(self, dt):
        if self.action:
            name = self.action
        else:
            name = {"walk": "walk", "approach": "walk", "leave": "walk", "arrive": "walk", "sleep": "sleep",
                    "fainted": "faint", "dazed": "faint"}.get(self.state, "idle")
        if name != self.anim_name:
            self.anim_name, self.frame, self.frame_t = name, 0, 0
        anim = self.sp.anims[name]
        frozen = (self.state == "sleep" and self.sp.pause_sleep) or \
                 (name in HOLD_LAST and self.frame == len(anim.left) - 1)
        if not frozen:
            self.frame_t += dt * self.anim_rate()
            while self.frame_t >= anim.delays[self.frame]:
                self.frame_t -= anim.delays[self.frame]
                if self.frame + 1 < len(anim.left):
                    self.frame += 1
                elif self.action:                     # 한 번 재생하는 동작이 끝남
                    done, self.action, self.action_done = self.action_done, None, None
                    if done:
                        done()
                    return self.animate(0)
                elif name in HOLD_LAST:
                    break
                else:
                    self.frame = 0
        frames = anim.right if self.facing > 0 else anim.left
        self.cv.itemconfig(self.img_id, image=frames[self.frame])
        off = self.sp.lift.get(name, 0)
        if self.sp.static:
            self.bob_t += dt
            if self.state in ("walk", "approach", "leave", "arrive"):   # 걸을 땐 통통 튀기
                off += abs(math.sin(self.bob_t / 110)) * 7
            elif self.state in ("idle", "drag", "battle"):   # 가만히 있을 땐 숨쉬기
                off += 2 if (self.bob_t // 550) % 2 else 0
        if off != getattr(self, "_img_off", 0):
            self._img_off = off
            self.cv.coords(self.img_id, self.cw // 2, self.ch - int(off))

    # -------------------------------------------------- mouse
    def on_press(self, e):
        self.drag = {"ox": e.x_root - self.x, "oy": e.y_root - self.y,
                     "sx": e.x_root, "sy": e.y_root, "moved": False,
                     "hist": [(e.x_root, e.y_root)]}

    def on_motion(self, e):
        d = self.drag
        if not d:
            return
        if not d["moved"] and abs(e.x_root - d["sx"]) + abs(e.y_root - d["sy"]) > 4:
            d["moved"] = True
            self.state = "drag"
            self.action = None
            self.say(random.choice(["으앗!", "?!", "내려줘~"]), 99999)
        if d["moved"]:
            self.x, self.y = e.x_root - d["ox"], e.y_root - d["oy"]
            d["hist"] = (d["hist"] + [(e.x_root, e.y_root)])[-4:]
            self.place()

    def on_release(self, e):
        d, self.drag = self.drag, None
        if not d:
            return
        if d["moved"]:                               # 던지기
            (x0, y0), (x1, y1) = d["hist"][0], d["hist"][-1]
            n = max(1, len(d["hist"]) - 1)
            self.vx = max(-25, min(25, (x1 - x0) / n))
            self.vy = max(-25, min(25, (y1 - y0) / n))
            self.state = "fall"
            self.clear_bubble()
            if math.hypot(self.vx, self.vy) > 12:
                self.say("우와아아~!", 1200)
            return
        # 그냥 클릭
        if self.wild:
            if self.state == "dazed":
                self.app.catch(self)
            else:
                self.say(random.choice(["!", "크르르…", "?!"]), 1000)
            return
        self.pat()

    def pat(self):
        """쓰다듬기 (클릭 또는 관리 창 버튼). 친밀도가 오른다."""
        if self.state == "sleep":
            self.say("…!? 깼다!", 1500)
            self.set_state("idle", 2000)
            return
        if self.state == "evolving":
            self.say("…!", 800)
            return
        if self.state in ("battle", "fainted"):      # 응원만
            self.say("♥ 힘내!" if self.state == "battle" else "…", 1000)
            return
        self.friendship += 1
        if self.friendship % 5 == 0:
            self.say("♥♥♥ 최고야!", 2000)
        else:
            self.say(random.choice(HAPPY + [chant(self.name)]), 1300)
        if self.state != "fall":
            self.set_state("jump")
        self.app.on_pat(self)

    def on_menu(self, e):
        self.app.show_menu(self, e.x_root, e.y_root)

    def destroy(self):
        self.win.destroy()
