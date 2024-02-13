from django.template import Library, Node, TemplateSyntaxError
from django.utils import translation

register = Library()


# {{{ get language_code in JS traditional naming format

class GetCurrentLanguageJsFmtNode(Node):
    def __init__(self, variable):
        self.variable = variable

    def render(self, context):
        lang_name = (
            translation.to_locale(translation.get_language()).replace("_", "-"))
        context[self.variable] = lang_name
        return ''


@register.tag("get_current_js_lang_name")
def do_get_current_js_lang_name(parser, token):
    """
    This will store the current language in the context, in js lang format.
    This is different with built-in do_get_current_language, which returns
    languange name like "en-us", "zh-hans". This method return lang name
    "en-US", "zh-Hans",  with the country code capitallized if country code
    has 2 characters, and capitalize first if country code has more than 2
    characters.

    Usage::

        {% get_current_language_js_lang_format as language %}

    This will fetch the currently active language name with js tradition and
    put it's value into the ``language`` context variable.
    """
    # token.split_contents() isn't useful here because this tag doesn't
    # accept variable as arguments
    args = token.contents.split()
    if len(args) != 3 or args[1] != 'as':
        raise TemplateSyntaxError("'get_current_js_lang_name' requires "
                "'as variable' (got %r)" % args)
    return GetCurrentLanguageJsFmtNode(args[2])


@register.filter(name='js_lang_fallback')
def js_lang_fallback(lang_name, js_name=None):
    """
    Return the fallback lang name for js files.
    :param a :class:`str:`
    :param js_name: a :class:`str:`, optional.
    :return: a :class:`str:`
    """

    # The mapping is crap, we use a special case table to fix it.
    if js_name == "fullcalendar":
        known_fallback_mapping = {
            "zh-hans": "zh-cn",
            "zh-hant": "zh-tw"}
        return known_fallback_mapping.get(lang_name.lower(), lang_name).lower()

    return lang_name

# }}}
