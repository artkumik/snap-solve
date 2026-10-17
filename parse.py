import logging

from pydantic import BaseModel

from google import genai
from google.genai import types

from sympy import Eq, S, simplify, solveset, Symbol
from sympy.logic.boolalg import BooleanFalse, BooleanTrue
from sympy.parsing.latex import parse_latex

class ProblemContext(BaseModel):
    task: str
    goal: str
    variables: list[str]
    problem_latex: str

def get_context(lines_text: str, question: str = "") -> ProblemContext | None:
    """Ask Gemini what problem the student is solving. Returns None if that fails."""
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
        # Give up after 30 s (and don't retry) so a slow or stuck request can't hang the upload.
        client = genai.Client(http_options=types.HttpOptions(
            timeout=30_000, retry_options=types.HttpRetryOptions(attempts=1)))
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt,
            config={"response_mime_type": "application/json", "response_schema": ProblemContext},
        )
        return response.parsed
    except Exception as exc:
        # Missing API key, network error, bad model name, ... The line checks still run without it.
        logging.getLogger(__name__).warning("Gemini context failed: %r", exc)
        return None

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
    context = get_context(combine_lines(lines), question)
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

    return {"context": context.model_dump() if context else None, "lines": results, "final_correct": final_correct}

def combine_lines(lines: list) -> str:
    texts = [line.get("data", "") for line in lines]
    return "\n".join(f"Line {i}: {text}" for i, text in enumerate(texts, start=1))

if __name__ == "__main__":
    import json
    result = parse_image_lines([{"data": "x^2 = 3x"}, {"data": "x = 3"}])
    print(json.dumps(result, indent=2))