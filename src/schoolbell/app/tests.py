"""
Unit tests for schoolbell.app.app.
"""

import unittest

from zope.testing import doctest
from zope.interface.verify import verifyObject


# When this file grows too big, move the following tests to
# test_app.py

def doctest_SchoolBellApplication():
    r"""Tests for SchoolBellApplication.

        >>> from schoolbell.app.app import SchoolBellApplication
        >>> app = SchoolBellApplication()

        >>> from schoolbell.app.interfaces import ISchoolBellApplication
        >>> verifyObject(ISchoolBellApplication, app)
        True

    Person, group and resource containers are reachable as items of the
    application object.

        >>> from schoolbell.app.interfaces import IPersonContainer
        >>> persons = app['persons']
        >>> verifyObject(IPersonContainer, persons)
        True

        >>> from schoolbell.app.interfaces import IGroupContainer
        >>> groups = app['groups']
        >>> verifyObject(IGroupContainer, groups)
        True

    For Zopeish reasons these containers must know where they come from

        >>> persons.__parent__ is app
        True
        >>> persons.__name__
        u'persons'

        >>> groups.__parent__ is app
        True
        >>> groups.__name__
        u'groups'

    TODO: resources

    """


def doctest_PersonContainer():
    """Tests for PersonContainer

        >>> from schoolbell.app.interfaces import IPersonContainer
        >>> from schoolbell.app.app import PersonContainer
        >>> c = PersonContainer()
        >>> verifyObject(IPersonContainer, c)
        True

    Let's make sure it acts like a proper container should act

        >>> from zope.app.container.tests.test_btree import TestBTreeContainer
        >>> class Test(TestBTreeContainer):
        ...    def makeTestObject(self):
        ...        return PersonContainer()
        >>> run_unit_tests(Test)

    """

def doctest_GroupContainer():
    """Tests for GroupContainer

        >>> from schoolbell.app.interfaces import IGroupContainer
        >>> from schoolbell.app.app import GroupContainer
        >>> c = GroupContainer()
        >>> verifyObject(IGroupContainer, c)
        True

    Let's make sure it acts like a proper container should act

        >>> from zope.app.container.tests.test_btree import TestBTreeContainer
        >>> class Test(TestBTreeContainer):
        ...    def makeTestObject(self):
        ...        return GroupContainer()
        >>> run_unit_tests(Test)

    """


def run_unit_tests(testcase):
    r"""Hack to call into unittest from doctests.

        >>> import unittest
        >>> class SampleTestCase(unittest.TestCase):
        ...     def test1(self):
        ...         self.assertEquals(2 + 2, 4)
        >>> run_unit_tests(SampleTestCase)
        
        >>> class BadTestCase(SampleTestCase):
        ...     def test2(self):
        ...         self.assertEquals(2 * 2, 5)
        >>> run_unit_tests(BadTestCase) # doctest: +REPORT_NDIFF
        .F
        ======================================================================
        FAIL: test2 (schoolbell.app.tests.BadTestCase)
        ----------------------------------------------------------------------
        Traceback (most recent call last):
          File "<doctest schoolbell.app.tests.run_unit_tests[3]>", line 3, in test2
            self.assertEquals(2 * 2, 5)
          File "/usr/lib/python2.3/unittest.py", line 302, in failUnlessEqual
            raise self.failureException, \
        AssertionError: 4 != 5
        <BLANKLINE>
        ----------------------------------------------------------------------
        Ran 2 tests in 0.001s
        <BLANKLINE>
        FAILED (failures=1)

    """
    import unittest
    from StringIO import StringIO
    testsuite = unittest.makeSuite(testcase)
    output = StringIO()
    result = unittest.TextTestRunner(output).run(testsuite)
    if not result.wasSuccessful():
        print output.getvalue(),


def test_suite():
    return unittest.TestSuite([
                doctest.DocTestSuite(optionflags=doctest.ELLIPSIS),
           ])

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
