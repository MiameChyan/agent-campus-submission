"""工具插件：一个 .py 文件就是一个（或几个）工具，放进插件目录即可被 Agent 使用，支持热加载。

写法（参考 src/tools/plugins/search.py）：

    from typing import Annotated
    from src.tools.plugin import ToolContext, tool

    @tool(description="给模型看的工具说明")
    def my_tool(ctx: ToolContext, query: Annotated[str, "参数说明"], top_k: Annotated[int, "条数"]) -> dict:
        return {"answer": ...}

- 第一个参数固定为 ToolContext（可访问知识库 ctx.kb），其余参数由类型注解自动生成 strict JSON Schema：
  str / int / float / bool / list[...] / Literal[...]，用 Annotated[类型, "说明"] 写参数说明。
- 返回值必须可 JSON 序列化。抛出 ToolExecutionError 可以给模型明确的错误类型与建议；其他异常会被包装为
  PluginError（不可重试）交给模型，不会打断主循环。
- 文件名以 "_" 开头的不会被加载（可用于草稿或共享代码）。

热加载：PluginRegistry.refresh() 比较目录中文件的名称、修改时间和大小，有变化就重新加载整个目录。
CLI 每次运行都会加载；HTTP 服务在每个请求开始时调用 refresh()，修改插件后无需重启。
某个插件加载失败只会让它自己不可用，并在 load_errors 中给出原因（GET /api/tools 可查看）。
"""
from __future__ import annotations

import hashlib
import importlib.util
import inspect
import sys
import threading
import traceback
import typing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .base import Tool

PLUGIN_DIR = Path(__file__).resolve().parent / "plugins"
_TYPE_MAP = {str: "string", int: "integer", float: "number", bool: "boolean"}


@dataclass
class ToolContext:
    kb: Any          # KnowledgeBase（避免循环导入，这里不标具体类型）


@dataclass
class ToolSpec:
    name: str
    description: str
    func: Callable[..., Any]
    properties: dict[str, Any]


def _json_schema(annotation: Any, where: str) -> dict:
    desc = None
    if typing.get_origin(annotation) is typing.Annotated:
        annotation, *meta = typing.get_args(annotation)
        desc = next((m for m in meta if isinstance(m, str)), None)
    origin = typing.get_origin(annotation)
    if annotation in _TYPE_MAP:
        schema: dict = {"type": _TYPE_MAP[annotation]}
    elif origin is typing.Literal:
        values = list(typing.get_args(annotation))
        schema = {"type": _TYPE_MAP[type(values[0])], "enum": values}
    elif origin is list:
        (item,) = typing.get_args(annotation) or (str,)
        schema = {"type": "array", "items": _json_schema(item, where)}
    else:
        raise TypeError(f"{where}：不支持的参数类型 {annotation!r}（支持 str/int/float/bool/list/Literal）")
    if desc:
        schema["description"] = desc
    return schema


def tool(name: str | None = None, description: str = ""):
    """把函数标记为工具。参数 schema 由类型注解生成。"""

    def wrap(func: Callable[..., Any]) -> Callable[..., Any]:
        tool_name = name or func.__name__
        hints = typing.get_type_hints(func, include_extras=True)
        params = list(inspect.signature(func).parameters.values())
        if not params or params[0].name != "ctx":
            raise TypeError(f"工具 {tool_name} 的第一个参数必须是 ctx: ToolContext")
        props = {}
        for p in params[1:]:
            if p.name == "reason":
                raise TypeError(f"工具 {tool_name}：参数名 reason 为系统保留（用于记录决策依据）")
            if p.name not in hints:
                raise TypeError(f"工具 {tool_name} 的参数 {p.name} 缺少类型注解")
            props[p.name] = _json_schema(hints[p.name], f"工具 {tool_name} 参数 {p.name}")
        func.__tool_spec__ = ToolSpec(tool_name, (description or func.__doc__ or "").strip(), func, props)
        return func

    return wrap


class PluginRegistry:
    def __init__(self, directory: Path | str = PLUGIN_DIR):
        self.directory = Path(directory)
        self.specs: dict[str, ToolSpec] = {}
        self.load_errors: dict[str, str] = {}
        self.version = 0
        self._fingerprint: tuple | None = None
        self._lock = threading.Lock()

    def _files(self) -> list[Path]:
        if not self.directory.is_dir():
            return []
        return sorted(p for p in self.directory.glob("*.py") if not p.name.startswith("_"))

    def _current_fingerprint(self) -> tuple:
        out = []
        for p in self._files():
            st = p.stat()
            out.append((p.name, st.st_mtime_ns, st.st_size))
        return tuple(out)

    def refresh(self) -> bool:
        """目录有变化时重新加载；返回是否发生了重新加载。"""
        with self._lock:
            fp = self._current_fingerprint()
            if fp == self._fingerprint:
                return False
            specs: dict[str, ToolSpec] = {}
            errors: dict[str, str] = {}
            for path in self._files():
                try:
                    for spec in self._load_file(path):
                        if spec.name in specs:
                            raise ValueError(f"工具名 {spec.name} 与其他插件重复")
                        specs[spec.name] = spec
                except Exception as exc:  # 插件自身的错误只影响它自己
                    errors[path.name] = f"{exc.__class__.__name__}: {exc}"
                    errors[path.name + ":traceback"] = traceback.format_exc(limit=3)
            self.specs, self.load_errors = specs, errors
            self._fingerprint = fp
            self.version += 1
            return True

    def _load_file(self, path: Path) -> list[ToolSpec]:
        digest = hashlib.md5(f"{path}:{path.stat().st_mtime_ns}".encode()).hexdigest()[:8]
        mod_name = f"kbqa_plugin_{path.stem}_{digest}"
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"无法加载 {path.name}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(mod_name, None)
        found = [obj.__tool_spec__ for obj in vars(module).values() if hasattr(obj, "__tool_spec__")]
        if not found:
            raise ValueError("文件中没有用 @tool 标记的函数")
        return found

    def build(self, ctx: ToolContext) -> dict[str, Tool]:
        """把插件绑定到本次运行的上下文，生成可直接执行的业务工具。"""
        tools = {}
        for spec in self.specs.values():
            def handler(_f=spec.func, **kwargs):
                return _f(ctx, **kwargs)
            tools[spec.name] = Tool(name=spec.name, description=spec.description, properties=spec.properties,
                                    kind="business", handler=handler)
        return tools

    def describe(self) -> dict:
        return {
            "directory": str(self.directory),
            "version": self.version,
            "tools": [{"name": s.name, "description": s.description, "parameters": list(s.properties)}
                      for s in self.specs.values()],
            "load_errors": {k: v for k, v in self.load_errors.items() if not k.endswith(":traceback")},
        }


_default: PluginRegistry | None = None


def default_registry() -> PluginRegistry:
    global _default
    if _default is None:
        _default = PluginRegistry()
    _default.refresh()
    return _default
