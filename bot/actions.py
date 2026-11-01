"""Turn an intent into a guaranteed-legal action."""

FOLD, CHECK, CALL, RAISE, SHOVE = "fold", "check", "call", "raise", "shove"


def legalize(intent, gs, amount=0):
    """Return {'action': ..., 'amount': ...}. `amount` is a raise-to total for this street."""
    to_call = gs.to_call
    if intent == RAISE or intent == SHOVE:
        if gs.can_raise and gs.max_raise_to > gs.current_bet and gs.stack > to_call:
            target = gs.max_raise_to if intent == SHOVE else int(amount)
            if target < gs.min_raise_to:
                target = gs.min_raise_to     # below min-raise: bump up to the minimum
            if target > gs.max_raise_to:
                target = gs.max_raise_to     # above stack: all-in
            return {"action": "raise", "amount": target}
        intent = CALL                        # raise not available: call instead
    if intent == CALL:
        if to_call <= 0:
            return {"action": "check", "amount": 0}
        return {"action": "call", "amount": min(to_call, gs.stack)}
    if to_call <= 0:
        return {"action": "check", "amount": 0}  # never fold when checking is free
    return {"action": "fold", "amount": 0}


def fallback(raw):
    """Last resort when everything else failed: check if legal, otherwise fold."""
    try:
        if raw.get("to_call", 1) <= 0:
            return {"action": "check", "amount": 0}
    except Exception:
        pass
    return {"action": "fold", "amount": 0}
