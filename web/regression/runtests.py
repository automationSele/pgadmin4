##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2019, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

""" This file collect all modules/files present in tests directory and add
them to TestSuite. """
from __future__ import print_function

import atexit
import json
import logging
import signal
import sys
import shutil
import traceback
import unittest
import os
import random

logger = logging.getLogger(__name__)
file_name = os.path.basename(__file__)

from testscenarios import scenarios

CURRENT_PATH = os.path.dirname(os.path.realpath(__file__))

# Set sys path to current directory so that we can import pgadmin package
root = os.path.dirname(CURRENT_PATH)

if sys.path[0] != root:
    sys.path.insert(0, root)
    os.chdir(root)

from pgadmin import create_app
import config
import regression
from regression.test_utils_pem import create_driver_instance, login_ui
from regression.test_setup import config_data
from regression.testsuite import TEMP_TEST_RESULT_FILE_PATH
from regression.feature_utils.pem.app_starter import AppStarter
from pgadmin.setup import db_upgrade, create_app_data_directory

config.TESTING_MODE = True
pgadmin_credentials = config_data
os.environ["PGADMIN_TESTING_MODE"] = "1"

# Disable upgrade checks - no need during testing, and it'll cause an error
# if there's no network connection when it runs.
config.UPGRADE_CHECK_ENABLED = False

# TODO: As SQLite is not totally removed from PEM7 yet. Once that work
# TODO: finishes from DEV team will remove below pgAdmin4 related code.
# Set environment variables for email and password
os.environ['PGADMIN_SETUP_EMAIL'] = ''
os.environ['PGADMIN_SETUP_PASSWORD'] = ''
if pgadmin_credentials:
    if 'pgAdmin4_login_credentials' in pgadmin_credentials:
        if all(item in pgadmin_credentials['pgAdmin4_login_credentials']
               for item in ['login_username', 'login_password']):
            pgadmin_credentials = pgadmin_credentials[
                'pgAdmin4_login_credentials']
            os.environ['PGADMIN_SETUP_EMAIL'] = \
                str(pgadmin_credentials['login_username'])
            os.environ['PGADMIN_SETUP_PASSWORD'] = \
                str(pgadmin_credentials['login_password'])

storage_directory = os.path.join(root, 'storage_tmp')
config.STORAGE_DIR = storage_directory
setattr(config, 'STORAGE_DIR', storage_directory)

# Always use empty storage directory
if os.path.exists(storage_directory):
    shutil.rmtree(storage_directory)

config.SQLITE_PATH = config.TEST_SQLITE_PATH
create_app_data_directory(config)

# Get the config database schema version. We store this in pgadmin.model
# as it turns out that putting it in the config files isn't a great idea
from pgadmin.model import SCHEMA_VERSION

# Delay the import test_utils as it needs updated config.SQLITE_PATH
from regression.python_test_utils import test_utils
from regression import test_utils_pem

config.SETTINGS_SCHEMA_VERSION = SCHEMA_VERSION

# Override some other defaults
from logging import WARNING

config.CONSOLE_LOG_LEVEL = WARNING

driver = None
app_starter = None
handle_cleanup = None

setattr(unittest.result.TestResult, "passed", [])

unittest.runner.TextTestResult.addSuccess = test_utils.add_success

# Override apply_scenario method as we need custom test description/name
scenarios.apply_scenario = test_utils.apply_scenario


def get_sorted_module_list(module_list):
    """This function sort the modules list"""
    return sorted(module_list, key=lambda module_tuple: module_tuple[0])


def get_test_modules(arguments, test_client, config, server):
    """
     This function loads the all modules in the tests directory into testing
     environment.
    :param arguments: this is command line arguments for module name to
    which test suite will run
    :type arguments: dict
    :param test_client: Flask test client
    :type test_client: Flask test client object
    :param config: app configuration
    :type config: dict
    :param server: server details
    :type server: dict
    :return module list: test module list
    :rtype: list
    """
    pem_module_list = []
    pgadmin_module_list = []
    exclude_pkgs = []
    gui_server_url = None

    from pgadmin.utils.route import TestsGeneratorRegistry
    global driver, app_starter, handle_cleanup

    if not config.SERVER_MODE:
        exclude_pkgs.append("browser.tests")
    if arguments['exclude'] is not None:
        exclude_pkgs += arguments['exclude'].split(',')
    if arguments['sqlonly'] is False and ("feature_tests" not in exclude_pkgs or
        "tests.gui" not in exclude_pkgs) and \
        ("tests.gui" in arguments['pkg'] or "feature_tests" in arguments['pkg'] or
         arguments['pkg'] == "pem" or "all" in arguments['pkg'] if arguments['pkg'] else
            False or arguments['pkg'] is None):
        default_browser = 'chrome'

        # Check default browser provided through command line. If provided
        # then use that browser as default browser else check for the setting
        # provided in test_config.json file.
        if (
            'default_browser' in arguments and
            arguments['default_browser'] is not None
        ):
            default_browser = arguments['default_browser'].lower()
        elif (
            config_data and
            "default_browser" in config_data
        ):
            default_browser = config_data['default_browser'].lower()

        # PEM: Using different function for driver instance creation
        driver = create_driver_instance(default_browser)

        app_starter = AppStarter(driver, config, server)

        gui_server_url = app_starter.start_app()
        # Login to PEM
        # PEM: Using different function to Login in the PEM
        login_ui(driver, test_client.test_config_data["login_username"],
                 test_client.test_config_data["login_password"])

    handle_cleanup = test_utils.get_cleanup_handler(test_client, app_starter)
    # Register cleanup function to cleanup on exit
    atexit.register(handle_cleanup)

    # Load the test modules which are in given package(i.e. in arguments.pkg)
    if arguments['pkg'] is None or arguments['pkg'] == "all":
        TestsGeneratorRegistry.load_generators('pgadmin', exclude_pkgs)
    else:
        TestsGeneratorRegistry.load_generators('pgadmin.%s' %
                                               arguments['pkg'],
                                               exclude_pkgs)
    module_list = TestsGeneratorRegistry.registry.items()

    # Separate out pgAdmin and PEM modules
    for module in module_list:
        if "pgadmin.pem" in module[0]:
            pem_module_list.append(module)
        else:
            pgadmin_module_list.append(module)

    # Sort module list so that test suite executes the test cases sequentially
    pgadmin_module_list = get_sorted_module_list(pgadmin_module_list)
    pem_module_list = get_sorted_module_list(pem_module_list)

    return pgadmin_module_list, pem_module_list, gui_server_url


def get_skipped_modules(class_name):
    """
    This function checks that given test class name exists in skipped module
    list
    :param class_name: test class name
    :type class_name: object
    :return: boolean
    """
    for module in regression.skipped_modules:
        if module in str(class_name):
            return True
    return False


def get_suite(
    module_list, test_app_client, server_information, test_db_name,
    test_server=None, pem_conn=None
):
    """
     This function add the tests to test suite and return modified test suite
      variable.
    :param module_list: test module list
    :type module_list: list
    :param test_app_client: test client
    :type test_app_client: pgadmin app object
    :param server_information
    :param test_server: server details
    :type test_server: dict
    :return pgadmin_suite: test suite with test cases
    :rtype: TestSuite
    """
    modules = []
    pgadmin_suite = unittest.TestSuite()

    # Get the each test module and add into list
    for key, klass in module_list:
        for item in klass:
            # Skipped the modules which are not supported by PEM7
            if get_skipped_modules(item):
                break
            gen = item
            modules.append(gen)

    # Set the test client to each module & generate the scenarios
    for module in modules:
        obj = module()
        obj.setApp(app)
        obj.setGuiServerUrl(gui_server_url)
        obj.setTestClient(test_app_client)
        obj.setTestServer(test_server)
        obj.setDriver(driver)
        obj.setServerInformation(server_information)
        obj.setPemConnection(pem_conn)
        obj.setTestDatabaseName(test_db_name)
        scenario = scenarios.generate_scenarios(obj)
        pgadmin_suite.addTests(scenario)
    return pgadmin_suite


def sig_handler(signo, frame):
    global handle_cleanup
    if handle_cleanup:
        handle_cleanup()


import re
terminal_colors_re = re.compile(r'(\x1b\[[0-9]{1,2}(;([0-9]{1,2})?){0,2}[mK]|\x1b\(B\x1b\[m)')

class StreamToLogger(object):

    def __init__(self, _terminal, _logger, _level):
        self.terminal = _terminal
        self.logger = _logger
        self.log_level = _level

    def __getattr__(self, _name):
        if _name == 'terminal':
            return self.terminal
        if _name == 'logger':
            return self.logger
        if _name == 'log_level':
            return self.log_level

        return getattr(self.terminal, _name)

    def write(self, buf):
        """
        This function writes the log in the logger file as well as on console

        :param buf: log message
        :type buf: str
        :return: None
        """
        global terminal_colors_re

        self.terminal.write(buf)
        for line in buf.rstrip().splitlines():
            self.logger.log(
                self.log_level, terminal_colors_re.sub('', line.rstrip())
            )

    def flush(self):
        pass


if __name__ == '__main__':
    # Failure detected?
    failure = False
    pem_modules = None
    test_result = dict()
    pem_test_result = dict()
    sql_test_result = dict()
    cov = None

    # Set signal handler for cleanup
    signal_list = dir(signal)
    required_signal_list = ['SIGTERM', 'SIGABRT', 'SIGQUIT', 'SIGINT']
    # Get the OS wise supported signals
    supported_signal_list = [sig for sig in required_signal_list if
                             sig in signal_list]
    for sig in supported_signal_list:
        signal.signal(getattr(signal, sig), sig_handler)

    # Register cleanup function to cleanup on exit
    atexit.register(test_utils_pem.pem_drop_objects)

    # Set basic logging configuration for log file
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s:%(levelname)s:%(name)s:%(message)s',
        filename=os.path.join(CURRENT_PATH, "regression.log"),
        filemode='a'
    )

    # Create logger to write log in the logger file as well as on console
    stderr_logger = logging.getLogger('STDERR')
    sys.stderr = StreamToLogger(sys.stderr, stderr_logger, logging.ERROR)

    stdout_logger = logging.getLogger('STDOUT')
    sys.stdout = StreamToLogger(sys.stdout, stdout_logger, logging.INFO)

    args = vars(test_utils_pem.add_arguments())

    servers = regression.test_setup.config_data['server_credentials']
    if args["server"] is None or \
            args["server"] > len(servers) or \
            args["server"] <= 0:
        raise Exception("Please pass valid server index value")

    server = test_utils.get_config_data(int(args["server"]) - 1)

    test_utils_pem.validate_and_adjust_arguments(args)

    print(
        "\n=============Running the test cases for '%s'============="
        % server['name'], file=sys.stdout
    )

    status, db_conn = test_utils_pem.get_pem_connection(server)

    if not status:
        print((
            'Error creating the pem database connection with '
            'error:\n{error}'
        ).format(error=db_conn), file=sys.stderr)
        sys.exit(1)

    if args['sqlonly'] is False:
        # Create test database with random number to avoid conflict in
        # parallel execution on different platforms. This database will be
        # used across all feature tests.
        test_db_name = "acceptance_test_db" + str(random.randint(10000, 65535))

        # Create database
        test_utils.create_database(server, test_db_name)

    db_conn.execute("SELECT VERSION();")
    version = db_conn.fetchall()
    print(
        "(Backend Database Version : {0})\n".format(version[0][0]),
        file=sys.stdout
    )

    # Delete SQLite db file if exists
    if os.path.isfile(config.TEST_SQLITE_PATH):
        os.remove(config.TEST_SQLITE_PATH)

    pem_conn, cov = test_utils_pem.init(args, server, db_conn)

    if server['default_binary_paths'] is not None:
        config.DEFAULT_BINARY_PATHS = server['default_binary_paths']

    # Create the app
    app = create_app()

    app.PGADMIN_RUNTIME = True
    if config.SERVER_MODE is True:
        app.PGADMIN_RUNTIME = False

    with app.app_context():
        db_upgrade(app)

    # Override DB name in app instance
    app.config['WTF_CSRF_ENABLED'] = False
    app.PGADMIN_KEY = ''
    app.config.update({'SESSION_COOKIE_DOMAIN': None})
    test_client = app.test_client()
    test_client.test_config_data = {
        "login_username": server["username"],
        "login_password": server["db_password"]
    }

    test_utils_pem.login_tester_account_pem(test_client)
    status, conn = test_utils_pem.get_pem_connection(server)

    # Set new pem and db connections as a global variables to use in utils
    # files
    regression.pem_conn = conn
    regression.db_conn = db_conn

    # Create test users for multiple users functionality
    test_utils_pem.create_users_for_test_client(server["db_password"])

    # get the user id
    pem_conn.execute("select oid from pg_roles where rolname='%s'"
                     %(server['username']))
    user_oid = pem_conn.fetchone()[0]

    # set the binary path for server
    if server['default_binary_paths'] is not None:
        test_utils_pem.configure_preferences(
            server['default_binary_paths'],
            user_oid)

    # Get test module list
    pgadmin_modules, pem_modules, gui_server_url = get_test_modules(
        args, test_client, config, server
    )
    server_information = test_utils.create_parent_server_node(server)
    setattr(config, 'STORAGE_DIR', storage_directory)

    server_disp_name = "{0}\t({1})".format(server['name'], version[0][0])

    if args['nosql'] is False:
        ran_tests, failed_cases, skipped_cases, passed_cases = \
            test_utils_pem.execute_sql_testsuite(args, server)
        sql_test_result[server_disp_name] = \
            [ran_tests, failed_cases, skipped_cases, passed_cases]

        if len(sql_test_result[server_disp_name][1]) != 0:
            failure = True

    # Run test suite for pgAdmin4
    if args['sqlonly'] is False:
        print("\nExecuting pgAdmin4 test cases", file=sys.stdout)
        if len(pgadmin_modules) > 0:
            suite = get_suite(
                pgadmin_modules, test_client, server_information, test_db_name,
                test_server=server, pem_conn=conn
                )
            from colour_runner.runner import ColourTextTestRunner
            tests = ColourTextTestRunner(
                stream=sys.stdout, descriptions=True, verbosity=2
            ).run(suite)

            ran_tests, failed_cases, skipped_cases, passed_cases = \
                test_utils_pem.get_tests_result(tests)

            test_result[server_disp_name] = \
                [ran_tests, failed_cases, skipped_cases, passed_cases]

            # Set empty list for 'passed' parameter for each testRun.
            # So that it will not append same test case name
            unittest.result.TestResult.passed = []

            if len(failed_cases) > 0:
                failure = True
        else:
            print("\nRan 0 tests", file=sys.stdout)

    if args['sqlonly'] is False:
        # Run test suite for PEM
        print("\nExecuting PEM test cases", file=sys.stdout)
        if len(pem_modules) > 0:
            pem_total_passed_cases = pem_total_failed_cases = \
                pem_total_skipped_cases = 0
            pem_failed_cases = pem_skipped_cases = {}
            pem_passed_cases = pem_failed_cases_json = pem_skipped_cases_json = {}

            suite = get_suite(
                pem_modules, test_client, server_information, test_db_name,
                test_server=server, pem_conn=conn
            )
            from colour_runner.runner import ColourTextTestRunner
            tests = ColourTextTestRunner(
                stream=sys.stdout, descriptions=True, verbosity=2
            ).run(suite)

            pem_ran_tests, pem_failed_cases, pem_skipped_cases, pem_passed_cases \
                = test_utils_pem.get_tests_result(tests)

            pem_test_result[server_disp_name] = [
                pem_ran_tests, pem_failed_cases, pem_skipped_cases,
                pem_passed_cases
            ]

            unittest.result.TestResult.passed = []
            if len(pem_failed_cases) > 0:
                failure = True
        else:
            print("\nRan 0 tests", file=sys.stdout)

    with open(TEMP_TEST_RESULT_FILE_PATH, 'w+') as outfile:
        json.dump({
            "pem": pem_test_result, "pgadmin": test_result,
            "sql": sql_test_result
        }, outfile, indent=2)

    print(
        "\n\n=== Dropping the objects created while running the testsuite ==="
    )

    # Drop the testing database created initially
    if args['sqlonly'] is False and db_conn:
        test_utils.drop_database(db_conn, test_db_name)

    # Delete test server
    test_utils.delete_test_server(test_client)

    # Stop code coverage
    if test_utils_pem.is_coverage_enabled(args):
        test_utils_pem.stop_coverage(cov)

    # Unset environment variable
    del os.environ["PGADMIN_TESTING_MODE"]

    if failure:
        sys.exit(1)
    else:
        sys.exit(0)
