"""Content helpers shared by the About page and the Core Values page."""

CULTURE_ICONS = {
    'Christ-Centered': 'cross',
    'Word-Based': 'book',
    'Prayer-Driven': 'flame',
    'Integrity-Led': 'star',
    'Excellence-Focused': 'star',
    'Compassion-Motivated': 'heart',
    'Multiplication-Minded': 'people',
}


def split_culture(culture):
    if not culture:
        return '', []
    intro = ''
    items = []
    for paragraph in culture.split('\n\n'):
        lines = [line.strip() for line in paragraph.split('\n') if line.strip()]
        if not lines:
            continue
        if not items and len(lines) == 1:
            intro = lines[0]
            continue
        title = lines[0]
        items.append({
            'title': title,
            'text': ' '.join(lines[1:]) if len(lines) > 1 else '',
            'icon': CULTURE_ICONS.get(title, 'star'),
        })
    return intro, items
