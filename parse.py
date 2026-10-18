import inspect
import logging
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv

from pydantic import BaseModel, Field, field_validator

from google import genai
from google.genai import errors, types

from sympy import Eq, FiniteSet, S, simplify, solveset, Symbol
from sympy.logic.boolalg import BooleanFalse, BooleanTrue
from sympy.parsing.latex import parse_latex

from latex_metrics import strip_delims

load_dotenv(Path(__file__).resolve().parent / ".env")

# The handwriting model writes LaTeX the way its training data does, e.g. "sin(z)" without
# a backslash, which SymPy would read as s*i*n(z). clean_latex() fixes such spellings.
FUNCTION_NAMES = re.compile(r"(?<![\\a-zA-Z])(arcsin|arccos|arctan|sinh|cosh|tanh|sin|cos|tan"
                            r"|sec|csc|cot|log|ln|exp|lim)(?![a-zA-Z])")
STYLE_COMMANDS = re.compile(r"\\(?:displaystyle|textstyle|limits)(?![a-zA-Z])")
# \left| would be read as a quantum "ket"; plain brackets mean the same thing here.
SIZED_BRACKET = re.compile(r"\\(?:left|right)(?![a-zA-Z])\s*(\\[{}]|[()\[\]|.])")
# Strict parsing rejects lines SymPy can only partly read (it would otherwise read
# "x = 0, x = 3" as just x = 0). Older SymPy versions don't have the option.
STRICT = {"strict": True} if "strict" in inspect.signature(parse_latex).parameters else {}

class ProblemContext(BaseModel):
    task: str = Field(description="Plain-language problem description. No LaTeX commands, math delimiters, or code.")
    goal: str = Field(description="Plain-language question for the student. No LaTeX commands, math delimiters, or code.")
    variables: list[str]
    problem_latex: str
    video_query: str

    @field_validator("task", "goal")
    @classmethod
    def keep_problem_about_math(cls, value: str) -> str:
        if re.search(r"\b(?:latex|tex|ocr|transcription|formatting|markup)\b|\\[a-zA-Z]+|```", value, re.I):
            return "Review the mathematical steps in this problem."
        return value

log = logging.getLogger(__name__)

# Models to try, in order. Gemini's free-tier quotas are counted per model, so when one runs
# out for the day the next is used. IDs Google doesn't recognize are simply skipped.
# Override in .env, e.g. GEMINI_MODELS=gemini-3.8-flash,gemini-2.5-flash
DEFAULT_MODELS = "gemini-3.5-flash,gemini-3.5-flash-lite,gemini-2.5-flash"
SKIP_EXHAUSTED_FOR = 60 * 60       # retry a model whose quota ran out after an hour
SKIP_UNKNOWN_FOR = 24 * 60 * 60    # a model ID Google rejected is skipped for a day
_skip_until: dict[str, float] = {}

# Identical work (same lines and question) is answered from memory instead of asking Gemini
# again, so repeated test uploads don't use up the daily quota. Cleared on server restart.
CACHE_LIMIT = 256
_context_cache: dict[tuple[str, str], ProblemContext] = {}


def gemini_models() -> list[str]:
    return [m.strip() for m in (os.getenv("GEMINI_MODELS") or os.getenv("GEMINI_MODEL") or DEFAULT_MODELS).split(",") if m.strip()]


def request_config(model: str) -> dict:
    config = {"response_mime_type": "application/json", "response_schema": ProblemContext}
    # thinking_level only exists on Gemini 3+; 2.5 models reject it with a 400 (which would
    # make the fallback model look "unknown" and get skipped for a day). They use a budget.
    if model.startswith("gemini-2"):
        if "flash" in model:
            config["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
    else:
        config["thinking_config"] = types.ThinkingConfig(thinking_level="low")
    return config


def get_context(lines_text: str, question: str = "") -> ProblemContext | None:
    """Ask Gemini what problem the student is solving."""
    prompt = (
        "These are lines of a student's handwritten math work, transcribed to LaTeX, "
        "one per line. Identify what problem they are solving. Do not solve it.\n"
        "For task and goal, write a concise problem statement in plain language for the student. "
        "Use words or ordinary Unicode math symbols. Do not include LaTeX commands, "
        "dollar-sign math delimiters, code blocks, or references to LaTeX or transcription. "
        "Keep any LaTeX source exclusively in problem_latex, which is used internally.\n"
        "The student's problem is mathematics, never LaTeX, programming, OCR, or formatting. "
        "Treat the supplied LaTeX only as a representation of their math work. "
        "Never make task or goal ask the student to fix, explain, convert, or write LaTeX, "
        "even if the transcription is malformed. Infer the underlying mathematical task; "
        "if it is unclear, say 'Review the mathematical steps in this problem.' "
        "Do not invent a notation-repair or code-debugging problem.\n"
        "For problem_latex, give the original problem as one LaTeX equation or expression, "
        "for example 'x^2 = 3x' or '\\lim_{x \\to \\infty} x^2'.\n"
        "For video_query, give a short YouTube search phrase (3 to 8 words) for a tutorial "
        "on the method this problem needs, for example 'solving quadratic equations by "
        "factoring'. Describe the method, not this exact problem or its answer.\n\n"
    )
    if question:
        prompt += f"Use this user-provided question as the authoritative problem statement: {question}\n\n"
    prompt += lines_text

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        log.warning("GEMINI_API_KEY is not set, so no problem context or related videos. "
                    "Add it to .env (see .env.example) and restart the server.")
        return None
    cache_key = (lines_text, question)
    if cache_key in _context_cache:
        return _context_cache[cache_key]

    # Give up after 30 s (and don't retry) so a slow or stuck request can't hang the upload.
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(
        timeout=30_000, retry_options=types.HttpRetryOptions(attempts=1)))
    for model in gemini_models():
        if _skip_until.get(model, 0) > time.time():
            continue
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=request_config(model),
            )
        except errors.APIError as exc:
            if exc.code == 429:  # this model's quota is used up; try the next one
                _skip_until[model] = time.time() + SKIP_EXHAUSTED_FOR
                log.warning("Gemini model %s is out of quota; trying the next model.", model)
                continue
            if exc.code in (400, 404):  # unknown model ID, or it can't do this request
                _skip_until[model] = time.time() + SKIP_UNKNOWN_FOR
                log.warning("Gemini model %s is unavailable (%s); trying the next model.", model, exc.code)
                continue
            log.warning("Gemini context failed (%s, status %s)", type(exc).__name__, getattr(exc, "code", None))  # bad key, server error, ...
            return None
        except Exception as exc:  # network error, timeout, ...
            log.warning("Gemini context failed (%s, status %s)", type(exc).__name__, getattr(exc, "code", None))
            return None
        context = response.parsed
        if not isinstance(context, ProblemContext):
            log.warning("Gemini model %s returned no usable answer.", model)
            return None
        if len(_context_cache) >= CACHE_LIMIT:
            _context_cache.pop(next(iter(_context_cache)))  # drop the oldest entry
        _context_cache[cache_key] = context
        return context

    log.warning("Every Gemini model is out of quota or unavailable right now; the daily free "
                "limits reset at midnight Pacific time. The math checks still work without it.")
    return None

def clean_latex(latex: str) -> str:
    """Rewrite the model's LaTeX into the forms SymPy's parser reads correctly."""
    latex = STYLE_COMMANDS.sub(" ", strip_delims(latex))
    latex = SIZED_BRACKET.sub(lambda match: "" if match.group(1) == "." else match.group(1), latex)
    return FUNCTION_NAMES.sub(r"\\\1 ", latex).strip()


def read_latex(latex: str):
    return parse_latex(clean_latex(latex), **STRICT)


def check_line(latex: str):
    """Returns (sympy_object, None) if valid, or (None, error_message) if not."""
    try:
        expr = read_latex(latex)
    except Exception:
        return None, "Couldn't read this line as math."

    if isinstance(expr, BooleanFalse):
        return None, "This statement is false."
    if isinstance(expr, BooleanTrue):
        return expr, None

    if isinstance(expr, Eq) and not expr.free_symbols:
        left, right = expr.lhs.doit(), expr.rhs.doit()
        if left != right and simplify(left - right) != 0:
            return None, "This statement is false."

    return expr, None


def meaning(expr, var: Symbol):
    if isinstance(expr, Eq):
        return solveset(expr.lhs - expr.rhs, var, domain=S.Reals)
    return simplify(expr.doit())


def same_meaning(a, b, var: Symbol):
    try:
        return meaning(a, var) == meaning(b, var)
    except Exception:
        return None


def reaches_goal(final, context: ProblemContext | None, var: Symbol):
    if context is None:
        return None
    try:
        problem = read_latex(context.problem_latex)
        return meaning(problem, var) == meaning(final, var)
    except Exception:
        return None

def parse_image_lines(lines: list, question: str = "") -> dict:
    context_error = None
    context = None
    if any(line.get("data", "").strip() for line in lines):
        try:
            context = get_context(combine_lines(lines), question)
            # Without an API key there's nothing to retry; the math checks run without context.
            if context is None and (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
                context_error = "Gemini returned no context. Open this question again to retry."
        except RuntimeError as exc:
            context_error = str(exc)
    var = Symbol(context.variables[0]) if context and context.variables else Symbol("x")

    results, parsed = [], []
    for i, line in enumerate(lines, start=1):
        text = line.get("data", "")
        expr, error = check_line(text) if text.strip() else (None, None)
        parsed.append(expr)
        results.append({"line": i, "latex": text, "valid": error is None if text.strip() else None,
                        "error": error, "follows_from_previous": None})
        first, last = line.get("first_symbol"), line.get("last_symbol")
        if "bounds" in line:
            results[-1]["bounds"] = line["bounds"]
        elif first and last:
            results[-1]["bounds"] = {"left": first["left"], "right": last["right"],
                                     "top": min(first["top"], last["top"]),
                                     "bottom": max(first["bottom"], last["bottom"])}

    for i in range(1, len(parsed)):
        if parsed[i - 1] is not None and parsed[i] is not None:
            results[i]["follows_from_previous"] = same_meaning(parsed[i - 1], parsed[i], var)
            if results[i]["follows_from_previous"] is False and all(isinstance(expr, Eq) for expr in parsed[i - 1:i + 1]):
                try:
                    before, after = meaning(parsed[i - 1], var), meaning(parsed[i], var)
                    changes = []
                    for values, verb in ((before - after, "loses"), (after - before, "introduces")):
                        if isinstance(values, FiniteSet) and values:
                            solutions = ", ".join(f"{var} = {value}" for value in sorted(values, key=str))
                            changes.append(f"This step {verb} {'the solution' if len(values) == 1 else 'solutions'} {solutions}.")
                    if changes:
                        results[i]["transition_error"] = " ".join(changes)
                except Exception:
                    pass  # The existing equivalence result still explains the invalid step.

    final_correct = None
    if parsed and parsed[-1] is not None:
        final_correct = reaches_goal(parsed[-1], context, var)

    result = {"context": context.model_dump() if context else None, "lines": results, "final_correct": final_correct}
    if context_error:
        result["context_error"] = context_error
    return result

def combine_lines(lines: list) -> str:
    texts = [line.get("data", "") for line in lines]
    return "\n".join(f"Line {i}: {text}" for i, text in enumerate(texts, start=1))

if __name__ == "__main__":
    import json
    result = parse_image_lines([{"data": "x^2 = 3x"}, {"data": "x = 3"}])
    print(json.dumps(result, indent=2))
