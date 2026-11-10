"""层次型知识库：从 Markdown 目录树加载 → 校验 → 提供 L0/L1/L2 三层访问。

目录结构（文件系统范式）：
    <root>/_dir.md                 目录的 L0 摘要（front matter: abstract）与 L1 概览（正文）
    <root>/<分类>/.../_dir.md
    <root>/<分类>/.../Dxx-标题.md   文档：front matter 元数据 + 按 "## " 切分的小节

启动时直接从 Markdown 构建，没有持久化索引文件；修改 .md 后下次运行即生效。
"""
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .retrievers import Retriever, create_retriever

DIR_META = "_dir.md"
VALID_STATUS = {"现行", "已废止"}
REQUIRED_DOC_FIELDS = (
    "doc_id", "title", "version_date", "status", "scope",
    "supersedes", "superseded_by", "links", "abstract",
)
_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.S)
_DOC_ID = re.compile(r"^D\d{2,}$")


class KBValidationError(ValueError):
    """知识库校验失败；problems 列出全部问题，便于一次修完。"""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("知识库校验失败：\n" + "\n".join(f"  - {p}" for p in problems))


@dataclass
class Section:
    doc_id: str
    section_id: str          # s1, s2 ...
    title: str               # "第三条 报销期限"
    text: str                # 小节原文（可被引用）

    @property
    def ref(self) -> str:
        return f"{self.doc_id}#{self.section_id}"


@dataclass
class Document:
    doc_id: str
    title: str
    version_date: str
    status: str
    scope: str
    supersedes: list[str]
    superseded_by: str | None
    links: list[str]
    abstract: str
    category: str            # 所在目录，如 "制度/财务"
    file: str                # 相对知识库根目录的路径
    sections: list[Section] = field(default_factory=list)

    def meta(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "version_date": self.version_date,
            "status": self.status,
            "scope": self.scope,
            "supersedes": self.supersedes,
            "superseded_by": self.superseded_by,
            "links": self.links,
            "category": self.category,
        }


@dataclass
class Directory:
    path: str                # "" 表示根目录
    title: str
    abstract: str            # L0
    overview: str            # L1
    subdirs: list[str] = field(default_factory=list)
    doc_ids: list[str] = field(default_factory=list)


def _split_front_matter(raw: str, file: str, problems: list[str]) -> tuple[dict, str]:
    m = _FRONT_MATTER.match(raw.replace("\r\n", "\n"))
    if not m:
        problems.append(f"{file}: 缺少 front matter（--- ... ---）")
        return {}, raw
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as exc:
        problems.append(f"{file}: front matter 不是合法 YAML：{exc}")
        return {}, m.group(2)
    if not isinstance(meta, dict):
        problems.append(f"{file}: front matter 必须是键值对")
        return {}, m.group(2)
    return meta, m.group(2)


def _split_sections(doc_id: str, body: str) -> list[Section]:
    sections: list[Section] = []
    title, lines = None, []
    for line in body.splitlines():
        if line.startswith("## "):
            if title is not None:
                sections.append(Section(doc_id, f"s{len(sections) + 1}", title, "\n".join(lines).strip()))
            title, lines = line[3:].strip(), []
        elif title is not None:
            lines.append(line)
    if title is not None:
        sections.append(Section(doc_id, f"s{len(sections) + 1}", title, "\n".join(lines).strip()))
    return sections


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


class KnowledgeBase:
    def __init__(self, root: Path, docs: dict[str, Document], dirs: dict[str, Directory],
                 retriever: Retriever | None = None):
        self.root = root
        self.docs = docs
        self.dirs = dirs
        self.sections: dict[str, Section] = {s.ref: s for d in docs.values() for s in d.sections}
        # 检索器可插拔（BM25 / 向量 / 混合），见 retrievers/registry.py
        self.retriever = retriever or create_retriever()
        # 上下文前缀：把“目录 / 文档 / 小节标题”拼到正文前再索引（上下文感知检索的轻量版）
        self.retriever.index([
            (sec.ref, f"{doc.category} {doc.doc_id} {doc.title} {sec.title}\n{sec.text}")
            for doc in docs.values() for sec in doc.sections
        ])

    # ---------- 加载与校验 ----------
    @classmethod
    def load(cls, root: str | Path, retriever: Retriever | None = None) -> "KnowledgeBase":
        root = Path(root).resolve()
        problems: list[str] = []
        if not root.is_dir():
            raise KBValidationError([f"知识库目录不存在：{root}"])

        dirs: dict[str, Directory] = {}
        docs: dict[str, Document] = {}

        for dir_path in sorted([root, *[p for p in root.rglob("*") if p.is_dir()]]):
            rel = dir_path.relative_to(root).as_posix()
            rel = "" if rel == "." else rel
            meta_file = dir_path / DIR_META
            title, abstract, overview = (rel.split("/")[-1] if rel else "根目录"), "", ""
            if meta_file.exists():
                meta, body = _split_front_matter(meta_file.read_text(encoding="utf-8"), f"{rel or '.'}/{DIR_META}", problems)
                title = str(meta.get("title") or title)
                abstract = str(meta.get("abstract") or "")
                overview = body.strip()
            else:
                problems.append(f"{rel or '.'}: 缺少目录说明文件 {DIR_META}")
            dirs[rel] = Directory(rel, title, abstract, overview)

        for rel, d in dirs.items():
            if rel:
                parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
                dirs[parent].subdirs.append(rel)

        for file in sorted(root.rglob("*.md")):
            if file.name == DIR_META:
                continue
            rel_file = file.relative_to(root).as_posix()
            meta, body = _split_front_matter(file.read_text(encoding="utf-8"), rel_file, problems)
            if not meta:
                continue
            missing = [k for k in REQUIRED_DOC_FIELDS if k not in meta]
            if missing:
                problems.append(f"{rel_file}: 缺少字段 {missing}")
                continue
            doc_id = str(meta["doc_id"])
            if not _DOC_ID.match(doc_id):
                problems.append(f"{rel_file}: doc_id 格式应为 D01 这样的形式，实际为 {doc_id!r}")
            if doc_id in docs:
                problems.append(f"{rel_file}: doc_id {doc_id} 与 {docs[doc_id].file} 重复")
                continue
            version = meta["version_date"]
            if isinstance(version, (_dt.date, _dt.datetime)):
                version = version.strftime("%Y-%m-%d")
            try:
                _dt.date.fromisoformat(str(version))
            except ValueError:
                problems.append(f"{rel_file}: version_date 必须是 YYYY-MM-DD，实际为 {version!r}")
            status = str(meta["status"])
            if status not in VALID_STATUS:
                problems.append(f"{rel_file}: status 必须是 {sorted(VALID_STATUS)} 之一，实际为 {status!r}")
            sections = _split_sections(doc_id, body)
            if not sections:
                problems.append(f"{rel_file}: 正文至少需要一个 '## ' 小节")
            category = file.parent.relative_to(root).as_posix()
            category = "" if category == "." else category
            doc = Document(
                doc_id=doc_id,
                title=str(meta["title"]),
                version_date=str(version),
                status=status,
                scope=str(meta["scope"]),
                supersedes=_as_list(meta["supersedes"]),
                superseded_by=(str(meta["superseded_by"]) if meta["superseded_by"] else None),
                links=_as_list(meta["links"]),
                abstract=str(meta["abstract"]),
                category=category,
                file=rel_file,
                sections=sections,
            )
            docs[doc_id] = doc
            dirs[category].doc_ids.append(doc_id)

        # 交叉引用校验：替代关系与链接不能指向不存在的文档，且替代关系必须双向一致
        for doc in docs.values():
            for ref in doc.links + doc.supersedes + ([doc.superseded_by] if doc.superseded_by else []):
                if ref not in docs:
                    problems.append(f"{doc.file}: 引用了不存在的文档 {ref}")
            for old in doc.supersedes:
                if old in docs and docs[old].superseded_by != doc.doc_id:
                    problems.append(f"{doc.file}: 声明替代 {old}，但 {old} 的 superseded_by 不是 {doc.doc_id}")
            if doc.superseded_by and doc.status != "已废止":
                problems.append(f"{doc.file}: 已被 {doc.superseded_by} 替代，status 应为“已废止”")
        if not docs:
            problems.append("知识库中没有任何文档")
        if problems:
            raise KBValidationError(problems)
        return cls(root, docs, dirs, retriever)

    # ---------- L0：浏览目录 ----------
    def browse(self, path: str = "") -> dict:
        path = path.strip().strip("/")
        if path not in self.dirs:
            raise KeyError(f"目录不存在：{path!r}。可用目录：{sorted(p or '/' for p in self.dirs)}")
        d = self.dirs[path]
        return {
            "path": path or "/",
            "title": d.title,
            "overview": d.overview,
            "subdirs": [{"path": s, "title": self.dirs[s].title, "abstract": self.dirs[s].abstract} for s in d.subdirs],
            "documents": [
                {
                    "doc_id": i,
                    "title": self.docs[i].title,
                    "version_date": self.docs[i].version_date,
                    "status": self.docs[i].status,
                    "abstract": self.docs[i].abstract,
                }
                for i in d.doc_ids
            ],
        }

    # ---------- L1：文档大纲 ----------
    def outline(self, doc_id: str) -> dict:
        doc = self.get_doc(doc_id)
        return {
            **doc.meta(),
            "abstract": doc.abstract,
            "sections": [{"section_id": s.section_id, "title": s.title} for s in doc.sections],
        }

    # ---------- L2：小节原文 ----------
    def read_section(self, doc_id: str, section_id: str) -> dict:
        doc = self.get_doc(doc_id)
        sec = next((s for s in doc.sections if s.section_id == section_id), None)
        if sec is None:
            raise KeyError(f"{doc_id} 中不存在小节 {section_id!r}，可用小节：{[s.section_id for s in doc.sections]}")
        return {**doc.meta(), "section_id": sec.section_id, "section_title": sec.title, "text": sec.text}

    # ---------- 快捷定位：关键词检索 ----------
    def search(self, query: str, top_k: int = 5) -> list[dict]:
        hits = []
        for ref, score in self.retriever.search(query, top_k=top_k):
            sec = self.sections[ref]
            doc = self.docs[sec.doc_id]
            preview = sec.text if len(sec.text) <= 40 else sec.text[:40] + "…"
            hits.append({
                "doc_id": doc.doc_id,
                "section_id": sec.section_id,
                "path": f"{doc.category}/{doc.doc_id}",
                "title": doc.title,
                "section_title": sec.title,
                "version_date": doc.version_date,
                "status": doc.status,
                "score": round(score, 3),
                "preview": preview,
            })
        return hits

    def get_doc(self, doc_id: str) -> Document:
        doc_id = doc_id.strip().upper()
        if doc_id not in self.docs:
            raise KeyError(f"文档不存在：{doc_id!r}。可用文档：{sorted(self.docs)}")
        return self.docs[doc_id]

    def summary(self) -> dict:
        return {
            "root": str(self.root),
            "directories": len(self.dirs),
            "documents": len(self.docs),
            "sections": len(self.sections),
            "doc_ids": sorted(self.docs),
            "retriever": self.retriever.name,
        }
