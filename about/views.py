from django.shortcuts import render

from .icons import icon_for
from .models import (
    ChurchProfile,
    CoreValue,
    Leader,
    MissionAction,
    MissionComponent,
    PathwayStep,
    VisionPillar,
)

STORY_HEADINGS = [
    'A Vision Born from God’s Calling',
    'The Birth of the Vision',
    'The Meaning Behind the Name',
    'Humble Beginnings',
    'Witnessing the Faithfulness of God',
    'Impacting the Community',
    'The Role of Prophetess ME Mosokini',
    'Looking Toward the Future',
]

CULTURE_ICONS = {
    'Christ-Centered': 'cross',
    'Word-Based': 'book',
    'Prayer-Driven': 'flame',
    'Integrity-Led': 'star',
    'Excellence-Focused': 'star',
    'Compassion-Motivated': 'heart',
    'Multiplication-Minded': 'people',
}

PRACTICE_ICONS = {
    'Families are restored': 'people',
    'Believers mature spiritually': 'flame',
    'Leaders emerge from within the Church': 'crown',
    'Young people discover purpose': 'star',
    'Communities are impacted positively': 'globe',
    'Kingdom values influence society': 'check',
    'The Gospel is shared effectively': 'book',
    'New ministries are birthed': 'gift',
    'Future church branches are established': 'crown',
    'Disciples become disciple-makers': 'people',
    'People live lives that honor Christ': 'cross',
}


def normalize(text):
    return str(text).replace('’', "'").strip().lower()


def split_story(story):
    if not story:
        return []
    headings = {normalize(h): h for h in STORY_HEADINGS}
    sections = []
    for paragraph in story.split('\n\n'):
        key = normalize(paragraph)
        if key in headings:
            sections.append({'title': headings[key], 'body': []})
        elif sections:
            sections[-1]['body'].append(paragraph)
    result = []
    for section in sections:
        section['body'] = '\n\n'.join(section['body']).strip()
        result.append(section)
    if not result and story.strip():
        result.append({'title': '', 'body': story.strip()})
    return result


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


def split_practice(practice):
    if not practice:
        return '', [], ''
    intro = ''
    closing = ''
    items = []
    for paragraph in practice.split('\n\n'):
        lines = [line.strip() for line in paragraph.split('\n') if line.strip()]
        if not lines:
            continue
        if lines[0].startswith('•'):
            for line in lines:
                text = line.lstrip('• ').strip()
                if text:
                    items.append({'text': text, 'icon': PRACTICE_ICONS.get(text, 'star')})
        elif not intro:
            intro = paragraph.strip()
        else:
            closing = paragraph.strip()
    return intro, items, closing


def about(request):
    values = list(CoreValue.objects.all())
    actions = list(MissionAction.objects.all())
    for value in values:
        value.icon = icon_for(value.title)
    for action in actions:
        action.icon = icon_for(action.title)
    profile = ChurchProfile.objects.first()
    story_sections = split_story(profile.story if profile else None)
    culture_intro, culture_items = split_culture(profile.culture_statement if profile else None)
    practice_intro, practice_items, practice_closing = split_practice(profile.vision_practice if profile else None)
    if story_sections and profile and profile.story_image:
        before = next((i for i, s in enumerate(story_sections) if s['title'] == 'Witnessing the Faithfulness of God'), None)
        if before is not None:
            story_sections.insert(before, {'image': True})
    context = {
        'profile': profile,
        'pillars': VisionPillar.objects.all(),
        'components': MissionComponent.objects.all(),
        'pathway': PathwayStep.objects.all(),
        'actions': actions,
        'values': values,
        'leaders': Leader.objects.all(),
        'story_sections': story_sections,
        'culture_intro': culture_intro,
        'culture_items': culture_items,
        'practice_intro': practice_intro,
        'practice_items': practice_items,
        'practice_closing': practice_closing,
    }
    return render(request, 'about.html', context)
