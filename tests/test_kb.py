"""知识库加载、校验与三层访问。"""
import pytest

from src.config import KB_VARIANTS
from src.kb.check import main as check_main
from src.kb.store import KBValidationError, KnowledgeBase


def test_load_default_kb(kb):
    assert sorted(kb.docs) == ["D01", "D02", "D03", "D04", "D05", "D06", "D07", "D08"]
    assert kb.docs["D03"].status == "已废止" and kb.docs["D03"].superseded_by == "D07"
    assert kb.docs["D07"].supersedes == ["D03"]


def test_variant_kb_has_no_d02():
    kb = KnowledgeBase.load(KB_VARIANTS / "no_conflict")
    assert "D02" not in kb.docs and "D01" in kb.docs


def test_browse_outline_read(kb):
    root = kb.browse("")
    assert {s["path"] for s in root["subdirs"]} == {"制度", "产品"}
    fin = kb.browse("制度/财务")
    assert [d["doc_id"] for d in fin["documents"]] == ["D01", "D02"]
    out = kb.outline("D07")
    assert out["supersedes"] == ["D03"] and len(out["sections"]) == 4
    sec = kb.read_section("D01", "s3")
    assert "30 天内提交报销申请" in sec["text"] and sec["status"] == "现行"


def test_unknown_ids_raise(kb):
    with pytest.raises(KeyError):
        kb.read_section("D99", "s1")
    with pytest.raises(KeyError):
        kb.read_section("D01", "s9")
    with pytest.raises(KeyError):
        kb.browse("不存在")


def test_search_ranks_relevant_sections(kb):
    assert kb.search("报销期限", 3)[0]["doc_id"] == "D01"
    assert kb.search("远程办公 天数", 1)[0]["doc_id"] == "D05"
    assert kb.search("股票期权行权") == []


def test_path_prefix_makes_category_searchable(kb):
    # 小节正文没有“人事”二字，但索引时拼了目录前缀
    hits = kb.search("人事 年假", 5)
    assert {h["doc_id"] for h in hits} >= {"D03", "D07"}


def test_validation_reports_all_problems(kb_copy):
    d01 = kb_copy / "制度/财务/D01-费用报销制度.md"
    d01.write_text(d01.read_text(encoding="utf-8").replace("links: [D02]", "links: [D99]")
                   .replace("version_date: 2024-03-01", "version_date: 2024/03/01"), encoding="utf-8")
    dup = kb_copy / "制度/财务/D09-重复.md"
    dup.write_text((kb_copy / "制度/行政/D06-办公设备申领规定.md").read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(KBValidationError) as exc:
        KnowledgeBase.load(kb_copy)
    text = "\n".join(exc.value.problems)
    assert "D99" in text and "version_date" in text and "重复" in text


def test_supersede_relation_must_be_consistent(kb_copy):
    d03 = kb_copy / "制度/人事/D03-年假制度-2023.md"
    d03.write_text(d03.read_text(encoding="utf-8").replace("superseded_by: D07", "superseded_by: null"), encoding="utf-8")
    with pytest.raises(KBValidationError) as exc:
        KnowledgeBase.load(kb_copy)
    assert any("D03" in p and "superseded_by" in p for p in exc.value.problems)


def test_edit_takes_effect_on_next_load(kb_copy):
    d01 = kb_copy / "制度/财务/D01-费用报销制度.md"
    d01.write_text(d01.read_text(encoding="utf-8").replace("30 天内", "45 天内"), encoding="utf-8")
    assert "45 天内" in KnowledgeBase.load(kb_copy).read_section("D01", "s3")["text"]


def test_check_command(capsys, kb_copy):
    assert check_main(["--kb", str(kb_copy)]) == 0
    (kb_copy / "制度/财务/_dir.md").unlink()
    assert check_main(["--kb", str(kb_copy)]) == 2
