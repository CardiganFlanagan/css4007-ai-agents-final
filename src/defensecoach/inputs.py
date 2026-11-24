MAX_INPUT_CHARS = 4000


class InputError(ValueError):
    pass


def check_input(text):
    text = (text or "").strip()
    if not text:
        raise InputError("Empty message. Type a question or an answer.")
    if len(text) > MAX_INPUT_CHARS:
        raise InputError(f"Message is too long ({len(text)} chars, max {MAX_INPUT_CHARS}).")
    return text
