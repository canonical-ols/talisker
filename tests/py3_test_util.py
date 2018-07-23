##
## Copyright (c) 2015-2018 Canonical, Ltd.
## 
## Permission is hereby granted, free of charge, to any person obtaining a copy of
## this software and associated documentation files (the "Software"), to deal in
## the Software without restriction, including without limitation the rights to
## use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
## of the Software, and to permit persons to whom the Software is furnished to do
## so, subject to the following conditions:
## 
## The above copyright notice and this permission notice shall be included in all
## copies or substantial portions of the Software.
## 
## THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
## IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
## FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
## AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
## LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
## OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
## SOFTWARE.
##

# ignore this whole file for flake8, as when run under py2 it will break
# flake8: noqa

import talisker.util


def test_get_root_exception_implicit():
    exc = None
    try:
        try:
            try:
                raise Exception('root')
            except Exception:
                raise Exception('one')
        except Exception:
            raise Exception('two')
    except Exception as e:
        exc = e

    root = talisker.util.get_root_exception(exc)
    assert root.args == ('root',)


def test_get_root_exception_explicit():
    exc = None
    try:
        try:
            try:
                raise Exception('root')
            except Exception as a:
                raise Exception('one') from a
        except Exception as b:
            raise Exception('two') from b
    except Exception as c:
        exc = c
    root = talisker.util.get_root_exception(exc)
    assert root.args == ('root',)


def test_get_root_exception_mixed():
    exc = None
    try:
        try:
            try:
                raise Exception('root')
            except Exception as a:
                raise Exception('one') from a
        except Exception:
            raise Exception('two')
    except Exception as e:
        exc = e
    root = talisker.util.get_root_exception(exc)
    assert root.args == ('root',)
