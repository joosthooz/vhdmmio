"""Submodule for the `SubConfig` `Loader`, which can be used to
create/configure hierarchical object structures in various ways."""

from .loader import Loader
from .utils import ParseError, Unset

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

    @property
    def prefix(self):
        """Returns the prefix for the (embedded) keys belonging to this
        subconfig. Invalid when the keys are in their own dictionary."""
        assert self._style is not True
        return '%s-' % self._style if self._style else ''

    def markdown(self):
        """Yields markdown documentation for all the keys that this loader can
        make sense of as `(key, markdown)` tuples."""
        cfg_fname = '%s.md' % self._configurable.__name__.lower()

        markdown = [self.doc]

        if self._style is True:
            markdown.append(
                'This key must be set to a dictionary. Its structure is defined '
                '[here](%s). Not specifying the key is equivalent to specifying '
                'an empty dictionary.' % cfg_fname)
            yield self.key, '\n\n'.join(markdown)
            return

        markdown.append(
            'More information about this structure may be found [here](%s).' % cfg_fname)

        segue = 'The following configuration keys are used to configure this structure.'
        if self._optional:
            segue += (' This structure is optional, so it is legal to not specify '
                      'any of them, except when this structure is required by context.')
        markdown.append(segue)

        for loader in self._configurable.loaders:
            for key, _ in loader.markdown():
                markdown.append('### `%s%s`' % (self.prefix, key))
                #doc = '\n\n'.join((
                    #'#' + paragraph if paragraph.startswith('###') else paragraph
                    #for paragraph in doc.split('\n\n')))
                #markdown.append(doc)
                markdown.append('This key is documented [here](%s#%s).' % (cfg_fname, key))

        markdown = '\n\n'.join(markdown)

        if self.prefix:
            yield '%s*' % self.prefix, markdown
        else:
            yield '%s%s keys' % (self.key[0].upper(), self.key[1:]), markdown

    def markdown_more(self):
        """Yields or returns a list of `@configurable` classes that must be
        documented in addition because the docs generated by `markdown()` refer
        to them."""
        yield self._configurable

    def deserialize(self, dictionary, parent):
        """`SubConfig` deserializer. See `Loader.deserialize()` for more
        info."""

        # Handle subkey style.
        if self._style is True:
            value = dictionary.pop(self.key, Unset)

            # If we didn't find the key and the subconfig is optional, don't
            # initialize anything and just set the value to `None`.
            if value is Unset and self._optional:
                return None

            # Make sure that the key is a dictionary before passing it to the
            # subconfig constructor.
            if not isinstance(value, dict):
                ParseError.invalid(self.key, value, 'a dictionary')

            # Wrap any exceptions generated by the subconfig with the
            # appropriate key.
            with ParseError.wrap(self.key):
                return self._configurable(parent, value)

        # Figure out which keys the subconfig supports by... well, reading the
        # documentation.
        keys = set()
        for loader in self._configurable.loaders:
            for key, _ in loader.markdown():
                keys.add(key)

        # Take the supported keys out of the incoming dictionary and put them
        # in a new dict, while stripping the prefix away.
        subdict = {}
        for key in keys:
            prefixed_key = self.prefix + key
            value = dictionary.pop(prefixed_key, Unset)
            if value is not Unset:
                subdict[key] = value

        # If we didn't find any keys and the subconfig is optional, don't
        # initialize anything and just set the value to `None`.
        if not subdict and self._optional:
            return None

        # Wrap any exceptions generated by the subconfig even though we don't
        # have a key. They're still configuration errors after all.
        with ParseError.wrap():
            return self._configurable(parent, subdict)

    def serialize(self, dictionary, value):
        """`SubConfig` serializer. See `Loader.serialize()` for more info."""

        # If we have None instead of a configurable instance, the value must
        # have been unspecified and we should be optional.
        if value is None:
            assert self._optional
            return

        # Serialize the subconfig.
        subdict = value.serialize()

        # Handle subkey style.
        if self._style is True:
            dictionary[self.key] = subdict
            return

        # Handle prefixed/embedded style.
        for key, val in subdict.items():
            dictionary[self.prefix + key] = val

    def mutable(self):
        """Returns whether the value managed by this loader can be mutated. If
        this is overridden to return `True`, the loader must implement
        `validate()`."""
        return True

    def validate(self, value):
        """Checks that the given value is valid for this loader, raising an
        appropriate ParseError if not. This function only needs to work if
        `mutable()` returns `True`."""

        # Note: an exact typecheck is used in order to ensure that
        # serialization followed by deserialization results in the same value.
        if type(value) is not self._configurable: #pylint: disable=C0123
            raise TypeError('value must be an instance of %s' % self._configurable.__name__)
        if value.parent is not self:
            raise ValueError('value must have been initialized with us as the parent')


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
