# coding=utf-8

import ast
import operator
import re
import itertools
import collections
import math

import six

import ibis

from . import utils
from . import filters
from . import errors


# Dictionary of registered keywords for instruction tags.
instruction_keywords = {}


def _get_constant_value(node):
    """
    Extract the value from a constant AST node.
    Works across Python 2.7 to 3.14+ by checking multiple attributes.
    Returns None if the node is not a constant or value cannot be extracted.
    """
    # Modern Python 3.8+: ast.Constant with 'value' attribute
    if hasattr(node, 'value'):
        return node.value
    # Legacy Python 2.7-3.7: ast.Num with 'n' attribute
    if hasattr(node, 'n'):
        return node.n
    # Legacy Python 2.7-3.7: ast.Str with 's' attribute
    if hasattr(node, 's'):
        return node.s
    # Python 3.0-3.7: ast.NameConstant (True, False, None)
    # Actually has 'value' attribute, so handled above
    return None


# Set of registered endwords for instruction tags with block scope.
instruction_endwords = set()


# Decorator function for registering handler classes for instruction tags.
# Registering an endword gives the instruction tag block scope.
def register(keyword, endword=None):

    def register_node_class(node_class):
        instruction_keywords[keyword] = (node_class, endword)
        if endword:
            instruction_endwords.add(endword)
        return node_class

    return register_node_class


# Helper class for evaluating expression strings.
#
# An Expression object is initialized with an expression string parsed from a template. An
# expression string can contain a variable name or a Python literal, optionally followed by a
# sequence of filters.
#
# The Expression object handles the rather convoluted process of parsing the string, evaluating
# the literal or resolving the variable, calling the variable if it resolves to a callable, and
# applying the filters to the resulting object. The consumer simply needs to call the expression's
# .eval() method and supply an appropriate Context object.
#
# Examples of valid expression syntax include:
#
#     foo.bar.baz|default('bam')|escape
#     'foo', 'bar', 'baz'|random
#
# Arguments can be passed to callables using bracket syntax:
#
#     foo.bar.baz('bam')|filter(25, 'text')
#

class ContextVariable(str):
    pass


class ResolveContextVariable(str):
    pass


class KeepExpr(Exception):
    pass


def safe_math_eval(s):
    def checkmath(x, *args):
        if x not in [a for a in dir(math) if "__" not in a]:
            if x in filters.filtermap or x in ibis.context.builtins:
                raise KeepExpr
            msg = "Unknown func {}()".format(x)
            raise SyntaxError(msg)
        fun = getattr(math, x)
        return fun(*args)

    bin_ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.Call: checkmath,
        ast.BinOp: ast.BinOp,
    }

    un_ops = {
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
        ast.UnaryOp: ast.UnaryOp,
    }

    ops = tuple(bin_ops) + tuple(un_ops)

    tree = ast.parse(s, mode="eval")

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)

        # Check if this is a constant node first (before trying to extract value)
        # utils.Constant is either ast.Constant (Py3.8+) or a tuple of types (Py2.7-3.7)
        if isinstance(node, utils.Constant):
            # Use helper to extract value - handles all Python versions
            # Note: don't check "if value is not None" because 0, False, None, '' are valid!
            return _get_constant_value(node)

        # Fallback: check for constant-like nodes by attribute presence
        # This handles potential future Python versions with new constant node types
        if hasattr(node, 'value'):
            return node.value
        if hasattr(node, 'n'):
            return node.n
        if hasattr(node, 's'):
            return node.s

        if isinstance(node, ast.Name):
            return node.id

        if isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)

            # collect lists of possible variables and return them
            ret = []
            if isinstance(left, list):
                ret += left
            elif isinstance(left, six.string_types):
                ret.append(left)
            if isinstance(right, list):
                ret += right
            elif isinstance(right, six.string_types):
                ret.append(right)

            if ret:
                return ret
            return bin_ops[type(node.op)](left, right)

        if isinstance(node, ast.UnaryOp):
            if isinstance(node.operand, ops):
                operand = _eval(node.operand)
            else:
                # Try to get value from constant node using helper
                operand = _get_constant_value(node.operand)
                if operand is None and not isinstance(node.operand, utils.Constant):
                    # operand is None AND it's not a Constant node, so it failed to extract
                    # (vs. operand is a Constant with value None)
                    try:
                        operand = _eval(node.operand)
                        if isinstance(operand, six.string_types):
                            raise SyntaxError("Cannot apply unary operator to variable")
                    except:
                        raise SyntaxError("Cannot extract value from operand: {}".format(type(node.operand).__name__))
            return un_ops[type(node.op)](operand)

        if isinstance(node, ast.Call):
            args = [_eval(x) for x in node.args]
            try:
                return checkmath(node.func.id, *args)
            except KeepExpr as e:
                return "{}({})".format(node.func.id, ",".join(map(str, args)))

        # Unknown node type - simpler error message (avoid expensive attribute enumeration)
        msg = "Unsupported AST node type: {}".format(type(node).__name__)
        raise SyntaxError(msg)

    return _eval(tree)


def apply_math_context(expr, argnames, args):
    """
    Takes an unparsable math expression, replaces argnames with args, then evaluates it again.
    """
    for index, arg in enumerate(argnames):
        expr = expr.replace(arg, str(args[index]))

    # re-evaluate math expr after resolving variables
    ret = safe_math_eval(expr)
    return ret


def eval_expr(expr):
    tree = ast.parse(expr, mode="eval")
    return eval(compile(tree, "<expr>", "eval"), {"__builtins__": {}})


def _is_constant_expr(expr):
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return False

    return not any(isinstance(node, ast.Name) for node in ast.walk(tree))


class Expression:

    re_func_call = re.compile(r'^([\w.]+)\((.*)\)$')
    re_varstring = re.compile(r'^[\w.]+$')

    def __init__(self, expr, token):
        self.token = token
        self.filters = []
        self.literal = None
        self.is_literal = False
        self.varstring = None
        self.func_args = None
        self.func_kwargs = None
        self.is_func_call = False
        self.dyn_args = False
        pipe_split = utils.splitc(expr.strip(), '|', strip=True)
        self._parse_primary_expr(pipe_split[0])
        self._parse_filters(pipe_split[1:])
        if self.is_literal and not self.dyn_args:
            self.literal = self._apply_filters_to_literal(self.literal)

    def _parse_primary_expr(self, expr):
        # 1) Try constant-only literal evaluation
        if _is_constant_expr(expr):
            try:
                self.literal = eval_expr(expr)
                self.is_literal = True
                return
            except Exception:
                # constant expression but invalid (syntax, zero-div, etc)
                pass

        # 2) Try math parsing (variable-aware)
        if any(op in expr for op in ('+', '/', '*', '**', '%')) or ' - ' in expr:
            try:
                matheval = safe_math_eval(expr)
                if isinstance(matheval, list):
                    # we've found possible variables in the math evaluation
                    self.is_literal = False
                    self.is_func_call = True

                    func_args = []
                    for arg in matheval:
                        if isinstance(arg, six.string_types):
                            if utils.isidentifier(arg):
                                func_args.append(ContextVariable(arg))
                                continue
                            elif self.re_func_call.match(arg):
                                func_args.append(Expression(arg, self.token))
                                continue
                        func_args.append(arg)

                    self.varstring = lambda *args: apply_math_context(expr, matheval, args)
                    self.func_args = func_args
                    self.func_kwargs = {}
                    return

                self.literal = matheval
                self.is_literal = True
                return
            except Exception:
                pass

        # 3) Variable / function parsing
        self.is_literal = False
        (
            self.is_func_call,
            self.dyn_args,
            self.varstring,
            self.func_args,
            self.func_kwargs,
        ) = self._try_parse_as_func_call(expr)

        if not self.is_func_call and not self.re_varstring.match(expr):
            msg = "Unparsable expression '{}'.".format(expr)
            errors.raise_(errors.TemplateSyntaxError(msg, self.token), None)

    def _try_parse_as_func_call(self, expr):
        match = self.re_func_call.match(expr)
        if not match:
            return False, False, expr, [], {}
        func_name = match.group(1)
        func_args = utils.splitc(match.group(2), ',', True, True)
        func_kwargs = {}
        dyn_args = False
        for index, arg in enumerate(func_args[:]):
            kwarg = None
            if "=" in arg:
                func_args.remove(arg)
                kwarg, arg = arg.split("=", 1)
            try:
                if kwarg:
                    func_kwargs[kwarg] = eval_expr(arg)
                else:
                    func_args[index] = eval_expr(arg)
            except Exception:
                # try resolving as variable
                if utils.isidentifier(arg):
                    if kwarg:
                        func_kwargs[kwarg] = ContextVariable(arg)
                    else:
                        func_args[index] = ContextVariable(arg)
                    dyn_args = True
                    continue

                # arg is a func call?
                arg_is_func = self.re_func_call.match(expr)
                if arg_is_func:
                    func_ret = Expression(arg, self.token)
                    if kwarg:
                        func_kwargs[kwarg] = func_ret
                    else:
                        func_args[index] = func_ret
                    continue

                msg = "Unparsable argument '{}'. Arguments must be valid Python literals.".format(arg)
                errors.raise_(errors.TemplateSyntaxError(msg, self.token))

        return True, dyn_args, func_name, func_args, func_kwargs

    def _parse_filters(self, filter_list):
        for filter_expr in filter_list:
            _, dyn_args, filter_name, filter_args, filter_kwargs = self._try_parse_as_func_call(filter_expr)
            if filter_name in filters.filtermap:
                self.filters.append((filter_name, filters.filtermap[filter_name], filter_args, filter_kwargs, dyn_args))
            else:
                msg = "Unrecognised filter name '{}'.".format(filter_name)
                raise errors.TemplateSyntaxError(msg, self.token)

    def _apply_filters_to_literal(self, obj):
        for filt in self.filters[:]:
            name, func, args, kwargs, dyn_args = filt
            if dyn_args or any(isinstance(a, Expression) for a in args) or any(isinstance(a, Expression)
                                                                               for a in kwargs.values()):
                continue
            try:
                obj = func(obj, *args, **kwargs)
                self.filters.remove(filt)
            except Exception as err:
                msg = "Error applying filter '{}'. ".format(name)
                errors.raise_(errors.TemplateSyntaxError(msg, self.token), err)
        return obj

    def eval(self, context):
        if self.is_literal and not self.dyn_args:
            if self.filters:
                # we have filters left
                return self._apply_filters_to_variable(self.literal, context)
            return self.literal
        else:
            return self._resolve_variable(context)

    def _resolve_arg_to_variable(self, arg, context):
        if isinstance(arg, ContextVariable):
            return context.resolve(arg, self.token)
        elif isinstance(arg, Expression):
            return arg.eval(context)
        return arg

    def _resolve_variable(self, context):
        if isinstance(self.varstring, six.string_types):
            obj = context.resolve(self.varstring, self.token)
        else:
            obj = self.varstring

        if self.is_func_call:
            try:
                func_args = []
                for index, arg in enumerate(self.func_args):
                    func_args.append(self._resolve_arg_to_variable(arg, context))

                fkw = {}
                for kwarg, value in self.func_kwargs.items():
                    fkw[kwarg] = self._resolve_arg_to_variable(value, context)

                if getattr(obj, "with_context", False):
                    fkw["context"] = context
                    obj = obj(*func_args, **fkw)
                else:
                    obj = obj(*func_args, **fkw)

                # a filter/builtin might return a masked variable name whose content should be resolved in the current
                # context. try to do so.
                if isinstance(obj, ResolveContextVariable):
                    value = context.resolve(obj, self.token)
                    obj = context.resolve(value, self.token)

            except Exception as err:
                msg = "Error calling function '{}'.".format(self.varstring)
                errors.raise_(errors.TemplateRenderingError(msg, self.token), err)
        return self._apply_filters_to_variable(obj, context)

    def _apply_filters_to_variable(self, obj, context):
        for name, func, args, kwargs, _ in self.filters:
            try:
                _args = []
                for arg in args:
                    if isinstance(arg, Expression):
                        _args.append(arg.eval(context))
                        continue
                    _args.append(self._resolve_arg_to_variable(arg, context))

                fkw = {}
                for kwarg, value in kwargs.items():
                    if isinstance(value, Expression):
                        fkw[kwarg] = value.eval(context)
                        continue
                    fkw[kwarg] = self._resolve_arg_to_variable(value, context)

                if getattr(func, "with_context", False):
                    fkw["context"] = context
                    obj = func(obj, *_args, **fkw)
                else:
                    obj = func(obj, *_args, **fkw)
            except Exception as err:
                msg = "Error applying filter '{}'.".format(name)
                errors.raise_(errors.TemplateRenderingError(msg, self.token), err)
        return obj


# Base class for all node objects. To render a node into a string call its .render() method.
# Subclasses shouldn't override the base .render() method; instead they should override
# .wrender() which ensures that any uncaught exceptions are wrapped in a TemplateRenderingError.
class Node:

    def __init__(self, token=None, children=None):
        self.token = token
        self.children = children or []
        try:
            self.process_token(token)
        except errors.TemplateError:
            raise
        except Exception as err:
            if token:
                tagname = "'{}'".format(token.keyword) if token.type == "INSTRUCTION" else token.type
                msg = "An unexpected error occurred while parsing the {} tag: ".format(tagname)
                msg += "{name}: {err}".format(name=err.__class__.__name__, err=err)
            else:
                msg = "Unexpected syntax error: {name}: {err}".format(name=err.__class__.__name__, err=err)
            errors.raise_(errors.TemplateSyntaxError(msg, token), err)

    def __str__(self):
        return self.to_str()

    def to_str(self, depth=0):
        output = ["·  " * depth + "{}".format(self.__class__.__name__)]
        for child in self.children:
            output.append(child.to_str(depth + 1))
        return "\n".join(output)

    def render(self, context):
        try:
            return self.wrender(context)
        except errors.TemplateError:
            raise
        except Exception as err:
            if self.token:
                tagname = "'{}'".format(self.token.keyword) if self.token.type == "INSTRUCTION" else self.token.type
                msg = "An unexpected error occurred while rendering the {} tag: ".format(tagname)
                msg += "{name}: {err}".format(name=err.__class__.__name__, err=err)
            else:
                msg = "Unexpected rendering error: {name}: {err}".format(name=err.__class__.__name__, err=err)
            errors.raise_(errors.TemplateRenderingError(msg, self.token), err)

    def wrender(self, context):
        return ''.join(child.render(context) for child in self.children)

    def process_token(self, token):
        pass

    def exit_scope(self):
        pass

    def split_children(self, delimiter_class):
        for index, child in enumerate(self.children):
            if isinstance(child, delimiter_class):
                return self.children[:index], child, self.children[index+1:]
        return self.children, None, []


# TextNodes represent ordinary template text, i.e. text not enclosed in tag delimiters.
class TextNode(Node):

    def wrender(self, context):
        return self.token.text


# A PrintNode evaluates an expression and prints its result. Multiple expressions can be listed
# separated by 'or' or '||'. The first expression to resolve to a truthy value will be printed.
# (If none of the expressions are truthy the final value will be printed regardless.)
#
#     {{ <expr> or <expr> or <expr> }}
#
# Alternatively, print statements can use the ternary operator: ?? ::
#
#     {{ <test-expr> ?? <expr1> :: <expr2> }}
#
# If <test-expr> is truthy, <expr1> will be printed, otherwise <expr2> will be printed.
#
# Note that either OR-chaining or the ternary operator can be used in a single print statement,
# but not both.
class PrintNode(Node):

    def process_token(self, token):
        chunks = utils.splitre(token.text, (r'\?\?', r'\:\:'), True)
        if len(chunks) == 5 and chunks[1] == '??' and chunks[3] == '::':
            self.is_ternary = True
            self.test_expr = Expression(chunks[0], token)
            self.true_branch_expr = Expression(chunks[2], token)
            self.false_branch_expr = Expression(chunks[4], token)
        else:
            self.is_ternary = False
            exprs = utils.splitre(token.text, (r'\s+or\s+', r'\|\|'))
            self.exprs = [Expression(e, token) for e in exprs]

    def wrender(self, context):
        if self.is_ternary:
            if self.test_expr.eval(context):
                content = self.true_branch_expr.eval(context)
            else:
                content = self.false_branch_expr.eval(context)
        else:
            for expr in self.exprs:
                content = expr.eval(context)
                if content:
                    break
        return filters.escape(str(content)) if self.token.type == "EPRINT" else str(content)


# ForNodes implement `for ... in ...` looping over iterables.
#
#     {% for <var> in <expr> %} ... [ {% empty %} ... ] {% endfor %}
#
# ForNodes support unpacking into multiple loop variables:
#
#     {% for <var1>, <var2> in <expr> %}
#
@register('for', 'endfor')
class ForNode(Node):

    regex = re.compile(r'for\s+(\w+(?:,\s*\w+)*)\s+in\s+(.+)')

    def process_token(self, token):
        match = self.regex.match(token.text)
        if match is None:
            msg = "Malformed 'for' tag."
            raise errors.TemplateSyntaxError(msg, token)
        self.loopvars = [var.strip() for var in match.group(1).split(',')]
        self.expr = Expression(match.group(2), token)

    def wrender(self, context):
        collection = self.expr.eval(context)
        if collection and hasattr(collection, '__iter__'):
            collection = list(collection)
            length = len(collection)
            unpack = len(self.loopvars) > 1
            output = []
            for index, item in enumerate(collection):
                context.push()
                if unpack:
                    try:
                        unpacked = dict(zip(self.loopvars, item))
                    except Exception as err:
                        msg = "Unpacking error."
                        errors.raise_(errors.TemplateRenderingError(msg, self.token), err)
                    else:
                        context.update(unpacked)
                else:
                    context[self.loopvars[0]] = item
                context['loop'] = {
                    'index': index,
                    'count': index + 1,
                    'length': length,
                    'is_first': index == 0,
                    'is_last': index == length - 1,
                    'parent': context.get('loop'),
                }
                output.append(self.for_branch.render(context))
                context.pop()
            return ''.join(output)
        else:
            return self.empty_branch.render(context)

    def exit_scope(self):
        for_nodes, _, empty_nodes = self.split_children(EmptyNode)
        self.for_branch = Node(None, for_nodes)
        self.empty_branch = Node(None, empty_nodes)


# Delimiter node to implement for/empty branching.
@register('empty')
class EmptyNode(Node):
    pass


# IfNodes implement if/elif/else branching.
#
#     {% if [not] <expr> %} ... {% endif %}
#     {% if [not] <expr> <operator> <expr> %} ... {% endif %}
#     {% if <...> %} ... {% elif <...> %} ... {% else %} ... {% endif %}
#
# IfNodes support 'and' and 'or' conjunctions; 'and' has higher precedence so:
#
#     if a and b or c and d
#
# is treated as:
#
#     if (a and b) or (c and d)
#
# Note that explicit brackets are not supported.
@register('if', 'endif')
class IfNode(Node):

    condition = collections.namedtuple('Condition', 'negated lhs op rhs')

    re_condition = re.compile(r'''
        (not\s+)?(.+?)\s+(==|!=|<|>|<=|>=|not[ ]in|in)\s+(.+)
        |
        (not\s+)?(.+)
        ''', re.VERBOSE
    )

    operators = {
        '==': operator.eq,
        '!=': operator.ne,
        '<': operator.lt,
        '>': operator.gt,
        '<=': operator.le,
        '>=': operator.ge,
        'in': lambda a, b: a in b,
        'not in': lambda a, b: a not in b,
    }

    def process_token(self, token):
        self.tag = token.keyword
        try:
            conditions = token.text.split(None, 1)[1]
        except:
            msg = "Malformed '{}' tag.".format(self.tag)
            errors.raise_(errors.TemplateSyntaxError(msg, token), None)

        self.condition_groups = [
            [
                self.parse_condition(condstr)
                for condstr in utils.splitre(or_block, (r'\s+and\s+', r'&&'))
            ]
            for or_block in utils.splitre(conditions, (r'\s+or\s+', r'\|\|'))
        ]

    def parse_condition(self, condstr):
        match = self.re_condition.match(condstr)
        if match.group(2):
            return self.condition(
                negated = bool(match.group(1)),
                lhs = Expression(match.group(2), self.token),
                op = self.operators[match.group(3)],
                rhs = Expression(match.group(4), self.token),
            )
        else:
            return self.condition(
                negated = bool(match.group(5)),
                lhs = Expression(match.group(6), self.token),
                op = None,
                rhs = None,
            )

    def eval_condition(self, cond, context):
        try:
            if cond.op:
                result = cond.op(cond.lhs.eval(context), cond.rhs.eval(context))
            else:
                result = operator.truth(cond.lhs.eval(context))
        except Exception as err:
            msg = "An exception was raised while evaluating the condition in the "
            msg += "'{}' tag.".format(self.tag)
            errors.raise_(errors.TemplateRenderingError(msg, self.token), err)
        if cond.negated:
            result = not result
        return result

    def wrender(self, context):
        for condition_group in self.condition_groups:
            for condition in condition_group:
                is_true = self.eval_condition(condition, context)
                if not is_true:
                    break
            if is_true:
                break
        if is_true:
            return self.true_branch.render(context)
        else:
            return self.false_branch.render(context)

    def exit_scope(self):
        if_nodes, elif_node, elif_nodes = self.split_children(ElifNode)
        if elif_node:
            self.true_branch = Node(None, if_nodes)
            self.false_branch = IfNode(elif_node.token, elif_nodes)
            self.false_branch.exit_scope()
            return
        if_nodes, _, else_nodes = self.split_children(ElseNode)
        self.true_branch = Node(None, if_nodes)
        self.false_branch = Node(None, else_nodes)


# Delimiter node to implement if/elif branching.
@register('elif')
class ElifNode(Node):
    pass


# Delimiter node to implement if/else branching.
@register('else')
class ElseNode(Node):
    pass


# CycleNodes cycle over an iterable expression.
#
#     {% cycle <expr> %}
#
# Each time the node is evaluated it will render the next value in the sequence, looping once it
# reaches the end; e.g.
#
#     {% cycle 'odd', 'even' %}
#
# will alternate continuously between printing 'odd' and 'even'.
@register('cycle')
class CycleNode(Node):

    def process_token(self, token):
        try:
            tag, arg = token.text.split(None, 1)
        except:
            msg = "Malformed 'cycle' tag."
            errors.raise_(errors.TemplateSyntaxError(msg, token), None)
        self.expr = Expression(arg, token)

    def wrender(self, context):
        # We store our state info on the context object to avoid a threading mess if
        # the template is being simultaneously rendered by multiple threads.
        if not self in context.stash:
            items = self.expr.eval(context)
            if not hasattr(items, '__iter__'):
                items = ''
            context.stash[self] = itertools.cycle(items)
        iterator = context.stash[self]
        return str(next(iterator, ''))


# IncludeNodes include a sub-template.
#
#     {% include <expr> %}
#
#     {% include <expr> with <name> = <expr> %}
#
#     {% include <expr> with <name1> = <expr> & <name2> = <expr> %}
#
# Requires a template name which can be supplied as either a string literal or a variable
# resolving to a string. This name will be passed to the registered template loader.
@register('include')
class IncludeNode(Node):
    def process_token(self, token):
        self.variables = {}
        parts = utils.splitre(token.text[7:], [r"with\s"])
        if len(parts) == 1:
            self.template_arg = parts[0]
            self.template_expr = Expression(parts[0], token)
        elif len(parts) == 2:
            self.template_arg = parts[0]
            self.template_expr = Expression(parts[0], token)
            chunks = utils.splitc(parts[1], "&", strip=True, discard_empty=True)
            for chunk in chunks:
                try:
                    name, expr = chunk.split('=', 1)
                    self.variables[name.strip()] = Expression(expr.strip(), token)
                except Exception as e:
                    raise
                    errors.raise_(errors.TemplateSyntaxError("Malformed 'include' tag.", token), None)
        else:
            raise errors.TemplateSyntaxError("Malformed 'include' tag.", token)

    def wrender(self, context):
        template_name = self.template_expr.eval(context)
        if isinstance(template_name, str):
            if ibis.loader:
                template = ibis.loader(template_name)
                context.push()
                for name, expr in self.variables.items():
                    context[name] = expr.eval(context)
                rendered = template.root_node.render(context)
                context.pop()
                return rendered
            else:
                msg = "No template loader has been specified. "
                msg += "A template loader is required by the 'include' tag in "
                msg += "template '{template_id}', line {line_number}.".format(template_id=self.token.template_id,
                                                                              line_number=self.token.line_number)
                raise errors.TemplateLoadError(msg)
        else:
            msg = "Invalid argument for the 'include' tag. "
            msg += "The variable '{}' should evaluate to a string. ".format(self.template_arg)
            msg += "This variable has the value: {}.".format(repr(template_name))
            raise errors.TemplateRenderingError(msg, self.token)


# ExtendsNodes implement template inheritance. They indicate that the current template inherits
# from or 'extends' the specified parent template.
#
#     {% extends "parent.txt" %}
#
# Requires the parent name as a string literal to pass to the registered template loader.
@register('extends')
class ExtendsNode(Node):

    def process_token(self, token):
        try:
            tag, arg = token.text.split(None, 1)
        except:
            errors.raise_(errors.TemplateSyntaxError("Malformed 'extends' tag.", token), None)

        expr = Expression(arg, token)
        if expr.is_literal and isinstance(expr.literal, str):
            self.parent_name = expr.literal
        else:
            msg = "Malformed 'extends' tag. The template name must be a string literal."
            raise errors.TemplateSyntaxError(msg, token)


# BlockNodes implement template inheritance.
#
#    {% block <title> %} ... {% endblock %}
#
# A block tag defines a titled block of content that can be overridden in child templates.
@register('block', 'endblock')
class BlockNode(Node):

    def process_token(self, token):
        self.title = token.text[5:].strip()

    def wrender(self, context):
        block_list = []
        for template in context.templates:
            block_node = template.blocks.get(self.title)
            if block_node:
                block_list.append(block_node)
        return self.render_block(context, block_list)

    def render_block(self, context, block_list):
        if block_list:
            current_block = block_list.pop(0)
            context.push()
            context['super'] = lambda: self.render_block(context, block_list)
            output = ''.join(child.render(context) for child in current_block.children)
            context.pop()
            return output
        else:
            return ''


# Strips leading and trailing whitespace along with all whitespace between HTML tags.
@register('spaceless', 'endspaceless')
class SpacelessNode(Node):

    def wrender(self, context):
        output = ''.join(child.render(context) for child in self.children)
        return filters.spaceless(output).strip()


# Trims leading and trailing whitespace.
@register('trim', 'endtrim')
class TrimNode(Node):

    def wrender(self, context):
        return ''.join(child.render(context) for child in self.children).strip()


# Caches a complex expression under a simpler alias.
#
#    {% with <name> = <expr> %} ... {% endwith %}
#
#    {% with <name1> = <expr> & <name2> = <expr> %} ... {% endwith %}
#
@register('with', 'endwith')
class WithNode(Node):
    def process_token(self, token):
        self.variables = {}
        chunks = utils.splitc(token.text[4:], "&", strip=True, discard_empty=True)
        for chunk in chunks:
            try:
                name, expr = chunk.split('=', 1)
                self.variables[name.strip()] = Expression(expr.strip(), token)
            except:
                errors.raise_(errors.TemplateSyntaxError("Malformed 'with' tag.", token), None)

    def wrender(self, context):
        context.push()
        for name, expr in self.variables.items():
            context[name] = expr.eval(context)
        rendered = ''.join(child.render(context) for child in self.children)
        context.pop()
        return rendered
