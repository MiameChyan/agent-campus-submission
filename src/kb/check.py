"""知识库校验命令：python -m src.kb.check [--kb data/kb]

新增或修改文档后先跑一遍，校验通过才会被 Agent 使用（Agent 启动时也会做同样的校验）。
"""
import argparse
import json
import sys

from ..config import DEFAULT_KB
from .store import KBValidationError, KnowledgeBase


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kb", default=str(DEFAULT_KB), help="知识库根目录")
    args = parser.parse_args(argv)
    try:
        kb = KnowledgeBase.load(args.kb)
    except KBValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, **kb.summary()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
