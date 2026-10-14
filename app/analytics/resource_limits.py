"""Conservative lexical JSON budget before object expansion; not a JSON parser."""


def json_cost(raw, *, maximum=200000, depth_limit=64):
    # Count structural punctuation and string starts outside strings. Scalars
    # are bounded by separators plus the input byte ceiling. Escape handling
    # prevents quoted braces/commas from consuming structural depth.
    depth = cost = 0
    quoted = escaped = False
    for char in raw:
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
            cost += 1
        elif char in '[{':
            depth += 1
            cost += 1
            if depth > depth_limit:
                raise ValueError('JSON depth budget exceeded')
        elif char in ']}':
            depth -= 1
            if depth < 0:
                raise ValueError('Invalid JSON structure')
        elif char in ',:':
            cost += 1
        if cost > maximum:
            raise ValueError('JSON expansion budget exceeded')
    if quoted or depth:
        raise ValueError('Incomplete JSON structure')
    return cost
