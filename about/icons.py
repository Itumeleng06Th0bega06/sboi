KEYWORDS = [
    ('prayer', 'flame'), ('worship', 'music'), ('praise', 'music'), ('song', 'music'),
    ('faith', 'cross'), ('trust', 'cross'), ('saviour', 'cross'), ('jesus', 'cross'),
    ('love', 'heart'), ('compassion', 'heart'), ('mercy', 'heart'),
    ('word', 'book'), ('bible', 'book'), ('scripture', 'book'), ('truth', 'book'),
    ('giving', 'gift'), ('generosity', 'gift'), ('sacrifice', 'gift'), ('offer', 'gift'),
    ('outreach', 'globe'), ('missions', 'globe'), ('evangelism', 'globe'), ('service', 'globe'), ('world', 'globe'),
    ('community', 'people'), ('family', 'people'), ('unity', 'people'), ('fellowship', 'people'), ('relationship', 'people'),
    ('excellence', 'star'), ('integrity', 'star'), ('holiness', 'star'), ('character', 'star'),
    ('fire', 'flame'), ('shekinah', 'flame'), ('presence', 'flame'), ('spirit', 'flame'), ('power', 'flame'), ('prayer', 'flame'),
]


def icon_for(text):
    if not text:
        return 'star'
    lower = str(text).lower()
    for keyword, icon in KEYWORDS:
        if keyword in lower:
            return icon
    return 'star'
