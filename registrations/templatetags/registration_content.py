import re
from django import template

register = template.Library()


@register.filter
def event_paragraphs(value):
    """Split organizer copy into plain-text paragraphs, leaving escaping to Django."""
    sections = []
    for part in re.split(r"\n\s*\n", str(value).replace("\r\n", "\n").strip()):
        lines = part.strip().split("\n", 1)
        if len(lines) == 2 and len(lines[0]) <= 100:
            sections.append({"title": lines[0], "body": lines[1]})
        elif part.strip():
            sections.append({"title": "", "body": part.strip()})
    return sections
