# Embedded file name: mud\worlddocs\utils.pyo
import re
SPECIAL_CHAR = re.compile("[.;:,\\'/\\\\]")

def GetTWikiName(name):
    if not name:
        return ''
    name = SPECIAL_CHAR.sub('', name)
    name = ''.join((n[0].upper() + n[1:] for n in name.split(' ') if n))
    return name