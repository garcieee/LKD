"""A reports.json that is not a list must not stop reports being filed."""
from app.db.store import ReportStore


def test_a_file_that_is_not_a_list_is_set_aside_and_reports_go_on(tmp_path):
    path = tmp_path / "reports.json"
    path.write_text("{\n  \n}")
    store = ReportStore(path)
    assert store.all() == []
    store.add({"id": "a"})
    assert [r["id"] for r in store.all()] == ["a"]
    assert (tmp_path / "reports.json.bad").read_text() == "{\n  \n}"


def test_a_file_cut_off_mid_write_is_set_aside_too(tmp_path):
    path = tmp_path / "reports.json"
    path.write_text('[{"id": "a"')
    store = ReportStore(path)
    store.add({"id": "b"})
    assert [r["id"] for r in store.all()] == ["b"]
    assert (tmp_path / "reports.json.bad").exists()
