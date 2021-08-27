import re
from youtube_dl.compat import compat_HTMLParser
from youtube_dl.utils import urlencode_postdata

def int_or_none(x):
    try:
        return int(x)
    except:
        return None

class HTMLAttributeParser(compat_HTMLParser):
    """Trivial HTML parser to gather the attributes for a single element"""
    def __init__(self):
        self.attrs = {}
        compat_HTMLParser.__init__(self)

    def handle_starttag(self, tag, attrs):
        self.attrs = dict(attrs)


def extract_attributes(html_element):
    """Given a string for an HTML element such as
    <el
         a="foo" B="bar" c="&98;az" d=boz
         empty= noval entity="&amp;"
         sq='"' dq="'"
    >
    Decode and return a dictionary of attributes.
    {
        'a': 'foo', 'b': 'bar', c: 'baz', d: 'boz',
        'empty': '', 'noval': None, 'entity': '&',
        'sq': '"', 'dq': '\''
    }.
    NB HTMLParser is stricter in Python 2.6 & 3.2 than in later versions,
    but the cases in the unit test will work for all of 2.6, 2.7, 3.2-3.5.
    """
    parser = HTMLAttributeParser()
    try:
        parser.feed(html_element)
        parser.close()
    # Older Python may throw HTMLParseError in case of malformed HTML
    except compat_HTMLParseError:
        pass
    return parser.attrs

def _hidden_inputs(html):
    html = re.sub(r'<!--(?:(?!<!--).)*-->', '', html)
    hidden_inputs = {}
    for input in re.findall(r'(?i)(<input[^>]+>)', html):
        attrs = extract_attributes(input)
        if not input:
            continue
        if attrs.get('type') not in ('hidden', 'submit'):
            continue
        name = attrs.get('name') or attrs.get('id')
        value = attrs.get('value')
        if name and value is not None:
            hidden_inputs[name] = value
    return hidden_inputs

def get_xpath(html, xpath):
    element = html.xpath(xpath)
    if len(element) != 1:
        return None
    return element[0]

def filter_children_recursive(html, include):
    def _fcr(html, l):
        if include(html):
            l.append(html)
        for i in html:
            _fcr(i, l)
    l = []
    _fcr(html, l)
    return l
