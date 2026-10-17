import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from pydantic import BaseModel

from google import genai
from google.genai import types

from sympy import Eq, S, simplify, solveset, Symbol
from sympy.logic.boolalg import BooleanFalse, BooleanTrue
from sympy.parsing.latex import parse_latex

load_dotenv(Path(__file__).resolve().parent / ".env")

class ProblemContext(BaseModel):
    task: str
    goal: str
    variables: list[str]
    problem_latex: str

def get_context(lines_text: str, question: str = "") -> ProblemContext | None:
    """Ask Gemini what problem the student is solving."""
    prompt = (
        "These are lines of a student's handwritten math work, transcribed to LaTeX, "
        "one per line. Identify what problem they are solving. Do not solve it.\n"
        "For problem_latex, give the original problem as one LaTeX equation or expression, "
        "for example 'x^2 = 3x' or '\\lim_{x \\to \\infty} x^2'.\n\n"
    )
    if question:
        prompt += f"The original question was: {question}\n\n"
    prompt += lines_text

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
