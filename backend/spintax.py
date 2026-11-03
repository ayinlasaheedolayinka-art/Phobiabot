import re
import random
from datetime import datetime

def parse_spintax(text: str) -> str:
    """
    Recursively parse spintax format: {option1|option2|{sub1|sub2}}
    """
    if not text:
        return ""
    
    pattern = re.compile(r'\{([^{}]+)\}')
    
    # Process inner-most brackets first until none remain
    while True:
        match = pattern.search(text)
        if not match:
            break
        options = match.group(1).split('|')
        selected = random.choice(options)
        text = text[:match.start()] + selected + text[match.end():]
        
    return text

def render_template(text: str, extra_vars: dict = None) -> str:
    """
    Renders spintax and dynamic variables such as {time}, {date}, {random_num}.
    """
    if not text:
        return ""
    
    now = datetime.now()
    variables = {
        "time": now.strftime("%H:%M"),
        "date": now.strftime("%Y-%m-%d"),
        "day": now.strftime("%A"),
        "random_id": str(random.randint(1000, 9999)),
    }
    
    if extra_vars:
        variables.update(extra_vars)
        
    rendered = text
    for key, val in variables.items():
        rendered = rendered.replace(f"{{{key}}}", str(val))
        
    return parse_spintax(rendered)
