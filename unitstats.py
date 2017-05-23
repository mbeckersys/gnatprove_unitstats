#!/usr/bin/env python

"""
This is a plug-in for GNAT programming studio (GPS), which post-processes the results from
GNATprove and shows them as HTML report.

(C) 2017 by Martin Becker <becker@rcs.ei.tum.de>

"""

__author__ = "Martin Becker"
__copyright__ = "Copyright 2017, Martin Becker"
__license__ = "GPL"
__version__ = "1.0.1"
__email__ = "becker@rcs.ei.tum.de"
__status__ = "Testing"


import os.path
import re
import GPS
import gps_utils
import text_utils
from modules import Module
import inspect, os, sys, subprocess
from shutil import copyfile
try:
    import gnatprove_unitstats
except:
    print "Unit Stats not available due to failing import of 'gnatprove_unitstats'"
    gnatprove_unitstats = None

LIGHTGREEN="#D5F5E3"
LIGHTRED="#F9E79F"
LIGHTORANGE="#FFBF00"
DEFAULT_SLOCPERLLR=20

MENUITEMS = """
<submenu before="Window">
      <Title>SPARK</Title>
        <menu action="Unit Statistics Text Report">
          <Title>Unit Statistics/Text Report</Title>
        </menu>
        <menu action="Unit Statistics HTML Report">
          <Title>Unit Statistics/HTML Report</Title>
        </menu>
</submenu>
"""

PROPERTIES="""
 <project_attribute
      name="NotebookFile"
      package="Prove"
      editor_page="Unit Statistics"
      editor_section="Single"
      description="The path to the Jupyter notebook to render GNATprove outputs." >
      <string type="file" default="" />
  </project_attribute>
  <project_attribute
      name="UnitsSorting"
      package="Prove"
      editor_page="Unit Statistics"
      editor_section="Single"
      description="The sort order for tabular output, comma-separated (e.g., 'coverage,success,alpha')" >
      <string default="" />
  </project_attribute>
  <project_attribute
      name="UnitsInclude"
      package="Prove"
      editor_page="Unit Statistics"
      editor_section="Single"
      description="Include only units, comma-separated" >
      <string default="" />
  </project_attribute>
  <project_attribute
      name="UnitsExclude"
      package="Prove"
      editor_page="Unit Statistics"
      editor_section="Single"
      description="Exclude units, comma-separated" >
      <string default="" />
  </project_attribute>
"""

class Unitstats(object):

    notebook = None
    prjdir = None
    prjfile = None
    sorting = None
    exclude = None
    include = None

    def __init__(self):
        """
        Various initializations done before the gps_started hook
        """

        XML = """
        <documentation_file>
           <name>http://docs.python.org/2/tutorial/</name>
           <descr>Unitstats tutorial</descr>
           <menu>/Help/Unitstats/Tutorial</menu>
           <category>Scripts</category>
        </documentation_file>
        <documentation_file>
          <shell lang="python">"""

        XML += """GPS.execute_action('display reqtrace help')</shell>
          <descr>Unit Statistics</descr>
          <menu>/Help/Unitstats/Help</menu>
          <category>Scripts</category>
        </documentation_file>
        """

        XML += PROPERTIES;

        XML += MENUITEMS;

        GPS.parse_xml(XML)


    def gps_started(self):
        """
        Initializations done after the gps_started hook (add menu)
        """

        # declare local function as action (menu, shortcut, etc.)
        gps_utils.make_interactive(
            callback=self.text_report,
            name='Unit Statistics Text Report')

        gps_utils.make_interactive(
            callback=self.html_report,
            name='Unit Statistics HTML Report')

        GPS.Hook("project_view_changed").add(self._project_recomputed)
        GPS.Hook("before_exit_action_hook").add(self._before_exit)
        GPS.Hook("project_changed").add(self._project_loaded)
        GPS.Hook("project_saved").add(self._project_loaded)


    def text_report(self, to_file=None, as_json=False):
        """
        Iterate over all files and subprograms and warn if a subprogram has no requirements.
        Note that requirements are checked for their exsistence against a database. Only
        existing requirements are considered.
        """
        print ("Unit Statistics Text Report...")

        # find all object folders of all projects
        prjs = GPS.Project.root().dependencies(recursive=True)
        if not isinstance(prjs, list):
            prjs = [GPS.Project.root()]
        else:
            prjs.append(GPS.Project.root())
        ofolders=[]
        for p in prjs: ofolders.extend (p.object_dirs())

        gfolders=[]
        for of in ofolders:
            g = os.path.join(of, "gnatprove")
            if os.path.exists(g): gfolders.append(g)

        if 0 < len(gfolders):
            print ("GNATprove folders: {}".format(gfolders))
            print ("project sorting={}".format(self.sorting))
            return gnatprove_unitstats.compute_unitstats (prjfile=self.prjfile, gfolders=gfolders, \
                                                   sorting=self.sorting, table=True, details=False, \
                                                   include=self.include, exclude=self.exclude,
                                                   to_file=to_file, as_json=as_json)
        else:
            print ("Did not find any gnatprove folders in object directories: {}".format(ofolders))
            return 1


    def _scriptpath(self):
        """return path of this script"""
        return os.path.split(os.path.realpath(__file__))[0]

    def html_report(self):
        """
        Iterate over all files and subprograms and warn if a subprogram has no requirements.
        Note that requirements are checked for their exsistence against a database. Only
        existing requirements are considered.
        """
        print ("Unit Statistics HTML Report...")

        statsdir = GPS.Project.root().object_dirs()[0]
        logfile=os.path.join(statsdir, "unitstats.log")
        if self.text_report (to_file=logfile, as_json=True):
            print("Error while generating report")
            return False

        if self.notebook is None: self.notebook = os.path.join(self._scriptpath(), "unitstats.ipynb")

        if not os.path.exists(self.notebook):
            print ("ERROR: Jupyter Notebook not found: {}".format(self.notebook))
            return

        def run_or_bailout(msg, cmd, graceful=False):
            print msg + " " + " ".join(cmd)
            try:
                subprocess.check_call(" ".join(cmd), shell=True)
            except:
                print "ERROR: " + msg
                if not graceful: raise OSError("command failed:" + str(cmd))


        # 2. execute notebook FIXME: make asynchronous
        nb = os.path.join(statsdir, "unitstats.ipynb")
        copyfile(self.notebook, nb)
        run_or_bailout ("Generating Report in {}...".format(statsdir),
                       ['unitstats=' + logfile, 'runipy', '-o ' + nb], graceful=True)

        # 3. convert notebook to html
        nbh = os.path.join(statsdir, "unitstats.html")
        run_or_bailout ("Converting to HTML...", ['ipython','nbconvert',nb,'--to html'])

        # 4. show html
        run_or_bailout("Show Report", ["sensible-browser", nbh])

    def _show_locations(self,reqs):
        """
        TODO: show unit info in location window
        """
        if not reqs:
            return

        GPS.Editor.register_highlighting("Proven Unit", LIGHTGREEN)
        GPS.Editor.register_highlighting("Failing Unit", LIGHTORANGE)
        for req,values in reqs.iteritems():
            for ref in values["locations"]: # each requirement can have multiple references
                if values["in_database"]:
                    category = "Valid Requirements"
                    txt="References " + req;
                else:
                    category = "Invalid Requirements"
                    txt="Nonexisting requirement " + req;
                GPS.Locations.add(category=category,
                                  file=GPS.File(ref["file"]),
                                  line=ref["line"],
                                  column=ref["col"],
                                  message=txt,
                                  highlight=category)


    def _project_loaded (self, hook_name):
        self.prjfile = GPS.Project.root().file()
        self.prjdir = self.prjfile.directory()

        # path to notebook
        self.notebook = GPS.Project.root().get_attribute_as_string ("NotebookFile", "Prove")
        if not self.notebook:
            self.notebook = prjdir + os.path.sep + "unitstats.ipynb"
        else:
            if not os.path.isabs(self.notebook):
                self.notebook = prjdir + os.path.sep + self.notebook
        print "Unitstats Notebook=" + self.notebook

        # sort order
        self.sorting = GPS.Project.root().get_attribute_as_string ("UnitsSorting", "Prove")
        if self.sorting is not None:
            self.sorting = self.sorting.split(",")
            print ("Project-wide unit sorting is: {}".format(self.sorting))

        # include/exclude
        self.include = GPS.Project.root().get_attribute_as_string ("UnitsInclude", "Prove")
        if self.include:
            self.include = self.sorting.split(",")
        self.exclude = GPS.Project.root().get_attribute_as_string ("UnitsExclude", "Prove")
        if self.exclude:
            self.exclude = self.sorting.split(",")


    def _project_recomputed(self, hook_name):
        """
        if python is one of the supported language for the project, add various
        predefined directories that may contain python files, so that shift-F3
        works to open these files as it does for the Ada runtime
        """

        GPS.Project.add_predefined_paths(
            sources="%splug-ins" % GPS.get_home_dir())
        try:
            GPS.Project.root().languages(recursive=True).index("python")
            # The rest is done only if we support python
            GPS.Project.add_predefined_paths(sources=os.pathsep.join(sys.path))
        except:
            pass


    def _before_exit(self, hook_name):
        """Called before GPS exits"""
        return 1


# Create the class once GPS is started, so that the filter is created
# immediately when parsing XML, and we can create our actions.
if gnatprove_unitstats:
    module = Unitstats()
    GPS.Hook("gps_started").add(lambda h: module.gps_started())
