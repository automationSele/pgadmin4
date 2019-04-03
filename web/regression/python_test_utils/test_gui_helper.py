##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2019, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################


def close_bgprocess_popup(tester):
    """
    Allow us to close the background process popup window
    """
    tester._screenshot()

    # In cases where backup div is not closed (sometime due to some error)
    try:
        if tester.driver.find_element_by_css_selector(
                ".ajs-message.ajs-bg-bgprocess.ajs-visible"):
            tester.driver.find_element_by_css_selector(
                ".btn.btn-sm-sq.btn-primary.pg-bg-close > i").click()
            print("Debug: backup window is clicked")
    except Exception:
        print("debug: checked for backup")
        pass

    # In cases where restore div is not closed (sometime due to some error)
    try:
        if tester.driver.find_element_by_xpath(
                "//div[@class='card-header bg-primary d-flex']/div"
                "[contains(text(), 'Restoring backup')]"):
            tester.driver.find_element_by_css_selector(
                ".btn.btn-sm-sq.btn-primary.pg-bg-close > i").click()
            print("Debug: restore window is clicked")
    except Exception:
        print("debug: checked for restore")
        pass

    # In cases where maintenance window is not closed (sometime due to some
    # error)
    try:
        if tester.driver.find_element_by_xpath(
                "//div[@class='card-header bg-primary d-flex']/div"
                "[contains(text(), 'Maintenance')]"):
            tester.driver.find_element_by_css_selector(
                ".btn.btn-sm-sq.btn-primary.pg-bg-close > i").click()
            print("Debug: maintenance window is clicked")
    except Exception:
        print("debug: checked for maintenance")
        pass
