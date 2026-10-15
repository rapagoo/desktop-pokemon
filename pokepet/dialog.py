"""화면 구석에 표정 초상화와 함께 뜨는 PMD 스타일 대화창."""
import tkinter as tk



class Dialog:
    """화면 오른쪽 아래에 PMD 스타일 대화창 (표정 초상화 + 글)을 차례로 띄운다."""
    SHOW_MS = 3200

    def __init__(self, app):
        self.app = app
        self.queue = []
        self.busy = False
        self.win = tk.Toplevel(app.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.config(bg="#9fc5e8")
        box = tk.Frame(self.win, bg="#0d1b3d", padx=10, pady=8)
        box.pack(padx=2, pady=2)
        self.face = tk.Label(box, bg="#0d1b3d", bd=0)
        self.face.grid(row=0, column=0, rowspan=2, padx=(0, 10))
        self.title = tk.Label(box, bg="#0d1b3d", fg="#ffd966", anchor="w",
                              font=("맑은 고딕", 10, "bold"))
        self.title.grid(row=0, column=1, sticky="w")
        self.text = tk.Label(box, bg="#0d1b3d", fg="white", anchor="w", justify="left",
                             wraplength=240, font=("맑은 고딕", 10))
        self.text.grid(row=1, column=1, sticky="w")
        self.win.withdraw()
        self.win.bind("<Button-1>", lambda e: self._next())

    def push(self, pet, emotion, text):
        self.app.log(f"[{emotion}] {pet.display_name}: {text}")
        if self.app.hidden:
            return
        self.queue.append((pet.num, pet.display_name, emotion, text))
        if not self.busy:
            self._next()

    def _next(self):
        if not self.queue:
            self.busy = False
            self.win.withdraw()
            return
        self.busy = True
        num, title, emotion, text = self.queue.pop(0)
        img = self.app.portrait(num, emotion)
        self.face.config(image=img or "", width=80 if img else 0)
        self.title.config(text=title)
        self.text.config(text=text)
        self.win.update_idletasks()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        l, t, r, b = self.app.area
        self.win.geometry(f"+{r - w - 16}+{b - h - 16}")
        self.win.deiconify()
        self.win.attributes("-topmost", True)
        token = object()
        self._token = token
        self.app.root.after(self.SHOW_MS, lambda: self._token is token and self._next())
