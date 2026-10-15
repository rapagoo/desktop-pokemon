"""관리 창: 파티 / 보관함 / 도감 / 기록 / 설정을 한곳에서.

여는 방법: Ctrl+Alt+P, 포켓몬 더블클릭, 우클릭 → 관리 창 열기.
닫으면 숨기기만 하므로 다시 열 때 빠르다. 열려 있는 동안 1초마다 지금 탭을 새로 그린다.
"""
import time
import tkinter as tk
from tkinter import ttk

from . import dex, screen
from .config import CAPTURE_GUARD, MAX_NUM, MAX_PARTY, START_LEVEL
from .util import exp_for, poke_name

FONT = ("맑은 고딕", 10)
FONT_B = ("맑은 고딕", 10, "bold")
FONT_S = ("맑은 고딕", 9)
MUTED = "#6b6b6b"
STATUS_COLORS = {"caught": "#8fd16a", "seen": "#8dbdf0", "unknown": "#f4f3ef"}   # 만남과 모름이 확실히 구분되게
TYPE_KO = {
    "normal": "노말", "fire": "불꽃", "water": "물", "electric": "전기", "grass": "풀", "ice": "얼음",
    "fighting": "격투", "poison": "독", "ground": "땅", "flying": "비행", "psychic": "에스퍼",
    "bug": "벌레", "rock": "바위", "ghost": "고스트", "dragon": "드래곤", "dark": "악", "steel": "강철",
    "fairy": "페어리",
}
DEX_COLS, DEX_CELL = 16, 28


def types_ko(types):
    return "/".join(TYPE_KO.get(t, t) for t in types)


class Manager:
    def __init__(self, app):
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title("바탕화면 포켓몬")
        self.win.geometry("680x640")
        self.win.minsize(560, 420)
        self.win.protocol("WM_DELETE_WINDOW", self.win.withdraw)
        self.win.bind("<Escape>", lambda e: self.win.withdraw())
        style = ttk.Style(self.win)
        style.configure(".", font=FONT)
        style.configure("Treeview", rowheight=24)

        top = ttk.Frame(self.win, padding=(12, 8))
        top.pack(fill="x")
        self.status = ttk.Label(top, foreground=MUTED, font=FONT_S)
        self.status.pack(side="right")
        ttk.Label(top, text="바탕화면 포켓몬", font=("맑은 고딕", 11, "bold")).pack(side="left")

        self.tabs = ttk.Notebook(self.win)
        self.tabs.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.pages = {}
        for key, title, build in (("party", "파티", self.build_party), ("box", "보관함", self.build_box),
                                  ("dex", "도감", self.build_dex), ("log", "기록", self.build_log),
                                  ("settings", "설정", self.build_settings)):
            frame = ttk.Frame(self.tabs, padding=10)
            self.tabs.add(frame, text=title)
            self.pages[key] = frame
            build(frame)
        self.tabs.bind("<<NotebookTabChanged>>", lambda e: self.refresh())
        # 포켓몬 창은 항상 위라서, 이 창을 쓰는 동안만 그보다 위로. 다른 앱으로 가면 내려놓음.
        self.win.bind("<FocusIn>", lambda e: self.win.attributes("-topmost", True))
        self.win.bind("<FocusOut>", lambda e: self.win.after(100, self.drop_if_unfocused))
        self.guarded = False
        self.tick()

    def drop_if_unfocused(self):
        if self.win.focus_get() is None:
            self.win.attributes("-topmost", False)

    # -------------------------------------------------- 공통
    def show(self, tab=None):
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
        if CAPTURE_GUARD and not self.guarded:          # 화면 공유에 안 보이게 (처음 보일 때 한 번)
            self.win.update_idletasks()
            self.guarded = screen.exclude_from_capture(self.win)
        if tab:
            self.tabs.select(self.pages[tab])
        self.refresh()

    @property
    def visible(self):
        return self.win.winfo_viewable()

    def current(self):
        return next(k for k, f in self.pages.items() if str(f) == self.tabs.select())

    def refresh(self):
        if not self.visible:
            return
        a = self.app
        saved = time.strftime("%H:%M", time.localtime(a.store.loaded_at)) if a.store.loaded_at else "아직 안 함"
        where = "클라우드 연동" if a.store.save_dir else "이 PC에만 저장"
        self.status.config(text=f"{a.store.nickname} · {where} · 마지막 저장 {saved}")
        self.tabs.tab(self.pages["box"], text=f"보관함 {len(a.box)}")
        self.tabs.tab(self.pages["dex"], text=f"도감 {len(a.caught & set(dex.DATA))}/{MAX_NUM}")
        getattr(self, f"refresh_{self.current()}")()

    def tick(self):
        self.refresh()
        self.win.after(1000, self.tick)

    def portrait(self, num, size=1):
        return self.app.portrait(num, "Normal", zoom=size)

    # -------------------------------------------------- 파티
    def build_party(self, f):
        self.party_head = ttk.Label(f, foreground=MUTED, font=FONT_S)
        self.party_head.pack(anchor="w", pady=(0, 6))
        self.party_rows = ttk.Frame(f)
        self.party_rows.pack(fill="both", expand=True)
        self.party_key = None

    def refresh_party(self):
        party = self.app.party()
        self.party_head.config(text=f"파티 {len(party)}/{MAX_PARTY} · 쓰다듬기로 친밀도가 오르고, "
                                    f"보관함으로 보내면 화면에서 쉬어요")
        key = tuple(id(p) for p in party)
        if key != self.party_key:                       # 구성이 바뀌었을 때만 줄을 새로 만듦
            self.party_key = key
            for w in self.party_rows.winfo_children():
                w.destroy()
            self.rows = [self.party_row(p) for p in party]
        for p, row in zip(party, self.rows):
            self.update_row(p, row)

    def party_row(self, p):
        row = ttk.Frame(self.party_rows, padding=6, relief="solid", borderwidth=1)
        row.pack(fill="x", pady=3)
        img = self.portrait(p.num)
        face = tk.Label(row, image=img or "", width=40 if img else 6, bg="#f0efea")
        face.image = img
        face.grid(row=0, column=0, rowspan=3, padx=(0, 10))
        title = ttk.Label(row, font=FONT_B)
        title.grid(row=0, column=1, sticky="w")
        sub = ttk.Label(row, foreground=MUTED, font=FONT_S)
        sub.grid(row=1, column=1, sticky="w")
        hint = ttk.Label(row, foreground="#2f6db3", font=FONT_S)
        hint.grid(row=2, column=1, columnspan=3, sticky="w")
        bar = tk.Canvas(row, width=110, height=8, highlightthickness=0, bg="#e4e2db")
        bar.grid(row=0, column=2, padx=10, sticky="s")
        nums = ttk.Label(row, foreground=MUTED, font=FONT_S)
        nums.grid(row=1, column=2, padx=10, sticky="n")
        btns = ttk.Frame(row)
        btns.grid(row=0, column=3, rowspan=2)
        ttk.Button(btns, text="쓰다듬기", width=8, command=lambda: (p.pat(), self.refresh())).pack(side="left")
        ttk.Button(btns, text="재우기", width=6,
                   command=lambda: p.state in ("walk", "idle") and p.set_state("sleep", 20000)).pack(side="left")
        ttk.Button(btns, text="보관함으로", width=9,
                   command=lambda: self.app.to_box(p)).pack(side="left")
        row.columnconfigure(1, weight=1)
        return {"title": title, "sub": sub, "hint": hint, "bar": bar, "nums": nums}

    def update_row(self, p, row):
        state = {"sleep": " · 자는 중", "battle": " · 배틀 중", "fainted": " · 쓰러져 쉬는 중",
                 "evolving": " · 진화 중!"}.get(p.state, "")
        row["title"].config(text=f"{'✨' if p.shiny else ''}{p.name}  Lv.{p.level}{state}")
        row["sub"].config(text=f"{types_ko(p.dex['types'])} · 친밀도 {p.friendship}")
        hint = dex.evolution_hint(p.num, p.friendship)
        row["hint"].config(text=f"다음 진화 → {hint}" if hint else "더 진화하지 않아요")
        lo, hi = exp_for(p.level), exp_for(p.level + 1)
        exp_pct = int(100 * (p.exp - lo) / max(1, hi - lo))
        ratio = max(0.0, p.hp / p.max_hp)
        color = "#3cb043" if ratio > .5 else "#f1c232" if ratio > .2 else "#e06666"
        bar = row["bar"]
        bar.delete("all")
        bar.create_rectangle(0, 0, int(110 * ratio), 8, fill=color, outline="")
        row["nums"].config(text=f"HP {int(p.hp)}/{p.max_hp} · EXP {exp_pct}%")

    # -------------------------------------------------- 보관함
    def build_box(self, f):
        self.box_head = ttk.Label(f, foreground=MUTED, font=FONT_S)
        self.box_head.pack(anchor="w", pady=(0, 6))
        cols = ("num", "name", "level", "friend", "hint")
        self.box_tree = ttk.Treeview(f, columns=cols, show="headings", selectmode="browse")
        for c, t, w in zip(cols, ("번호", "이름", "레벨", "친밀도", "다음 진화"), (50, 100, 50, 60, 300)):
            self.box_tree.heading(c, text=t)
            self.box_tree.column(c, width=w, anchor="w" if c in ("name", "hint") else "center")
        self.box_tree.pack(fill="both", expand=True)
        self.box_tree.bind("<Double-Button-1>", lambda e: self.box_withdraw())
        btns = ttk.Frame(f)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="파티로 데려오기", command=self.box_withdraw).pack(side="left")
        ttk.Button(btns, text="놓아주기…", command=self.box_release).pack(side="right")
        self.box_key = None

    def refresh_box(self):
        a = self.app
        self.box_head.config(text=f"보관함 {len(a.box)}마리 · 파티 {len(a.party())}/{MAX_PARTY} · "
                                  "파티가 가득 찼을 때 잡은 포켓몬도 여기로 와요")
        key = tuple((r["num"], r.get("level"), r.get("friendship")) for r in a.box)
        if key == self.box_key:
            return
        self.box_key = key
        self.box_tree.delete(*self.box_tree.get_children())
        for i, r in enumerate(a.box):
            self.box_tree.insert("", "end", iid=str(i), values=(
                r["num"], poke_name(r["num"], a.names), r.get("level", START_LEVEL),
                r.get("friendship", 0), dex.evolution_hint(r["num"], r.get("friendship", 0)) or "-"))

    def selected_box(self):
        sel = self.box_tree.selection()
        return int(sel[0]) if sel else None

    def box_withdraw(self):
        i = self.selected_box()
        if i is None:
            return
        if len(self.app.party()) >= MAX_PARTY:
            self.box_head.config(text="파티가 가득 찼어요. 먼저 파티에서 한 마리를 보관함으로 보내 주세요.")
            return
        self.app.from_box(i)
        self.box_key = None
        self.refresh()

    def box_release(self):
        i = self.selected_box()
        if i is not None:
            self.app.release_from_box(i)
            self.box_key = None
            self.refresh()

    # -------------------------------------------------- 도감
    def build_dex(self, f):
        self.dex_head = ttk.Label(f, foreground=MUTED, font=FONT_S)
        self.dex_head.pack(anchor="w", pady=(0, 6))
        body = ttk.Frame(f)
        body.pack(fill="both", expand=True)
        rows = (MAX_NUM + DEX_COLS - 1) // DEX_COLS
        self.dex_canvas = tk.Canvas(body, width=DEX_COLS * DEX_CELL, highlightthickness=0, bg="white",
                                    scrollregion=(0, 0, DEX_COLS * DEX_CELL, rows * DEX_CELL))
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.dex_canvas.yview)
        self.dex_canvas.configure(yscrollcommand=scroll.set)
        self.dex_canvas.pack(side="left", fill="y")
        scroll.pack(side="left", fill="y")
        self.dex_canvas.bind("<MouseWheel>", lambda e: self.dex_canvas.yview_scroll(-e.delta // 120, "units"))
        self.dex_canvas.bind("<Button-1>", self.dex_click)
        self.dex_cells = {}
        for n in range(1, MAX_NUM + 1):
            r, c = divmod(n - 1, DEX_COLS)
            x, y = c * DEX_CELL, r * DEX_CELL
            rect = self.dex_canvas.create_rectangle(x + 1, y + 1, x + DEX_CELL - 1, y + DEX_CELL - 1,
                                                    outline="#d8d6ce", fill=STATUS_COLORS["unknown"])
            self.dex_canvas.create_text(x + DEX_CELL / 2, y + DEX_CELL / 2, text=str(n), font=("맑은 고딕", 7),
                                        fill="#555")
            self.dex_cells[n] = rect
        self.dex_detail = ttk.Frame(body, padding=(12, 0))
        self.dex_detail.pack(side="left", fill="both", expand=True)
        self.dex_face = tk.Label(self.dex_detail)
        self.dex_face.pack(anchor="w")
        self.dex_name = ttk.Label(self.dex_detail, font=("맑은 고딕", 12, "bold"))
        self.dex_name.pack(anchor="w", pady=(6, 0))
        self.dex_info = ttk.Label(self.dex_detail, foreground=MUTED, font=FONT_S, wraplength=170, justify="left")
        self.dex_info.pack(anchor="w", pady=(4, 0))
        legend = ttk.Frame(self.dex_detail)
        legend.pack(side="bottom", anchor="w")
        for i, (key, label) in enumerate((("caught", "잡음"), ("seen", "만남"), ("unknown", "아직 모름"))):
            tk.Label(legend, bg=STATUS_COLORS[key], width=2).grid(row=i, column=0, pady=1)
            ttk.Label(legend, text=label, font=FONT_S).grid(row=i, column=1, sticky="w", padx=4)
        self.dex_selected = None
        self.dex_key = None

    def status_of(self, n):
        return "caught" if n in self.app.caught else "seen" if n in self.app.seen else "unknown"

    def refresh_dex(self):
        a = self.app
        caught, seen = len(a.caught & set(dex.DATA)), len((a.seen | a.caught) & set(dex.DATA))
        self.dex_head.config(text=f"잡음 {caught} · 만남 {seen} · 전체 {MAX_NUM}  (칸을 누르면 정보)")
        key = (frozenset(a.caught), frozenset(a.seen))   # 수가 같아도 내용이 바뀌면(다른 PC 기록 불러오기) 다시 칠함
        if key != self.dex_key:
            self.dex_key = key
            for n, rect in self.dex_cells.items():
                self.dex_canvas.itemconfigure(rect, fill=STATUS_COLORS[self.status_of(n)])
            if self.dex_selected:
                self.show_dex_entry(self.dex_selected)

    def dex_click(self, e):
        x, y = self.dex_canvas.canvasx(e.x), self.dex_canvas.canvasy(e.y)
        n = int(y // DEX_CELL) * DEX_COLS + int(x // DEX_CELL) + 1
        if 1 <= n <= MAX_NUM:
            self.show_dex_entry(n)

    def show_dex_entry(self, n):
        self.dex_selected = n
        status = self.status_of(n)
        e = dex.entry(n)
        if status == "unknown":
            self.dex_face.config(image="", text="?", font=("맑은 고딕", 28), width=3)
            self.dex_name.config(text=f"No.{n:03d}  ???")
            self.dex_info.config(text="아직 만나지 못했어요.")
            return
        img = self.portrait(n, 2)
        self.dex_face.config(image=img or "", text="" if img else "?", width=80 if img else 3)
        self.dex_face.image = img
        self.dex_name.config(text=f"No.{n:03d}  {e['name']}")
        lines = [types_ko(e["types"]), "잡음" if status == "caught" else "만남 (아직 못 잡음)"]
        if e["from"]:
            lines.append(f"{dex.name(e['from'])}에서 진화")
        hint = dex.evolution_hint(n)
        if hint:
            lines.append("진화: " + hint)
        if e["legendary"]:
            lines.append("전설의 포켓몬")
        self.dex_info.config(text="\n".join(lines))

    # -------------------------------------------------- 기록
    def build_log(self, f):
        cols = ("time", "pc", "text")
        self.log_tree = ttk.Treeview(f, columns=cols, show="headings")
        for c, t, w in zip(cols, ("시각", "PC", "내용"), (110, 60, 420)):
            self.log_tree.heading(c, text=t)
            self.log_tree.column(c, width=w, anchor="w")
        self.log_tree.pack(fill="both", expand=True)
        self.log_key = None

    def refresh_log(self):
        events = self.app.events
        key = (len(events), events[-1]["t"] if events else 0)
        if key == self.log_key:
            return
        self.log_key = key
        self.log_tree.delete(*self.log_tree.get_children())
        for ev in reversed(events):
            when = time.strftime("%m/%d %H:%M", time.localtime(ev["t"]))
            self.log_tree.insert("", "end", values=(when, ev.get("pc", ""), ev["text"]))

    # -------------------------------------------------- 설정
    def build_settings(self, f):
        a = self.app

        def section(title):
            ttk.Label(f, text=title, font=FONT_B).pack(anchor="w", pady=(10, 4))
            box = ttk.Frame(f)
            box.pack(fill="x")
            return box

        s = section("저장 · 학원 ↔ 집 연동")
        self.save_label = ttk.Label(s, foreground=MUTED, font=FONT_S)
        self.save_label.pack(anchor="w")
        row = ttk.Frame(s)
        row.pack(anchor="w", pady=4)
        ttk.Button(row, text="클라우드 폴더로 바꾸기…", command=a.choose_save_dir).pack(side="left")
        ttk.Button(row, text="이 PC에만 저장", command=a.use_local_save).pack(side="left", padx=6)
        ttk.Button(row, text="지금 저장", command=a.save).pack(side="left")

        s = section("이 PC 별명")
        row = ttk.Frame(s)
        row.pack(anchor="w")
        self.nick = tk.StringVar(value=a.store.nickname)
        ttk.Entry(row, textvariable=self.nick, width=16).pack(side="left")
        ttk.Button(row, text="바꾸기", command=lambda: (a.store.set_nickname(self.nick.get()), a.save())
                   ).pack(side="left", padx=6)
        ttk.Label(s, text="교환 대화창에 \"학원에서 왔어!\"처럼 나와요.", foreground=MUTED, font=FONT_S
                  ).pack(anchor="w", pady=(2, 0))

        s = section("수업 중")
        self.auto_hide = tk.BooleanVar(value=a.auto_hide)
        ttk.Checkbutton(s, text="전체 화면 앱(영상·발표)이 켜지면 자동으로 숨기기", variable=self.auto_hide,
                        command=lambda: a.set_auto_hide(self.auto_hide.get())).pack(anchor="w")
        row = ttk.Frame(s)
        row.pack(anchor="w", pady=4)
        ttk.Button(row, text="5분 숨기기", command=lambda: a.hide(5 * 60 * 1000)).pack(side="left")
        ttk.Button(row, text="야생 포켓몬 지금 부르기", command=a.call_wild).pack(side="left", padx=6)

        s = section("단축키")
        ttk.Label(s, text="Ctrl + Alt + P : 이 창 열기    ·    포켓몬 더블클릭 : 이 창 열기    ·    Esc : 닫기",
                  foreground=MUTED, font=FONT_S).pack(anchor="w")

        ttk.Button(f, text="바탕화면 포켓몬 종료", command=a.quit).pack(anchor="e", side="bottom")

    def refresh_settings(self):
        a = self.app
        self.save_label.config(text=f"지금 저장 위치: {a.store.describe()}")
