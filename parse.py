import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from pydantic import BaseModel

from google import genai
from google.genai import errors, types

from sympy import Eq, S, simplify, solveset, Symbol
from sympy.logic.boolalg import BooleanFalse, BooleanTrue
from sympy.parsing.latex import parse_latex

load_dotenv(Path(__file__).resolve().parent / ".env")

class ProblemContext(BaseModel):
    task: str
    goal: str
    variables: list[str]
    problem_latex: str
    video_query: str

log = logging.getLogger(__name__)

# Models to try, in order. Gemini's free-tier quotas are counted per model, so when one runs
# out for the day the next is used. IDs Google doesn't recognize are simply skipped.
# Override in .env, e.g. GEMINI_MODELS=gemini-3.8-flash,gemini-2.5-flash
DEFAULT_MODELS = "gemini-3.8-flash,gemini-3.5-flash,gemini-3.5-flash-lite,gemini-2.5-flash"
SKIP_EXHAUSTED_FOR = 60 * 60       # retry a model whose quota ran out after an hour
SKIP_UNKNOWN_FOR = 24 * 60 * 60    # a model ID Google rejected is skipped for a day
_skip_until: dict[str, float] = {}

# Identical work (same lines and question) is answered from memory instead of asking Gemini
# again, so repeated test uploads don't use up the daily quota. Cleared on server restart.
CACHE_LIMIT = 256
_context_cache: dict[tuple[str, str], ProblemContext] = {}


def gemini_models() -> list[str]:
    return [m.strip() for m in os.getenv("GEMINI_MODELS", DEFAULT_MODELS).split(",") if m.strip()]


def get_context(lines_text: str, question: str = "") -> ProblemContext | None:
    """Ask Gemini what problem the student is solving."""
    prompt = (
        "These are lines of a student's handwritten math work, transcribed to LaTeX, "
        "one per line. Identify what problem they are solving. Do not solve it.\n"
        "For problem_latex, give the original problem as one LaTeX equation or expression, "
        "for example 'x^2 = 3x' or '\\lim_{x \\to \\infty} x^2'.\n"
        "For video_query, give a short YouTube search phrase (3 to 8 words) for a tutorial "
        "on the method this problem needs, for example 'solving quadratic equations by "
        "factoring'. Describe the method, not this exact problem or its answer.\n\n"
    )
    if question:
        prompt += f"The original question was: {question}\n\n"
    prompt += lines_text

<<<<<<< HEAD
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
                config={"response_mime_type": "application/json", "response_schema": ProblemContext},
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
            log.warning("Gemini context failed: %r", exc)  # bad key, server error, ...
            return None
        except Exception as exc:  # network error, timeout, ...
            log.warning("Gemini context failed: %r", exc)
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
=======
    try:
        # Stay within the browser's 90-second upload timeout.
        client = genai.Client(
            api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"),
            http_options=types.HttpOptions(
                timeout=60_000, retry_options=types.HttpRetryOptions(attempts=1)),
        )
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash"),
            contents=prompt,
            config={"response_mime_type": "application/json", "response_schema": ProblemContext,
                    "thinking_config": types.ThinkingConfig(thinking_level="low")},
        )
        return response.parsed
    except Exception as exc:
        code = getattr(exc, "code", None)
        messages = {
            400: "Gemini rejected the request. Check the API key and model configuration.",
            401: "Gemini authentication failed. Check GEMINI_API_KEY in .env.",
            403: "Gemini access denied. Check your API key permissions.",
            404: "The configured Gemini model is unavailable.",
            429: "Gemini quota or rate limit reached. Check usage and billing, then retry.",
            504: "Gemini timed out. Open this question again to retry.",
        }
        message = messages.get(code, "Could not get context from Gemini. Check the key and connection, then retry.")
        logging.getLogger(__name__).warning("Gemini context failed (%s, status %s)", type(exc).__name__, code)
        raise RuntimeError(message) from exc
>>>>>>> 35c014720f1369d63e67fb9498a370e06b395490

def check_line(latex: str):
    """Returns (sympy_object, None) if valid, or (None, error_message) if not."""
    try:
        expr = parse_latex(latex)
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
        problem = parse_latex(context.problem_latex)
        return meaning(problem, var) == meaning(final, var)
    except Exception:
        return None

def parse_image_lines(lines: list, question: str = "") -> dict:
    context_error = None
    try:
        context = get_context(combine_lines(lines), question)
        if context is None:
            context_error = "Gemini returned no context. Open this question again to retry."
    except RuntimeError as exc:
        context = None
        context_error = str(exc)
    var = Symbol(context.variables[0]) if context and context.variables else Symbol("x")

    results, parsed = [], []
    for i, line in enumerate(lines, start=1):
        text = line.get("data", "")
        expr, error = check_line(text)
        parsed.append(expr)
        results.append({"line": i, "latex": text, "valid": error is None,
                        "error": error, "follows_from_previous": None})

    for i in range(1, len(parsed)):
        if parsed[i - 1] is not None and parsed[i] is not None:
            results[i]["follows_from_previous"] = same_meaning(parsed[i - 1], parsed[i], var)

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
