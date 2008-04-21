# Make a package

# Patch ZCML module, since SchoolTool's startup is different
import apidoc
apidoc.patchZCMLModule()

# Due to a different structure, the apidoc BASEDIR is no good.
import schooltool.app
from os.path import dirname
from zope.app.apidoc import utilities
utilities.BASEDIR = dirname(dirname(dirname(dirname(schooltool.app.__file__))))
