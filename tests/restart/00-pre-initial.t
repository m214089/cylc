#!/bin/bash
# THIS FILE IS PART OF THE CYLC SUITE ENGINE.
# Copyright (C) 2008-2017 NIWA
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#-------------------------------------------------------------------------------
# Test restarting a suite with pre-initial cycle dependencies
. "$(dirname "$0")/test_header"
set_test_number 4
install_suite "${TEST_NAME_BASE}" "${TEST_NAME_BASE}"

run_ok "${TEST_NAME_BASE}-validate" cylc validate "${SUITE_NAME}"
suite_run_ok "${TEST_NAME_BASE}-run" cylc run --debug "${SUITE_NAME}"
suite_run_ok "${TEST_NAME_BASE}-restart" cylc restart --debug "${SUITE_NAME}"

if ! which sqlite3 > /dev/null; then
    skip 1 "sqlite3 not installed?"
    purge_suite "${SUITE_NAME}"
    exit 0
fi
RUND="$(cylc get-global-config --print-run-dir)"
sqlite3 "${RUND}/${SUITE_NAME}/log/db" \
    'SELECT name, cycle, status FROM task_states ORDER BY name, cycle' \
    >'final-state'
contains_ok 'final-state' "${TEST_SOURCE_DIR}/${TEST_NAME_BASE}/ref-state"

purge_suite "${SUITE_NAME}"
exit
