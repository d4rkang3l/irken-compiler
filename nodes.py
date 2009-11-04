# -*- Mode: Python -*-

# lambda language

# XXX why not name this module 'nodes'?

import typing

# used to generate a unique identifier for each node.  it's important that these
#   be *unique*, because the serial number of a node is later used as a type
#   variable during type inference!

class serial_counter:

    def __init__ (self):
        self.counter = 0

    def next (self):
        result = self.counter
        self.counter += 1
        return result

serial = serial_counter()

# node types

class node:

    # The initial implementation of the node class did the 'right' thing,
    #   by subclassing <node> to get each of the individual node types.
    # Then of course I started using all these nice attributes.  For example,
    #   I would have a 'calls' attribute on each function that would track
    #   every time it was called.
    # Once I started writing code that transformed this tree of nodes, however,
    #   this all came back to bite me.  The problem is that you need to be able
    #   to safely *copy* trees of these objects. Otherwise you get dangling
    #   pointers and lists, etc... even simple transformations were coming out
    #   completely mangled.  It's *really* made me appreciate the ideas of pure
    #   functional data structures!
    # So, this was rewritten with <kind>, <params>, and <subs>.  Clumsy, but easy
    #   to copy and rewrite.  Accessing these attributes is a real pain, but I
    #   don't have to worry about losing things, or surprises.  Also, walking the
    #   tree of nodes is much simpler.
    # However.  The rest of the compiler doesn't want to be rewritten in this way,
    #   so the last thing we do before handing off to cps.py is to add a bunch of
    #   attributes to each node, in fix_attribute_names().
    # I plan to fix this when it becomes either too clumsy or too embarrassing.
    #
    # XXX Pyrex solves this interestingly... it uses a special attribute to list
    #     the *names* of attributes that refer to sub-expressions.  I think I
    #     considered this and discarded it because the 'set of all
    #     sub-expressions' is still difficult to synthesize, in cases where one
    #     attribute might hold a single expression, and others might hold sets
    #     of them.

    # generic flag
    flag = False
    constructor = False

    def __init__ (self, kind, params=(), subs=(), type=None):
        self.kind = kind
        self.params = params
        # XXX consider making this tuple(subs)
        self.subs = subs
        self.serial = serial.next()
        size = 1
        for sub in subs:
            size += sub.size
        self.size = size
        self.type = type

    def pprint (self, depth=0):
        print '%3d' % (self.serial,),
        print '  ' * depth, self.kind,
        print '[%d]' % (self.size,),
        if self.type:
            print '%s ' % (self.type,),
        else:
            print '? ',
        if self.params:
            print self.params
        else:
            print
        for sub in self.subs:
            sub.pprint (depth+1)

    def __repr__ (self):
        if self.params:
            return '<%s %r %d>' % (self.kind, self.params, self.serial)
        else:
            return '<%s %d>' % (self.kind, self.serial)

    def __iter__ (self):
        return walk_node (self)

    def is_a (self, kind):
        return self.kind == kind

    def one_of (self, *kinds):
        return self.kind in kinds

    def is_var (self, name):
        return self.kind == 'varref' and self.params == name

    def copy (self):
        return node (self.kind, self.params, self.subs, self.type)

    def deep_copy (self):
        # XXX ugliness.  because self.params is sometimes a list, it would behoove
        #   use to use a copy of that list!  However it's not always a list.
        if is_a (self.params, list):
            params = self.params[:]
        else:
            params = self.params

        r = node (self.kind, params, [ x.deep_copy() for x in self.subs ], self.type)
        
        # special-case: binding positions are not nodes or sub-expressions, but
        #   we want fresh copies of them as well...
        if r.binds():
            # XXX urgh, we'll lose type information here.
            binds = [ vardef (x.name) for x in r.get_names() ]
            if self.is_a ('let_splat'):
                r.params = binds
            elif self.is_a ('fix'):
                r.params = binds
                # update function attributes
                for i in range (len (binds)):
                    if r.subs[i].is_a ('function'):
                        binds[i].function = r.subs[i]
            elif self.is_a ('function'):
                # function
                r.params[1] = binds
            else:
                raise ValueError ("new binding construct?")
        return r

    def binds (self):
        return self.kind in ('let_splat', 'function', 'fix')

    def get_names (self):
        if self.kind == 'function':
            return self.params[1]
        elif self.kind in ('let_splat', 'fix'):
            return self.params
        else:
            raise ValueError ("get_names() not valid for this node")

    def get_body (self):
        # get the body of an expression
        if self.one_of ('let_splat', 'fix', 'function'):
            return self.subs[-1]
        else:
            return self

    def get_rator (self):
        assert (self.kind == 'application')
        return self.subs[0]

    def get_rands (self):
        assert (self.kind == 'application')
        return self.subs[1:]

    def fix_attribute_names (self):
        if self.kind == 'varref':
            self.name = self.params
        elif self.kind == 'varset':
            self.name = self.params
            self.value = self.subs[0]
        elif self.kind == 'literal':
            self.type, self.value = self.params
        elif self.kind == 'primapp':
            self.name = self.params
            self.args = self.subs
        elif self.kind == 'sequence':
            self.exprs = self.subs
        elif self.kind == 'cexp':
            self.form, self.type_sig = self.params
            self.args = self.subs
        elif self.kind == 'verify':
            self.tc, self.safety = self.params
            self.arg = self.subs[0]
        elif self.kind == 'conditional':
            [self.test_exp, self.then_exp, self.else_exp] = self.subs
        elif self.kind == 'function':
            self.name, self.formals, self.recursive, self.type = self.params
            self.body = self.subs[0]
        elif self.kind == 'fix':
            self.names = self.params
            self.inits = self.subs[:-1]
            self.body = self.subs[-1]
        elif self.kind == 'let_splat':
            self.names = self.params
            self.inits = self.subs[:-1]
            self.body = self.subs[-1]
        elif self.kind == 'application':
            self.recursive = self.params
            self.rator = self.subs[0]
            self.rands = self.subs[1:]
        elif self.kind == 'get':
            [self.ob] = self.subs
            self.name = self.params
        elif self.kind == 'set':
            [self.ob, self.val] = self.subs
            self.name = self.params
        elif self.kind == 'make_tuple':
            (self.type, self.tag) = self.params
            self.args = self.subs
        elif self.kind == 'typecase':
            self.vtype, self.alt_formals = self.params
            self.value = self.subs[0]
            self.alts = self.subs[1:]
        else:
            raise ValueError (self.kind)

def scheme_string (s):
    r = ['"']
    for ch in s:
        if s == '"':
            r.append ('\\')
            r.append ('"')
        else:
            r.append (ch)
    r.append ('"')
    return ''.join (r)

def to_scheme (node):
    if node.is_a ('varref'):
        return node.name
    elif node.is_a ('varset'):
        return ['set!', node.name, to_scheme (node.value)]
    elif node.is_a ('literal'):
        if node.type == 'string':
            return scheme_string (node.value)
        else:
            return node.value
    elif node.is_a ('primapp'):
        return [node.name] + [to_scheme (x) for x in node.args]
    elif node.is_a ('sequence'):
        return ['begin'] + [to_scheme (x) for x in node.exprs]
    elif node.is_a ('cexp'):
        return ['%%cexp', scheme_string (node.form)] + [to_scheme (x) for x in node.args]
    elif node.is_a ('conditional'):
        return ['if', to_scheme(node.test_exp),to_scheme(node.then_exp),to_scheme(node.else_exp)]
    elif node.is_a ('function'):
        return ['lambda', [x.name for x in node.formals]] + [to_scheme (node.body)]
    elif node.is_a ('fix'):
        return ['letrec', [[x.name, to_scheme (y)] for x,y in zip(node.names, node.inits)], to_scheme (node.body)]
    elif node.is_a ('let_splat'):
        return ['let*', [[x.name, to_scheme (y)] for x,y in zip(node.names, node.inits)], to_scheme (node.body)]
    elif node.is_a ('application'):
        return [to_scheme (node.rator)] + [to_scheme (x) for x in node.rands]
    elif node.is_a ('make_tuple'):
        return ['make_tuple', node.type] + [to_scheme (x) for x in node.args]
    elif node.is_a ('set'):
        return ['set', to_scheme (node.ob), node.name, to_scheme (node.val)]
    elif node.is_a ('get'):
        return ['get', to_scheme (node.ob), node.name]
    elif node.is_a ('typecase'):
        return ['typecase', node.params[0], node.params[1], [to_scheme (x) for x in node.alts]]
    else:
        raise ValueError

import sys
def as_sexp (x):
    if is_a (x, list):
        r = [as_sexp (y) for y in x]
        return '(%s)' % (' '.join (r))
    elif is_a (x, tuple):
        import pdb; pdb.set_trace()
    else:
        return str (x)

def walk_node (n):
    yield n
    for sub in n.subs:
        for x in walk_node (sub):
            yield x

def walk_up (n):
    for sub in n.subs:
        for x in walk_node (sub):
            yield x
    yield n

# this is *not* a node!
class vardef:
    def __init__ (self, name, type=None, nary=False):
        assert (is_a (name, str))
        self.name = name
        self.type = type
        self.nary = nary
        self.assigns = []
        self.refs = []
        self.function = None
        self.serial = serial.next()
        self.escapes = False
    def __repr__ (self):
        #return '{%s.%d}' % (self.name, self.serial)
        if self.type:
            return '{%s:%s}' % (self.name, self.type)
        else:
            return '{%s}' % (self.name,)

def varref (name):
    return node ('varref', name)

def varset (name, value):
    return node ('varset', name, [value])

def literal (kind, value):
    return node ('literal', (kind, value))

def primapp (name, args):
    return node ('primapp', name, args)

def sequence (exprs):
    if not exprs:
        exprs = [literal ('undefined', 'undefined')]
    return node ('sequence', (), exprs, type=exprs[-1].type)

def cexp (form, type_sig, args):
    return node ('cexp', (form, type_sig), args)

def make_tuple (type, tag, args):
    return node ('make_tuple', (type, tag), args)

def conditional (test_exp, then_exp, else_exp):
    return node ('conditional', (), [test_exp, then_exp, else_exp])

def function (name, formals, body, type=None):
    return node ('function', [name, formals, False, type], [body])

def fix (names, inits, body, type=None):
    n = node ('fix', names, inits + [body], type)
    for i in range (len (names)):
        if inits[i].is_a ('function'):
            names[i].function = inits[i]
    return n

def let_splat (names, inits, body, type=None):
    return node ('let_splat', names, inits + [body], type)

def application (rator, rands):
    return node ('application', False, [rator] + rands)
    
def get (ob, name):
    return node ('get', name, [ob])

def set (ob, name, val):
    return node ('set', name, [ob, val])

def typecase (vtype, value, alt_formals, alts):
    return node ('typecase', (vtype, alt_formals), [value] + alts)

# ================================================================================

class ConfusedError (Exception):
    pass

def parse_type (exp):
    assert (len (exp) >= 2)
    assert (is_a (x, str) for x in exp)
    assert (exp[-2] == '->')

    def pfun (x):
        if is_a (x, list):
            return parse_type (x)
        else:
            return x

    result_type = pfun (exp[-1])
    arg_types = tuple ([pfun(x) for x in exp[:-2]])
    return (result_type, arg_types)

from lisp_reader import atom

is_a = isinstance

class walker:

    """The walker converts from 's-expression' => 'node tree' representation"""

    def walk_exp (self, exp):
        WALK = self.walk_exp
        if is_a (exp, str):
            return varref (exp)
        elif is_a (exp, atom):
            return literal (exp.kind, exp.value)
        elif is_a (exp, list):
            rator = exp[0]
            simple = is_a (rator, str)
            if simple:
                if rator == '%%cexp':
                    type_sig = parse_type (exp[1])
                    assert (is_a (exp[2], atom))
                    assert (exp[2].kind == 'string')
                    form = exp[2].value
                    return cexp (form, type_sig, [ WALK (x) for x in exp[3:]])
                elif rator == '%%make-tuple':
                    type = exp[1]
                    tag = exp[2]
                    args = exp[3:]
                    return make_tuple (type, tag, [ WALK (x) for x in args ] )
                elif rator.startswith ('%'):
                    return primapp (rator, [WALK (x) for x in exp[1:]])
                elif rator == 'begin':
                    return sequence ([WALK (x) for x in exp[1:]])
                elif rator == 'set_bang':
                    ignore, name, val = exp
                    return varset (name, WALK (val))
                elif rator == 'quote':
                    return literal (exp[1].kind, exp[1].value)
                elif rator == 'if':
                    return conditional (WALK (exp[1]), WALK (exp[2]), WALK (exp[3]))
                elif rator == 'function':
                    fun_name, fun_type = exp[1]
                    nary, formals = exp[2]
                    formals = [vardef (name, type) for (name, type) in formals]
                    return function (fun_name, formals, WALK (exp[3]), fun_type)
                elif rator == 'let_splat':
                    ignore, vars, body = exp
                    names = [vardef(x[0]) for x in vars]
                    inits = [WALK (x[1])  for x in vars]
                    return let_splat (names, inits, WALK (body))
                elif rator == 'fix':
                    ignore, names, inits, body = exp
                    names = [vardef (x) for x in names]
                    inits = [WALK (x)   for x in inits]
                    return fix (names, inits, WALK (body))
                elif rator == 'get':
                    ignore, ob, name = exp
                    return get (WALK (ob), name)
                elif rator == 'set':
                    ignore, ob, name, val = exp
                    return set (WALK (ob), name, WALK (val))
                elif rator == 'typecase':
                    ignore, vtype, value, alt_formals, alts = exp
                    alt_formals = [ (selector, [vardef (name) for name in formals]) for selector, formals in alt_formals ]
                    return typecase (vtype, WALK(value), alt_formals, [WALK (x) for x in alts])
                else:
                    # a varref application
                    return application (WALK (rator), [WALK (x) for x in exp[1:]])
            else:
                # a non-simple application
                return application (WALK (rator), [ WALK (x) for x in exp[1:]])
        else:
            raise ValueError, exp

    def go (self, exp):
        exp = self.walk_exp (exp)
        if len (typing.datatypes):
            exp = add_constructors (exp)
        for node in exp:
            node.fix_attribute_names()
        return exp

# these worked by inserting the constructor definitions directly
#  into the node tree.  I think we want to avoid this now, since
#  we won't know the exact shape of each record until after typing.
def add_constructors (root):
    names = []
    inits = []
    for name, dt in typing.datatypes.items():
        if is_a (dt, typing.union):
            for sname, stype in dt.alts:
                fname, fun = dt.gen_constructor (sname)
                names.append (vardef (fname))
                inits.append (fun)
        elif is_a (dt, typing.product):
            fname, fun = dt.gen_constructor()
            names.append (vardef (fname))
            inits.append (fun)
        else:
            raise ValueError ("unknown datatype")
    return fix (names, inits, root)

# alpha conversion

def rename_variables (exp, datatypes):
    vars = []

    def lookup_var (name, lenv):
        while lenv:
            rib, lenv = lenv
            # walk rib backwards for the sake of <let*>
            #   (e.g., (let ((x 1) (x 2)) ...))
            for i in range (len(rib)-1, -1, -1):
                x = rib[i]
                if x.name == name:
                    return x
        if datatypes.has_key (name):
            return None
        elif name.startswith ('&'):
            return None
        else:
            raise ValueError ("unbound variable: %r" % (name,))

    # walk <exp>, inventing a new name for each <vardef>,
    #   renaming varref/varset as we go...
    def rename (exp, lenv):
        if exp.binds():
            defs = exp.get_names()
            for vd in defs:
                # hack to avoid renaming methods
                if vd.name.startswith ('&'):
                    vars.append (vd)
                elif vd.name != '_':
                    vd.alpha = len (vars)
                    vars.append (vd)
            if exp.is_a ('let_splat'):
                # this one is tricky
                names = []
                lenv = (names, lenv)
                for i in range (len (defs)):
                    # add each name only after its init
                    init = exp.subs[i]
                    rename (init, lenv)
                    names.append (defs[i])
                # now all the inits are done, rename body
                rename (exp.subs[-1], lenv)
                # ugh, non-local exit
                return
            else:
                # normal binding behavior
                lenv = (defs, lenv)
            if exp.is_a ('fix'):
                # rename functions
                for i in range (len (defs)):
                    if exp.subs[i].is_a ('function'):
                        if not defs[i].name.startswith ('&'):
                            exp.subs[i].params[0] = '%s_%d' % (defs[i].name, defs[i].alpha)
            for sub in exp.subs:
                rename (sub, lenv)
        elif exp.is_a ('typecase'):
            # this is a strangely shaped binding construct
            rename (exp.value, lenv)
            n = len (exp.alts)
            for i in range (n):
                selector, defs = exp.alt_formals[i]
                alt = exp.alts[i]
                for vd in defs:
                    vd.alpha = len (vars)
                    vars.append (vd)
                lenv = (defs, lenv)
                rename (alt, lenv)
        elif exp.one_of ('varref', 'varset'):
            name = exp.params
            probe = lookup_var (name, lenv)
            if probe:
                exp.var = probe
                if exp.is_a ('varset'):
                    if probe.nary:
                        raise ValueError ("can't assign to a varargs argument")
                exp.params = exp.name = '%s_%d' % (name, exp.var.alpha)
            for sub in exp.subs:
                rename (sub, lenv)
        else:
            for sub in exp.subs:
                rename (sub, lenv)

    #exp.pprint()
    rename (exp, None)
    # now go back and change the names of the vardefs
    for vd in vars:
        if vd.name.startswith ('&'):
            vd.name = vd.name[1:]
        elif vd.name != '_':
            vd.name = '%s_%d' % (vd.name, vd.alpha)

    result = {}
    for vd in vars:
        result[vd.name] = vd
    return result
