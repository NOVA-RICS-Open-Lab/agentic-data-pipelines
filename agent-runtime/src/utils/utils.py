import secrets
import string

ALPHANUM = string.ascii_lowercase + string.digits

def make_trace_id(tag: str) -> str:
    """
    Return a string of the form 'trace_<tag><random>',
    where the total length after 'trace_' is 32 chars.
    """
    tag += "0"
    pad_len = 32 - len(tag)
    random_suffix = ''.join(secrets.choice(ALPHANUM) for _ in range(pad_len))
    return f"trace_{tag}{random_suffix}"


def inject_verbatim_functions(task: str, verbatim_functions: str) -> str:
    """
    Append a verbatim_functions blob to a task prompt inside fixed markers, in code
    rather than relying on the receiving LLM to relay it faithfully on its own.
    No-op if verbatim_functions is empty.
    """
    if not verbatim_functions:
        return task
    return (
        f"{task}\n\n"
        "=== VERBATIM_FUNCTIONS (reproduce exactly, character-for-character - do not "
        "paraphrase, summarize, or drop any part) ===\n"
        f"{verbatim_functions}\n"
        "=== END VERBATIM_FUNCTIONS ==="
    )


def inject_functions_to_implement(task: str, functions_to_implement: str) -> str:
    """
    Append the FunctionsToImplement specs to a task prompt inside fixed markers, so
    the receiving agent gets the exact tool list rather than whatever prose an
    upstream LLM chose to fold into the context. The Researcher and Generator
    prompts both look for this === FUNCTIONS_TO_IMPLEMENT === block.
    No-op if functions_to_implement is empty.
    """
    if not functions_to_implement:
        return task
    return (
        f"{task}\n\n"
        "=== FUNCTIONS_TO_IMPLEMENT (one 'Name: Purpose' per line - build EXACTLY these "
        "tools; do not rename, merge, add or drop any) ===\n"
        f"{functions_to_implement}\n"
        "=== END FUNCTIONS_TO_IMPLEMENT ==="
    )
