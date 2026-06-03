"""Interactive debugger trace engine for ISLI Skills.

Uses sys.settrace() to collect line-by-line execution snapshots with
variable inspection, breakpoint support, and watch expressions.

All stdlib — no external dependencies.
"""

import ast
import asyncio
import io
import json
import sys
import time
from typing import Any


FORBIDDEN_MODULES = {"os", "sys", "subprocess", "socket", "pickle", "marshal"}

SAFE_BUILTINS: dict[str, Any] = {
    "print": print,
    "range": range,
    "len": len,
    "int": int,
    "float": float,
    "str": str,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    "bool": bool,
    "min": min,
    "max": max,
    "sum": sum,
    "any": any,
    "all": all,
    "sorted": sorted,
    "abs": abs,
    "round": round,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    "Exception": Exception,
    "ValueError": ValueError,
    "TypeError": TypeError,
    "AttributeError": AttributeError,
    "KeyError": KeyError,
    "RuntimeError": RuntimeError,
    "StopIteration": StopIteration,
    "ZeroDivisionError": ZeroDivisionError,
    "IndexError": IndexError,
    "NameError": NameError,
    "AssertionError": AssertionError,
    "NotImplementedError": NotImplementedError,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "hasattr": hasattr,
    "getattr": getattr,
    "setattr": setattr,
    "iter": iter,
    "next": next,
    "reversed": reversed,
    "slice": slice,
    "chr": chr,
    "ord": ord,
    "bin": bin,
    "hex": hex,
    "oct": oct,
    "pow": pow,
    "divmod": divmod,
    "complex": complex,
    "format": format,
    "open": open,  # needed for file reading in debug scripts
}


def validate_debug_code(code: str) -> None:
    """AST security scan: forbid dangerous imports and patterns."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f"Syntax error in debug code: {e}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FORBIDDEN_MODULES:
                    raise ValueError(f"Import of module '{alias.name}' is forbidden")
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in FORBIDDEN_MODULES:
                raise ValueError(f"Import from module '{node.module}' is forbidden")


def safe_repr(obj: Any, max_len: int = 256) -> str:
    """Serialize an object to a string, capping length for JSON safety."""
    try:
        s = repr(obj)
        if len(s) > max_len:
            s = s[:max_len] + "..."
        return s
    except Exception:
        return f"<unreprable {type(obj).__name__}>"


def _filter_dunder(d: dict[str, Any]) -> dict[str, Any]:
    """Strip dunder variables from a namespace dict."""
    return {k: v for k, v in d.items() if not (k.startswith("__") and k.endswith("__"))}


class TraceLimitExceeded(Exception):
    """Raised when the debugger hits max_steps or max_time. Aborts exec()."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class DebugTraceCollector:
    """sys.settrace hook that records execution events."""

    def __init__(
        self,
        code_lines: dict[int, str],
        breakpoints: list[int],
        mode: str,
        max_steps: int,
        max_trace_size: int,
        only_changes: bool,
        include_locals: bool,
        include_globals: bool,
        watch_expressions: list[str],
    ) -> None:
        self.code_lines = code_lines
        self.breakpoints = set(breakpoints)
        self.mode = mode
        self.max_steps = max_steps
        self.max_trace_size = max_trace_size
        self.only_changes = only_changes
        self.include_locals = include_locals
        self.include_globals = include_globals
        self.watch_expressions = watch_expressions

        self.trace: list[dict[str, Any]] = []
        self.step_count = 0
        self.trace_size = 0
        self.truncated = False
        self.truncation_reason: str | None = None
        self.breakpoints_hit: list[int] = []
        self._prev_locals_repr: dict[str, str] = {}
        self.start_time = 0.0

    def _make_event(
        self, frame: Any, event: str, exc_info: tuple[Any, Any, Any] | None = None
    ) -> dict[str, Any]:
        line = frame.f_lineno
        source_line = self.code_lines.get(line, "")

        event_data: dict[str, Any] = {
            "line": line,
            "event": event,
            "source_line": source_line,
        }

        if self.include_locals:
            raw = _filter_dunder(frame.f_locals)
            reprs = {k: safe_repr(v) for k, v in raw.items()}
            if self.only_changes and self._prev_locals_repr:
                changed = {
                    k: v for k, v in reprs.items()
                    if self._prev_locals_repr.get(k) != v
                }
                # Always include new variables even if only_changes is on
                new_keys = set(reprs.keys()) - set(self._prev_locals_repr.keys())
                for k in new_keys:
                    changed[k] = reprs[k]
                if changed:
                    event_data["locals"] = changed
            else:
                event_data["locals"] = reprs
            self._prev_locals_repr = reprs

        if self.include_globals:
            raw = _filter_dunder(frame.f_globals)
            event_data["globals"] = {k: safe_repr(v) for k, v in raw.items()}

        if self.watch_expressions:
            watches: dict[str, str] = {}
            for expr in self.watch_expressions:
                try:
                    val = eval(expr, {"__builtins__": SAFE_BUILTINS}, frame.f_locals)
                    watches[expr] = safe_repr(val)
                except Exception as e:
                    watches[expr] = f"<Error: {e}>"
            if watches:
                event_data["watch_results"] = watches

        if line in self.breakpoints:
            event_data["breakpoint_hit"] = True
            if line not in self.breakpoints_hit:
                self.breakpoints_hit.append(line)

        if exc_info is not None:
            exc_type, exc_value, _ = exc_info
            event_data["exception"] = {
                "type": exc_type.__name__ if exc_type else None,
                "message": str(exc_value) if exc_value else None,
            }

        return event_data

    def _add_event(self, frame: Any, event: str, exc_info: tuple[Any, Any, Any] | None = None) -> None:
        if self.truncated:
            return

        event_data = self._make_event(frame, event, exc_info)
        size = len(json.dumps(event_data, default=str))
        if self.trace_size + size > self.max_trace_size:
            self.truncated = True
            self.truncation_reason = "max_trace_size exceeded"
            return

        self.trace.append(event_data)
        self.trace_size += size

    def trace_fn(self, frame: Any, event: str, arg: Any) -> Any:
        # Only trace our exec'd code (filename '<string>').
        if frame.f_code.co_filename != "<string>":
            return None

        # Time guard — raise to abort exec() immediately
        if time.time() - self.start_time > 30:
            self.truncated = True
            self.truncation_reason = "max_time (30s) exceeded"
            raise TraceLimitExceeded("max_time (30s) exceeded")

        # Step guard — raise to abort exec() immediately
        if self.step_count >= self.max_steps:
            self.truncated = True
            self.truncation_reason = "max_steps exceeded"
            raise TraceLimitExceeded("max_steps exceeded")

        self.step_count += 1

        if event == "line":
            should_record = (
                self.mode == "trace"
                or (self.mode == "breakpoints" and frame.f_lineno in self.breakpoints)
            )
            if should_record:
                self._add_event(frame, event)
        elif event == "exception":
            # Always record exceptions regardless of mode
            self._add_event(frame, event, arg)

        return self.trace_fn


async def execute_with_trace(
    code: str,
    payload: dict[str, Any] | None = None,
    breakpoints: list[int] | None = None,
    mode: str = "breakpoints",
    max_steps: int = 1000,
    max_trace_size: int = 32768,
    only_changes: bool = True,
    include_locals: bool = True,
    include_globals: bool = False,
    watch_expressions: list[str] | None = None,
    stdin: str = "",
) -> dict[str, Any]:
    """Execute Python code with line-by-line trace instrumentation.

    Returns a dict with trace events, final result, exception info, stdout, etc.
    """
    validate_debug_code(code)

    # Parse source lines for pretty output
    code_lines: dict[int, str] = {}
    for i, line in enumerate(code.split("\n"), start=1):
        code_lines[i] = line

    collector = DebugTraceCollector(
        code_lines=code_lines,
        breakpoints=breakpoints or [],
        mode=mode,
        max_steps=max_steps,
        max_trace_size=max_trace_size,
        only_changes=only_changes,
        include_locals=include_locals,
        include_globals=include_globals,
        watch_expressions=watch_expressions or [],
    )

    # Prepare execution namespace
    namespace: dict[str, Any] = {
        "__builtins__": SAFE_BUILTINS,
        "payload": payload or {},
    }

    # Stdin redirect
    old_stdin = sys.stdin
    stdin_buffer = None
    if stdin:
        stdin_buffer = io.StringIO(stdin)
        sys.stdin = stdin_buffer

    # Stdout redirect
    old_stdout = sys.stdout
    stdout_buffer = io.StringIO()
    sys.stdout = stdout_buffer

    use_trace = mode in ("trace", "breakpoints")
    if use_trace:
        collector.start_time = time.time()
        sys.settrace(collector.trace_fn)

    exception_info: dict[str, Any] | None = None
    final_result: Any = None

    try:
        compiled = compile(code, "<string>", "exec")
        exec(compiled, namespace)

        # Capture result: prefer 'run' function, fall back to 'result' variable
        if "run" in namespace:
            run_func = namespace["run"]
            if asyncio.iscoroutinefunction(run_func):
                final_result = await run_func(payload or {})
            else:
                final_result = run_func(payload or {})
        elif "result" in namespace:
            final_result = namespace["result"]

    except TraceLimitExceeded:
        # Expected when max_steps or max_time is hit; already recorded in collector
        pass
    except Exception as exc:
        exception_info = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
    finally:
        if use_trace:
            sys.settrace(None)
        sys.stdout = old_stdout
        if stdin_buffer:
            sys.stdin = old_stdin

    if use_trace:
        execution_time_ms = int((time.time() - collector.start_time) * 1000)
    else:
        execution_time_ms = 0
    stdout = stdout_buffer.getvalue()

    return {
        "success": exception_info is None and not collector.truncated,
        "trace": collector.trace,
        "final_result": safe_repr(final_result) if final_result is not None else None,
        "exception": exception_info,
        "total_steps": collector.step_count,
        "breakpoints_hit": collector.breakpoints_hit,
        "trace_truncated": collector.truncated,
        "truncation_reason": collector.truncation_reason,
        "stdout": stdout,
        "execution_time_ms": execution_time_ms,
    }
