#!/usr/bin/env python

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

from cylc.conditional_simplifier import ConditionalSimplifier
from cylc.cycling.loader import get_point_relative
from cylc.prerequisite import Prerequisite
from cylc.task_outputs import (
    TASK_OUTPUT_EXPIRED, TASK_OUTPUT_SUBMITTED, TASK_OUTPUT_SUBMIT_FAILED,
    TASK_OUTPUT_STARTED, TASK_OUTPUT_SUCCEEDED, TASK_OUTPUT_FAILED)


# Task trigger names (e.g. foo:fail => bar).
# Can use "foo:fail => bar" or "foo:failed => bar", etc.
_ALT_TRIGGER_NAMES = {
    TASK_OUTPUT_EXPIRED: ["expire"],
    TASK_OUTPUT_SUBMITTED: ["submit"],
    TASK_OUTPUT_SUBMIT_FAILED: ["submit-fail"],
    TASK_OUTPUT_STARTED: ["start"],
    TASK_OUTPUT_SUCCEEDED: ["succeed"],
    TASK_OUTPUT_FAILED: ["fail"],
}


class TaskTriggerError(ValueError):
    """Illegal task trigger name."""

    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return repr(self.msg)


class TaskTrigger(object):
    """Class representing an upstream dependency.

    Args:
        task_name (str): The name of the upstream task.
        abs_cycle_point (cylc.cycling.PointBase): The cycle point of the
            upstream dependency if it is an absolute dependency.
            e.g. foo[^] => ...). Else `None`.
        cycle_point_offset (str): String representing the offset of the
            upstream task (e.g. -P1D) if this dependency is not an absolute
            one. Else None.
        qualifier (str): The task state / message for this trigger e.g.
            succeeded.

    """

    __slots__ = ['task_name', 'abs_cycle_point', 'cycle_point_offset',
                 'qualifier']

    def __init__(self, task_name, abs_cycle_point, cycle_point_offset,
                 qualifier):
        self.task_name = task_name
        self.abs_cycle_point = abs_cycle_point
        self.cycle_point_offset = cycle_point_offset
        self.qualifier = qualifier

    def get_message(self, point):
        """Return a string used to identify this trigger internally.

        Args:
            point (cylc.cycling.PointBase): The cycle point of the dependent
                task to which this trigger applies.

        Returns:
            str

        """
        if self.abs_cycle_point:
            point = self.abs_cycle_point
        elif self.cycle_point_offset:
            point = get_point_relative(
                self.cycle_point_offset, point)
        return '%s.%s %s' % (self.task_name, point, self.qualifier)

    @staticmethod
    def get_trigger_name(trigger_name):
        """Standardise a trigger name.

        E.g. 'foo:fail' becomes 'foo:failed' etc.

        """
        for standard_name, alt_names in _ALT_TRIGGER_NAMES.items():
            if trigger_name == standard_name or trigger_name in alt_names:
                return standard_name
        raise TaskTriggerError("Illegal task trigger name: %s" % trigger_name)


class Dependency(object):
    """A graph dependency in its abstract form.

    Used to generate cylc.prerequisite.Prerequisite objects.

    Args:
        exp (list): A (nested) list of TaskTrigger objects and conditional
            characters representing the dependency. E.G: "foo & bar" would be
            [<TaskTrigger("foo")>, "&", <TaskTrigger("Bar")>].
        task_triggers (set): A set of TaskTrigger objects contained in the
            expression (exp).
        suicide (bool): True if this is a suicide trigger else False.

    """

    __slots__ = ['_exp', 'task_triggers', 'suicide']

    def __init__(self, exp, task_triggers, suicide):
        self._exp = exp
        self.task_triggers = tuple(task_triggers)  # More memory efficient.
        self.suicide = suicide

    def get_prerequisite(self, point, tdef):
        """Generate a Prerequisite object from this dependency.

        Args:
            point (cylc.cycling.PointBase): The cycle point at which to
                generate the Prerequisite for.
            tdef (cylc.taskdef.TaskDef): The TaskDef of the dependent task.

        Returns:
            cylc.prerequisite.Prerequisite

        """
        # Create Prerequisite.
        cpre = Prerequisite(point, tdef.start_point)

        # Loop over TaskTrigger instances.
        for task_trigger in self.task_triggers:
            if task_trigger.cycle_point_offset is not None:
                # Inter-cycle trigger - compute the trigger's cycle point from
                # its offset.
                prereq_offset_point = get_point_relative(
                    task_trigger.cycle_point_offset, point)
                if prereq_offset_point > point:
                    # Update tdef.max_future_prereq_offset.
                    prereq_offset = prereq_offset_point - point
                    if (tdef.max_future_prereq_offset is None or
                            (prereq_offset >
                             tdef.max_future_prereq_offset)):
                        tdef.max_future_prereq_offset = (
                            prereq_offset)
                # Register task message with Prerequisite object.
                cpre.add(task_trigger.get_message(point),
                         ((prereq_offset_point < tdef.start_point) &
                          (point >= tdef.start_point)))
            else:
                # Trigger is within the same cycle point.
                # Register task message with Prerequisite object.
                cpre.add(task_trigger.get_message(point))
        cpre.set_condition(self.get_expression(point))
        return cpre

    def get_expression(self, point):
        """Return the expression as a string.

        Args:
            point (cylc.cycling.PointBase): The cycle point at which to
                generate the expression string for.

        """
        return ''.join(self._stringify_list(self._exp, point))

    @classmethod
    def _stringify_list(cls, nested_expr, point):
        """Stringify a nested list of TaskTrigger objects."""
        ret = []
        for item in nested_expr:
            if isinstance(item, TaskTrigger):
                ret.append(item.get_message(point))
            elif type(item) is list:
                ret.extend(['('] + cls._stringify_list(item, point) + [')'])
            else:
                ret.append(item)
        return ret
