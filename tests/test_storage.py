"""저장소 테스트: 임시 폴더를 클라우드 폴더 삼아 학원 PC·집 PC 두 대를 흉내 낸다."""
import json
import tempfile
import time
import unittest
from pathlib import Path

from pokepet.storage import SAVE_FOLDER, SaveStore, write_json


def make_store(root, machine, cloud=None):
    """root 아래에 PC 하나의 로컬 파일들을 두고, cloud 폴더를 공유 저장 위치로 쓰는 저장소."""
    pc = Path(root) / machine
    pc.mkdir(exist_ok=True)
    s = SaveStore(pc / "party.json", pc / "settings.json")
    s.machine = machine
    if cloud:
        s.set_save_dir(cloud)
    return s


PIKA = [{"num": 25, "level": 7}]
EEVEE = [{"num": 133, "level": 9}]


class TestSaveStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cloud = self.root / "Dropbox"
        self.cloud.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_local_by_default(self):
        s = make_store(self.root, "academy")
        s.save(PIKA)
        self.assertEqual(s.save_file, self.root / "academy" / "party.json")
        self.assertEqual(s.load()["party"], PIKA)

    def test_reads_old_list_format(self):
        s = make_store(self.root, "academy")
        s.local_file.write_text(json.dumps(PIKA), encoding="utf-8")
        self.assertEqual(s.load()["party"], PIKA)

    def test_two_pcs_share_cloud_save(self):
        academy = make_store(self.root, "academy", self.cloud)
        academy.load()
        academy.save(PIKA)
        home = make_store(self.root, "home", self.cloud)
        rec = home.load()
        self.assertEqual(rec["party"], PIKA)
        self.assertEqual(rec["machine"], "academy")
        self.assertTrue((self.cloud / SAVE_FOLDER / "save.json").exists())

    def test_does_not_overwrite_newer_save_from_other_pc(self):
        academy = make_store(self.root, "academy", self.cloud)
        home = make_store(self.root, "home", self.cloud)
        academy.load()
        home.load()
        home.save(EEVEE)                       # 집에서 먼저 저장
        time.sleep(0.01)
        where = academy.save(PIKA)             # 학원은 그걸 모르고 저장 시도
        self.assertEqual(where.name, "save-conflict-academy.json")
        self.assertEqual(home.peek()["party"], EEVEE)   # 집 기록은 그대로

    def test_same_pc_can_keep_saving(self):
        academy = make_store(self.root, "academy", self.cloud)
        academy.load()
        academy.save(PIKA)
        where = academy.save(EEVEE)
        self.assertEqual(where.name, "save.json")
        self.assertEqual(academy.peek()["party"], EEVEE)

    def test_other_running_detection(self):
        academy = make_store(self.root, "academy", self.cloud)
        home = make_store(self.root, "home", self.cloud)
        academy.heartbeat()
        self.assertEqual(home.other_running(), "academy")
        self.assertIsNone(academy.other_running())      # 내 표시는 무시
        # 오래된 표시(꺼진 지 오래)는 무시
        write_json(home.lock_file, {"machine": "academy", "heartbeat": time.time() - 3600})
        self.assertIsNone(home.other_running())

    def test_release_only_removes_own_lock(self):
        academy = make_store(self.root, "academy", self.cloud)
        home = make_store(self.root, "home", self.cloud)
        academy.heartbeat()
        home.release()
        self.assertTrue(academy.lock_file.exists())
        academy.release()
        self.assertFalse(academy.lock_file.exists())

    def test_nicknames_are_shared_through_save(self):
        academy = make_store(self.root, "DESKTOP-34NQTUN", self.cloud)
        academy.set_nickname("학원")
        academy.load()
        academy.save(PIKA)
        home = make_store(self.root, "HOME-PC", self.cloud)
        home.set_nickname("집")
        home.load()
        self.assertEqual(home.label("DESKTOP-34NQTUN"), "학원")
        self.assertEqual(home.label("HOME-PC"), "집")
        home.save(EEVEE)                       # 집이 저장해도 학원 별명은 남아 있어야 함
        self.assertEqual(academy.peek()["machines"], {"DESKTOP-34NQTUN": "학원", "HOME-PC": "집"})

    def test_label_without_nickname_is_machine_name(self):
        s = make_store(self.root, "academy", self.cloud)
        self.assertEqual(s.label("academy"), "academy")
        self.assertEqual(s.label("UNKNOWN"), "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
