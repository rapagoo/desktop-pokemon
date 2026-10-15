"""저장소: 파티 진행 상황을 불러오고 저장한다. 화면(Tk)과 무관한 순수 파일 작업.

저장 위치
  - 기본: 프로젝트 폴더의 party.json (이 PC에만 저장)
  - 클라우드: settings.json의 save_dir (Dropbox·OneDrive 등) 아래 DesktopPokemon/save.json
    → 학원 PC와 집 PC가 같은 폴더를 보면 진행 상황이 이어진다.

여러 PC 안전장치
  - running.json: 실행 중인 PC가 1분마다 갱신. 다른 PC의 기록이 3분 안이면 "실행 중"으로 본다.
  - 저장할 때 내가 불러온 뒤 다른 PC가 저장했으면 덮어쓰지 않고 save-conflict-<PC>.json 에 따로 저장.

나중에 계정·DB 방식이 필요하면 같은 메서드(load/save/other_running/heartbeat/release)를 가진
클래스로 바꿔 끼우면 된다.
"""
import json
import socket
import time
from pathlib import Path

SAVE_FOLDER = "DesktopPokemon"
HEARTBEAT_STALE_S = 180


def machine_name():
    return socket.gethostname()


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path, data):
    """임시 파일에 쓰고 바꿔치기 (저장 도중 꺼져도 파일이 깨지지 않게)."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


class SaveStore:
    def __init__(self, local_file, settings_file):
        self.local_file = Path(local_file)
        self.settings_file = Path(settings_file)
        self.machine = machine_name()
        self.loaded_at = 0.0          # 마지막으로 불러온(또는 저장한) 기록의 saved_at

    # -------------------------------------------------- 위치
    @property
    def save_dir(self):
        """클라우드 저장 폴더 (설정 안 했으면 None)."""
        d = (read_json(self.settings_file, {}) or {}).get("save_dir")
        return Path(d) / SAVE_FOLDER if d else None

    @property
    def save_file(self):
        return self.save_dir / "save.json" if self.save_dir else self.local_file

    @property
    def lock_file(self):
        return self.save_dir / "running.json" if self.save_dir else None

    def set_save_dir(self, folder):
        settings = read_json(self.settings_file, {}) or {}
        settings["save_dir"] = str(folder) if folder else None
        write_json(self.settings_file, settings)

    def describe(self):
        return str(self.save_dir.parent) if self.save_dir else "이 PC (party.json)"

    # -------------------------------------------------- 불러오기 / 저장
    @staticmethod
    def parse(data):
        """저장 파일 내용 -> {"party": [...], "machine", "saved_at"}. 예전 형식(파티 리스트만)도 읽는다."""
        if isinstance(data, list):
            return {"party": data, "machine": None, "saved_at": 0.0}
        if isinstance(data, dict) and isinstance(data.get("party"), list):
            return {"party": data["party"], "machine": data.get("machine"),
                    "saved_at": float(data.get("saved_at") or 0)}
        return None

    def peek(self, path=None):
        """저장 파일을 읽기만 한다 (없으면 None)."""
        return self.parse(read_json(path or self.save_file))

    def load(self):
        rec = self.peek()
        self.loaded_at = rec["saved_at"] if rec else 0.0
        return rec

    def save(self, party):
        """저장하고 실제로 쓴 경로를 돌려준다."""
        target = self.save_file
        target.parent.mkdir(parents=True, exist_ok=True)
        current = self.peek()
        if current and current["machine"] not in (None, self.machine) \
                and current["saved_at"] > self.loaded_at:
            # 내가 불러온 뒤 다른 PC가 저장함 → 덮어쓰지 않음
            target = target.with_name(f"save-conflict-{self.machine}.json")
        now = time.time()
        write_json(target, {"version": 2, "machine": self.machine, "saved_at": now, "party": party})
        if target == self.save_file:
            self.loaded_at = now
        return target

    # -------------------------------------------------- 실행 중 표시
    def other_running(self):
        """다른 PC에서 지금 실행 중이면 그 PC 이름, 아니면 None."""
        if not self.lock_file:
            return None
        lock = read_json(self.lock_file)
        if lock and lock.get("machine") != self.machine \
                and time.time() - float(lock.get("heartbeat", 0)) < HEARTBEAT_STALE_S:
            return lock.get("machine")
        return None

    def heartbeat(self):
        if self.lock_file:
            self.lock_file.parent.mkdir(parents=True, exist_ok=True)
            write_json(self.lock_file, {"machine": self.machine, "heartbeat": time.time()})

    def release(self):
        lock = read_json(self.lock_file) if self.lock_file else None
        if lock and lock.get("machine") == self.machine:
            self.lock_file.unlink(missing_ok=True)
