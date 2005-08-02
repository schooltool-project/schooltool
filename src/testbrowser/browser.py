##############################################################################
#
# Copyright (c) 2005 Zope Corporation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""Mechanize-based Functional Doctest interfaces

$Id: browser.py 37603 2005-07-30 15:56:06Z benji_york $
"""
__docformat__ = "reStructuredText"
import re
import mechanize
import zope.interface

from testbrowser import interfaces

RegexType = type(re.compile(''))

header_key = 'X-zope-handle-errors'
        
class Browser(object):
    """A web user agent."""
    zope.interface.implements(interfaces.IBrowser)

    def __init__(self, url=None, mech_browser=None):
        if mech_browser is None:
            mech_browser = mechanize.Browser()
        self.mech_browser = mech_browser
        
        if url is not None:
            self.open(url)

    
    def url(self):
        """See zope.testbrowser.interfaces.IBrowser"""
        return self.mech_browser.geturl()
    url = property(url)

    def isHtml(self):
        """See zope.testbrowser.interfaces.IBrowser"""
        return self.mech_browser.viewing_html()
    isHtml = property(isHtml)

    def title(self):
        """See zope.testbrowser.interfaces.IBrowser"""
        return self.mech_browser.title()
    title = property(title)

    def controls(self):
        """See zope.testbrowser.interfaces.IBrowser"""
        return ControlsMapping(self)
    controls = property(controls)

    def forms(self):
        """See zope.testbrowser.interfaces.IBrowser"""
        return FormsMapping(self)
    forms = property(forms)

    def contents(self):
        """See zope.testbrowser.interfaces.IBrowser"""
        response = self.mech_browser.response()
        old_location = response.tell()
        response.seek(0)
        for line in iter(lambda: response.readline().strip(), ''):
            pass
        contents = response.read()
        response.seek(old_location)
        return contents
    contents = property(contents)

    def headers(self):
        """See zope.testbrowser.interfaces.IBrowser"""
        return self.mech_browser.response().info()
    headers = property(headers)


    def getHandleErrors(self):
        headers = self.mech_browser.addheaders
        return dict(headers).get(header_key, True)

    def setHandleErrors(self, value):
        headers = self.mech_browser.addheaders
        current_value = self.getHandleErrors()
        if current_value == value:
            return
        if header_key in dict(headers):
            headers.remove((header_key, current_value))
        headers.append((header_key, value))
            
    handleErrors = property(getHandleErrors, setHandleErrors)

    def open(self, url, data=None):
        """See zope.testbrowser.interfaces.IBrowser"""
        self.mech_browser.open(url, data)
        self._changed()

    def reload(self):
        """See zope.testbrowser.interfaces.IBrowser"""
        self.mech_browser.reload()
        self._changed()

    def goBack(self, count=1):
        """See zope.testbrowser.interfaces.IBrowser"""
        self.mech_browser.back(count)
        self._changed()

    def addHeader(self, key, value):
        """See zope.testbrowser.interfaces.IBrowser"""
        self.mech_browser.addheaders.append( (key, value) )

    def click(self, text=None, url=None, id=None, name=None, coord=(1,1)):
        """See zope.testbrowser.interfaces.IBrowser"""
        # Determine whether the click is a form submit and click the submit
        # button if this is the case.
        form, control = self._findControl(text, id, name, type='submit')
        if control is None:
            form, control = self._findControl(text, id, name, type='image')
        if control is not None:
            self._clickSubmit(form, control, coord)
            self._changed()
            return

        # If we get here, we didn't find a control to click, so we'll look for
        # a regular link.

        if id is not None:
            def predicate(link):
                return dict(link.attrs).get('id') == id
            self.mech_browser.follow_link(predicate=predicate)
        else:
            if isinstance(text, RegexType):
                text_regex = text
            elif text is not None:
                text_regex = re.compile(re.escape(text), re.DOTALL)
            else:
                text_regex = None

            if isinstance(url, RegexType):
                url_regex = url
            elif url is not None:
                url_regex = re.compile(re.escape(url), re.DOTALL)
            else:
                url_regex = None

            self.mech_browser.follow_link(
                text_regex=text_regex, url_regex=url_regex)
        self._changed()

    def getControl(self, text=None, id=None, name=None):
        """See zope.testbrowser.interfaces.IBrowser"""
        form, control = self._findControl(text, id, name)
        if control is None:
            raise ValueError('could not locate control: ' + text)
        return Control(control)

    def _findControl(self, text, id, name, type=None, form=None):
        for control_form, control in self._controls:
            if form is None or control_form == form:
                if (((id is not None and control.id == id)
                or (name is not None and control.name == name)
                or (text is not None and text in str(control.value))
                ) and (type is None or control.type == type)):
                    self.mech_browser.form = control_form
                    return control_form, control
    
        return None, None
        
    def _findForm(self, id, name, action):
        for form in self.mech_browser.forms():
            if ((id is not None and form.attrs.get('id') == id)
            or (name is not None and form.name == name)
            or (action is not None and re.search(action, str(form.action)))):
                self.mech_browser.form = form
                return form

        return None
        
    def _clickSubmit(self, form, control, coord):
        self.mech_browser.open(form.click(
                    id=control.id, name=control.name, coord=coord))

    __controls = None
    def _controls(self):
        if self.__controls is None:
            self.__controls = []
            for form in self.mech_browser.forms():
                for control in form.controls:
                    self.__controls.append( (form, control) )
        return self.__controls
    _controls = property(_controls)

    def _changed(self):
        self.__controls = None


class Control(object):
    """A control of a form."""
    zope.interface.implements(interfaces.IControl)

    def __init__(self, control):
        self.mech_control = control

        # for some reason ClientForm thinks we shouldn't be able to modify
        # hidden fields, but while testing it is sometimes very important
        if self.mech_control.type == 'hidden':
            self.mech_control.readonly = False

    def __getattr__(self, name):
        # See zope.testbrowser.interfaces.IControl
        names = ['disabled', 'type', 'name', 'multiple']
        booleans = ['disabled', 'multiple']
        if name in names:
            result = getattr(self.mech_control, name, None)
        else:
            raise AttributeError(name)

        if name in booleans:
            result = bool(result)

        return result

    def getValue(self):
        value = self.mech_control.value
        if self.type == 'checkbox' and self.options == [True]:
            value = bool(value)
        return value
    
    def setValue(self, value):
        if self.mech_control.type == 'file':
            self.mech_control.add_file(value)
            return
        if self.type == 'checkbox' and self.options == [True]:
            if value: 
                value = ['on']
            else:
                value = []
        self.mech_control.value = value
    
    value = property(getValue, setValue)

    def clear(self):
        self.mech_control.clear()

    def options(self):
        """See zope.testbrowser.interfaces.IControl"""
        if (self.type == 'checkbox'
        and self.mech_control.possible_items() == ['on']):
            return [True]
        try:
            return self.mech_control.possible_items()
        except:
            raise AttributeError('options')
    options = property(options)

    def __repr__(self):
        return "<Control name=%r type=%r>" %(self.name, self.type)


class FormsMapping(object):
    """All forms on the page of the browser."""
    zope.interface.implements(interfaces.IFormsMapping)
    
    def __init__(self, browser):
        self.browser = browser

    def __getitem__(self, key):
        """See zope.interface.common.mapping.IItemMapping"""
        form = self.browser._findForm(key, key, None)
        if form is None:
            raise KeyError(key)
        return Form(self.browser, form)

    def get(self, key, default=None):
        """See zope.interface.common.mapping.IReadMapping"""
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key):
        """See zope.interface.common.mapping.IReadMapping"""
        return self.browser._findForm(key, key, None) is not None


class ControlsMapping(object):
    """A mapping of all controls in a form or a page."""
    zope.interface.implements(interfaces.IControlsMapping)

    def __init__(self, browser, form=None):
        """Initialize the ControlsMapping
        
        browser - a Browser instance
        form - a ClientForm instance
        """
        self.browser = browser
        self.mech_form = form

    def __getitem__(self, key):
        """See zope.testbrowser.interfaces.IControlsMapping"""
        form, control = self.browser._findControl(key, key, key,
                                                  form=self.mech_form)
        if control is None:
            raise KeyError(key)
        return Control(control).value

    def get(self, key, default=None):
        """See zope.interface.common.mapping.IReadMapping"""
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, item):
        """See zope.testbrowser.interfaces.IControlsMapping"""
        try:
            self[item]
        except KeyError:
            return False
        else:
            return True

    def __setitem__(self, key, value):
        """See zope.testbrowser.interfaces.IControlsMapping"""
        form, control = self.browser._findControl(key, key, key)
        if control is None:
            raise KeyError(key)
        Control(control).value = value

    def update(self, mapping):
        """See zope.testbrowser.interfaces.IControlsMapping"""
        for k, v in mapping.items():
            self[k] = v


class Form(ControlsMapping):
    """HTML Form"""
    zope.interface.implements(interfaces.IForm)
    
    def __getattr__(self, name):
        # See zope.testbrowser.interfaces.IForm
        names = ['action', 'method', 'enctype', 'name']
        if name in names:
            return getattr(self.mech_form, name, None)
        else:
            raise AttributeError(name)

    def id(self):
        """See zope.testbrowser.interfaces.IForm"""
        return self.mech_form.attrs.get('id')
    id = property(id)

    def controls(self):
        """See zope.testbrowser.interfaces.IForm"""
        return ControlsMapping(browser=self.browser, form=self.mech_form)
    controls = property(controls)

    def submit(self, text=None, id=None, name=None, coord=(1,1)):
        """See zope.testbrowser.interfaces.IForm"""
        form, control = self.browser._findControl(
            text, id, name, type='submit', form=self.mech_form)

        if control is None:
            form, control = self.browser._findControl(
                text, id, name, type='image', form=self.mech_form)

        if control is not None:
            self.browser._clickSubmit(form, control, coord)
            self.browser._changed()

    def getControl(self, text=None, id=None, name=None):
        """See zope.testbrowser.interfaces.IForm"""
        form, control = self.browser._findControl(text, id, name,
                                                  form=self.mech_form)
        if control is None:
            raise ValueError('could not locate control: ' + text)
        return Control(control)
