# Recipe stolen from open PR (https://github.com/sphinx-doc/sphinx/pull/1826).


from asyncio import iscoroutinefunction

from sphinx import addnodes
from sphinx.domains.python import (
    PyClassmember,
    PyModulelevel,
)
from sphinx.ext.autodoc import FunctionDocumenter as _FunctionDocumenter
from sphinx.ext.autodoc import MethodDocumenter as _MethodDocumenter


class PyCoroutineMixin(object):
    """Helper for coroutine-related Sphinx custom directives."""

    def handle_signature(self, sig, signode):
        ret = super(PyCoroutineMixin, self).handle_signature(sig, signode)
        signode.insert(0, addnodes.desc_annotation('coroutine ', 'coroutine '))
        return ret


class PyCoroutineFunction(PyCoroutineMixin, PyModulelevel):
    """Sphinx directive for coroutine functions."""

    def run(self):
        self.name = 'py:function'
        return PyModulelevel.run(self)


class PyCoroutineMethod(PyCoroutineMixin, PyClassmember):
    """Sphinx directive for coroutine methods."""

    def run(self):
        self.name = 'py:method'
        return PyClassmember.run(self)


class FunctionDocumenter(_FunctionDocumenter):
    """Automatically detect coroutine functions."""

    def import_object(self):
        ret = _FunctionDocumenter.import_object(self)
        if not ret:
            return ret

        obj = self.parent.__dict__.get(self.object_name)
        if iscoroutinefunction(obj):
            self.directivetype = 'coroutine'
            self.member_order = _FunctionDocumenter.member_order + 2
        return ret


class MethodDocumenter(_MethodDocumenter):
    """Automatically detect coroutine methods."""

    def import_object(self):
        ret = _MethodDocumenter.import_object(self)
        if not ret:
            return ret

        obj = self.parent.__dict__.get(self.object_name)
        if iscoroutinefunction(obj):
            self.directivetype = 'coroutinemethod'
            self.member_order = _MethodDocumenter.member_order + 2
        return ret


def setup(app):
    """Sphinx extension entry point."""

    # Add new directives.
    app.add_directive_to_domain('py', 'coroutine', PyCoroutineFunction)
    app.add_directive_to_domain('py', 'coroutinemethod', PyCoroutineMethod)

    # Customize annotations for anything that looks like a coroutine.
    app.add_autodocumenter(FunctionDocumenter)
    app.add_autodocumenter(MethodDocumenter)

    # Return extension meta data.
    return {
        'version': '1.0',
        'parallel_read_safe': True,
    }
