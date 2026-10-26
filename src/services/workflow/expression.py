"""Conditions and computed values in workflows: a small, safe expression language.

Used by "if" / "while" steps (condition "expression") and by "assign" steps
whose value starts with "=". It reads like Python:

    price > 100 and status == "ok"
    not contains(title, "Sold out")
    count + 1
    lower(trim(name)) + "@example.com"

Names are workflow variables; "{{name}}" is accepted too. Variables hold text,
so comparisons and arithmetic treat two values that both read as numbers as
numbers ("10" > "9"), and anything else as text. Nothing is executed: the
expression is parsed with `ast` and only the nodes below are evaluated.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable
from typing import Any

MAX_LENGTH = 2_000
MAX_TEXT = 100_000

_BRACES = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_CONSTANTS = {"true": True, "false": False, "True": True, "False": False}


class ExpressionError(ValueError):
    pass


def _number(value: Any) -> int | float | None:
    """The value as a number, or None when it does not read as one."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if re.fullmatch(r"[-+]?\d+", text):
        return int(text)
    if re.fullmatch(r"[-+]?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?", text):
        return float(text)
    return None


def to_text(value: Any) -> str:
    """How a result is stored in a variable."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    return str(value)


def truthy(value: Any) -> bool:
    """bool as is, numbers unless 0, text unless empty, "0" or "false"."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() not in ("", "0", "false")


def _need_number(value: Any, op: str) -> int | float:
    n = _number(value)
    if n is None:
        raise ExpressionError(f"'{to_text(value)[:40]}' is not a number (for {op})")
    return n


def _int(value: Any) -> int:
    return int(_need_number(value, "int"))


def _matches(text: Any, pattern: Any) -> bool:
    try:
        return re.search(to_text(pattern), to_text(text)) is not None
    except re.error as e:
        raise ExpressionError(f"invalid regular expression: {e}") from e


FUNCTIONS: dict[str, tuple[int, Callable[..., Any]]] = {
    # name: (number of arguments, function)
    "len": (1, lambda s: len(to_text(s))),
    "int": (1, _int),
    "num": (1, lambda s: _need_number(s, "num")),
    "str": (1, to_text),
    "lower": (1, lambda s: to_text(s).lower()),
    "upper": (1, lambda s: to_text(s).upper()),
    "trim": (1, lambda s: to_text(s).strip()),
    "contains": (2, lambda s, part: to_text(part) in to_text(s)),
    "startswith": (2, lambda s, part: to_text(s).startswith(to_text(part))),
    "endswith": (2, lambda s, part: to_text(s).endswith(to_text(part))),
    "matches": (2, _matches),
    "replace": (3, lambda s, old, new: to_text(s).replace(to_text(old), to_text(new))),
}


def _source(text: str) -> str:
    return _BRACES.sub(r"\1", (text or "").strip())


def parse(text: str) -> ast.Expression:
    """The checked syntax tree; ExpressionError for anything outside the language."""
    source = _source(text)
    if not source:
        raise ExpressionError("the expression is empty")
    if len(source) > MAX_LENGTH:
        raise ExpressionError(f"the expression is longer than {MAX_LENGTH} characters")
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as e:
        raise ExpressionError(f"invalid expression: {e.msg}") from e
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            raise ExpressionError(f"'{type(node).__name__}' is not allowed in an expression")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (str, int, float, bool)):
            raise ExpressionError("only text, numbers, true and false can be written as values")
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else ""
            if name not in FUNCTIONS:
                raise ExpressionError(
                    f"unknown function '{name or ast.unparse(node.func)}'; "
                    f"use {', '.join(sorted(FUNCTIONS))}"
                )
            if node.keywords or len(node.args) != FUNCTIONS[name][0]:
                raise ExpressionError(f"{name}() takes {FUNCTIONS[name][0]} argument(s)")
    return tree


def names(text: str) -> list[str]:
    """Variables an expression reads (function names and true/false are not variables)."""
    tree = parse(text)
    called = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    found = sorted(
        (n.col_offset, n.id)
        for n in ast.walk(tree)
        if isinstance(n, ast.Name) and id(n) not in called and n.id not in _CONSTANTS
    )
    return list(dict.fromkeys(name for _, name in found))


def evaluate(text: str, variables: dict[str, str]) -> Any:
    """The value of the expression; ExpressionError when it cannot be worked out."""
    return _eval(parse(text).body, variables)


def _compare(op: ast.cmpop, left: Any, right: Any) -> bool:
    if isinstance(op, (ast.In, ast.NotIn)):
        found = to_text(left) in to_text(right)
        return found if isinstance(op, ast.In) else not found
    a, b = _number(left), _number(right)
    if a is None or b is None:
        a, b = to_text(left), to_text(right)
    if isinstance(op, ast.Eq):
        return a == b
    if isinstance(op, ast.NotEq):
        return a != b
    if isinstance(op, ast.Lt):
        return a < b
    if isinstance(op, ast.LtE):
        return a <= b
    if isinstance(op, ast.Gt):
        return a > b
    return a >= b


def _arith(op: ast.operator, left: Any, right: Any) -> Any:
    if isinstance(op, ast.Add):
        a, b = _number(left), _number(right)
        if a is None or b is None:
            joined = to_text(left) + to_text(right)
            if len(joined) > MAX_TEXT:
                raise ExpressionError("the text is too long")
            return joined
        return a + b
    symbol = {ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.FloorDiv: "//", ast.Mod: "%"}[type(op)]
    a, b = _need_number(left, symbol), _need_number(right, symbol)
    if isinstance(op, ast.Sub):
        return a - b
    if isinstance(op, ast.Mult):
        if abs(a) > 1e100 or abs(b) > 1e100:
            raise ExpressionError("the number is too large")
        return a * b
    if b == 0:
        raise ExpressionError("division by zero")
    if isinstance(op, ast.Div):
        return a / b
    if isinstance(op, ast.FloorDiv):
        return a // b
    return a % b


def _eval(node: ast.AST, variables: dict[str, str]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        if node.id not in variables:
            raise ExpressionError(f"{{{{{node.id}}}}} has no value")
        return variables[node.id]
    if isinstance(node, ast.BoolOp):
        result: Any = None
        for value in node.values:
            result = _eval(value, variables)
            # and stops at the first false value, or at the first true one.
            if truthy(result) != isinstance(node.op, ast.And):
                return result
        return result
    if isinstance(node, ast.UnaryOp):
        value = _eval(node.operand, variables)
        if isinstance(node.op, ast.Not):
            return not truthy(value)
        n = _need_number(value, "-")
        return -n if isinstance(node.op, ast.USub) else n
    if isinstance(node, ast.BinOp):
        return _arith(node.op, _eval(node.left, variables), _eval(node.right, variables))
    if isinstance(node, ast.Compare):
        left = _eval(node.left, variables)
        for op, comparator in zip(node.ops, node.comparators, strict=True):
            right = _eval(comparator, variables)
            if not _compare(op, left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Call):
        _, fn = FUNCTIONS[node.func.id]  # type: ignore[attr-defined]
        return fn(*(_eval(a, variables) for a in node.args))
    raise ExpressionError(f"'{type(node).__name__}' is not allowed in an expression")


_ALLOWED = (
    ast.Expression,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.USub,
    ast.UAdd,
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Call,
)
