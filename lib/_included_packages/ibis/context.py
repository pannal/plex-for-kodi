# coding=utf-8

import datetime
from . import errors


# User-configurable functions and variables available in all contexts.
builtins = {
    'now': datetime.datetime.now,
    'range': range,
}


class ContextDict(dict):
    def __getattr__(self, attr):
        return self.get(attr)

    def __setattr__(self, attr, value):
        self[attr] = value


# A wrapper around a stack of dictionaries.
class DataStack:
    strict_mode = False

    def __init__(self, strict_mode):
        self.stack = []
        self.strict_mode = strict_mode

    def __getitem__(self, key):
        for d in reversed(self.stack):
            if key in d:
                try:
                    return d[key]
                except KeyError:
                    if self.strict_mode:
                        raise
                    return
        raise KeyError(key)

    def __getattr__(self, key):
        if key not in self.__dict__:
            try:
                return self[key]
            except KeyError:
                if self.strict_mode:
                    raise
                return
        return self.__dict__[key]


# A Context object is a wrapper around the user's input data. Its `.resolve()` method contains
# the lookup-logic for resolving dotted variable names.
class Context(object):

    def __init__(self, data_dict, strict_mode):
        # Stack of data dictionaries for the .resolve() method.
        self.data = DataStack(strict_mode)

        # Standard builtins.
        self.data.stack.append(ContextDict({
            'context': self,
            'is_defined': self.is_defined,
        }))

        # User-configurable builtins.
        self.data.stack.append(ContextDict(builtins))

        # Instance-specific data.
        self.data.stack.append(ContextDict(data_dict))

        # Nodes can store state information here to avoid threading issues.
        self.stash = {}

        # Chain of ancestor templates.
        self.templates = []

        # In strict mode undefined variables raise an UndefinedVariable exception.
        self.strict_mode = strict_mode

    def __setitem__(self, key, value):
        self.data.stack[-1][key] = value

    def __getitem__(self, key):
        return self.data[key]

    def __getattr__(self, key):
        if key not in self.__dict__:
            try:
                return self.get(key)
            except KeyError:
                if self.strict_mode:
                    raise
                return
        return self.__dict__[key]

    def push(self, data=None):
        self.data.stack.append(ContextDict(data or {}))

    def pop(self):
        self.data.stack.pop()

    def get(self, key, default=None):
        for d in reversed(self.data.stack):
            if key in d:
                return d[key]
        return default

    def set_global(self, key, value):
        self.data.stack[2][key] = value

    def update(self, data_dict):
        self.data.stack[-1].update(data_dict)

    def resolve(self, varstring, token):
        words = []
        result = self.data
        for word in varstring.split('.'):
            words.append(word)
            if hasattr(result, word):
                result = getattr(result, word)
            else:
                try:
                    result = result[word]
                except:
                    try:
                        result = result[int(word)]
                    except:
                        if self.strict_mode:
                            msg = "Cannot resolve the variable '{}' in template ".format('.'.join(words))
                            msg += "'{template_id}', line {line_number}.".format(template_id=token.template_id,
                                                                                 line_number=token.line_number)
                            errors.raise_(errors.UndefinedVariable(msg, token), None)
                        return Undefined()
        return result

    def is_defined(self, varstring):
        current = self.data
        for word in varstring.split('.'):
            if hasattr(current, word):
                current = getattr(current, word)
            else:
                try:
                    current = current[word]
                except:
                    try:
                        current = current[int(word)]
                    except:
                        return False
        return True


# Null type returned when a context lookup fails.
class Undefined:

    def __str__(self):
        return ''

    def __bool__(self):
        return False

    __nonzero__ = __bool__

    def __len__(self):
        return 0

    def __contains__(self, key):
        return False

    def __iter__(self):
        return self

    def __next__(self):
        raise StopIteration

    next = __next__

    def __eq__(self, other):
        return False

    def __ne__(self, other):
        return True

