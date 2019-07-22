"""Submodule for the `SubConfig` `Loader`, which can be used to
create/configure hierarchical object structures in various ways."""

from .loader import Loader
from .utils import ParseError

class SubConfig(Loader):
    """Loader for embedded `Configurable`s. The sub-configurable's
    configuration can be taken from:

     - a single key containing a dictionary (`style` = `True`),
     - the current dictionary level with a prefix (`style` = `'<prefix>'`),
     - or the current dictionary (`style` = `False`).

    The class is constructed with a reference to its parent as its first
    and only positional argument. Any keys that have been parsed before can be
    read from this for contextual information."""

    def __init__(self, key, doc, config, style, optional=False):
        super().__init__(key, doc)
        self._configurable = config
        self._style = style
        self._optional = optional

    def markdown(self):
        """Yields markdown documentation for all the keys that this loader can
        make sense of as `(key, markdown)` tuples."""
        if self._style is True:
            yield self.friendly_key, self.doc + '\n\nRefer to TODO for more info.'
            return

        prefix = '%s-' % self._style.replace('_', '-') if self._style else ''

        markdown = [self.doc]

        segue = 'The following configuration keys are used to configure this object.'
        if self._optional:
            segue += (' This object is optional, so it is legal to not specify '
                      'any of them, except when this object is required by context.')
        markdown.append(segue)

        for loader in self._configurable.loaders:
            for key, doc in loader.markdown():
                markdown.append('### `%s%s`' % (prefix, key))
                doc = '\n\n'.join((
                    '#' + paragraph if paragraph.startswith('###') else paragraph
                    for paragraph in doc.split('\n\n')))
                markdown.append(doc)

        markdown = '\n\n'.join(markdown)

        if prefix:
            yield '%s*' % prefix, markdown
        else:
            yield '%s%s keys' % (self.friendly_key[0].upper(), self.friendly_key[1:]), markdown

    def markdown_more(self):
        """Yields or returns a list of `@configurable` classes that must be
        documented in addition because the docs generated by `markdown()` refer
        to them."""
        yield self._configurable

    def deserialize(self, dictionary, parent, path=()):
        """`SubConfig` deserializer. See `Loader.deserialize()` for more
        info."""
        if self._style is True:
            if self._optional and self.key not in dictionary:
                return None
            subdict = dictionary.pop(self.key, {})
            if not isinstance(subdict, dict):
                raise ParseError('%s must be a dictionary' % self.friendly_path(path))
            path = path + (self.friendly_key,)

        else:
            prefix = '%s-' % self._style.replace('_', '-') if self._style else ''

            # Figure out which keys the subconfig supports by... well, reading the
            # documentation.
            keys = set()
            for loader in self._configurable.loaders:
                for key, _ in loader.markdown():
                    keys.add(key.replace('-', '_'))

            subdict = {}
            for key in keys:
                in_key = prefix + key
                if in_key in dictionary:
                    subdict[key] = dictionary.pop(in_key)
            if not subdict and self._optional:
                return None

        return self._configurable.from_dict(subdict, parent)

    def serialize(self, dictionary, value):
        """`SubConfig` serializer. See `Loader.serialize()` for more info."""
        if value is None:
            return
        if self._style is True:
            dictionary[self.friendly_key] = value.to_dict()
        else:
            prefix = '%s-' % self._style.replace('_', '-') if self._style else ''
            subdict = value.to_dict()
            for key, val in subdict.items():
                dictionary[prefix + key] = val


def subconfig(method, optional=False):
    """Method decorator for configuring a `configurable`-annotated class from
    the dictionary inside a configuration key for another
    `configurable`-annotated class. The annotated method is called with zero
    arguments (not even `self`) to get the class that is to be constructed.
    The name of the key is set to the name of the method, and the markdown
    documentation for the key is set to the method's docstring."""
    return SubConfig(method.__name__, method.__doc__, method(), True, optional)


def opt_subconfig(method):
    """Same as `subconfig()`, but the class is optional. If the key is not
    present, the value will be set to `None`."""
    return subconfig(method, True)


def embedded(method, optional=False):
    """Method decorator for constructing embedded `SubConfig` loaders inside a
    `configurable`-annotated class. The annotated method is called with zero
    arguments (not even `self`) to get an optional prefix and the class that is
    to be constructed as a single value (the class) or a two-tuple of the
    prefix string and the class. The method is transformed to a property that
    allows the constructed class to be accessed."""
    data = method()
    if isinstance(data, tuple):
        style = data[0]
        config = data[1]
    else:
        style = False
        config = data
    return SubConfig(method.__name__, method.__doc__, config, style, optional)


def opt_embedded(method):
    """Same as `embedded()`, but the class is optional. If none of the keys
    used by the subclass are present, the value will be set to `None`."""
    return embedded(method, True)
