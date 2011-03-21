#!/bin/bash

set -e; trap "echo 'TEST FAILED (see output log)'" ERR

SUITE_REG=Z1TtestQrX:foobar
SUITE_DIR=${TMPDIR:-/tmp/$USER}/Z1TtestQrX/foobar

if [[ $# != 0 ]]; then
    if [[ $1 == '-h' || $1 == '--help' ]]; then
        echo "Usage: test-sched"
        echo 
        echo "Run an automated test of core cylc functionality using a new copy of"
        echo "the userguide example suite. This should be used to check that new"
        echo "developments in the cylc codebase have not introduced serious bugs."
        echo "The test runs a suite registered as 'test'; to watch its progress"
        echo "use 'cylc view'. Aside from timing differences results should be the"
        echo "same in real or dummy mode."
        echo
        echo "Currently the test does the following:"
        echo "  - Copies the userguide example suite definition directory;"
        echo "  - Registers the new suite as $SUITE_REG;"
        echo "  - Starts the suite at T0=06Z, with task X set to fail at 12Z;"
        echo "  - Unlocks the running suite;"
        echo "  - Sets a stop time at 12Z (i.e. T0+30 hours);"
        echo "  - Waits for the suite to stall as result of X failing;"
        echo "  - Inserts a new coldstart task at 06Z (T0+24 hours);"
        echo "  - Purges the failed X and dependants through to 00Z (T0+18 hours)"
        echo "    inclusive, which allows the suite to get going again at 06Z;"
        echo "  - Waits for the suite to shut itself down at the 12Z stop time."
        echo "  - Run a single task (called prep) from the suite with submit." 
        echo
        echo "Options:"
        echo "  -h, --help   Print this help message and exit."
        exit 0
    else
        echo "ERROR, no arguments required."
        exit 1
    fi
fi

#if [[ ! -x bin/cylc ]]; then
#    echo  "ERROR: run this test from the top level of a cylc installation."
#    exit 1
#fi

# START FROM A CLEAN SLATE
echo -n ">> pre-start cleanup..."
if cylc db unreg $SUITE_REG; then
    echo "unregistered old suite"
fi
rm -rf $SUITE_DIR
echo done

# COPY THE SUITE
echo -n ">> COPYING userguide example suite to $SUITE_DIR ... "
cylc db copy CylcExamples:userguide $SUITE_REG $SUITE_DIR

# log file for stdout and stderr
OUT=test.out; OUT_SCHED=test-sched.out
rm -f $OUT $OUT_SCHED

# suite log
LOG=$( cylc info log -p $SUITE_REG )
# remove old test log
rm -rf $LOG

# START UP THE TEST SUITE
echo
echo ">> STARTING at 2010010106, with TASK X to FAIL at 2010010112"
export TEST_X_FAIL_TIME=2010010112

# startup errors (e.g. due to lockserver denying access to the suite)
# won't be trapped here because we run cylc in the background!
cylc run $SUITE_REG 2010010106 >> $OUT_SCHED 2>&1 &
echo -n "   Will wait 5 seconds for startup ... "
sleep 5
echo done

# now check for startup errors, as just described.
if grep '_run failed:  1' $OUT_SCHED  > /dev/null; then
    cat $OUT_SCHED
    munge 2> /dev/null # activate trap with a non-existent command
fi

# WAIT FOR ALL TASKS AT 2010010112 TO FINISH 
# at which point the suite is stalled because X failed.
echo
echo ">> WAITING for suite to stall at 2010010112 due to failed X"
echo -n "   ."
READY=false
while ! $READY; do
    READY=true
    for TASK in A B C D E F; do
        #! grep "${TASK}%2010010106 finished" $LOG && READY=false
        ! grep "${TASK}%2010010106 finished" $LOG > /dev/null 2>&1 && READY=false
    done
    #! grep "X%2010010112 failed" $LOG && READY=false
    ! grep "X%2010010112 failed" $LOG > /dev/null 2>&1 && READY=false
    echo -n .
    sleep 1
done
echo done

# SET A STOP TIME OF
echo
echo -n ">> SETTING STOP TIME 2010010212 ..."
cylc stop -f $SUITE_REG 2010010212 >> $OUT 2>&1
echo done

# INSERT A COLDSTART TASK AT 2010010206
echo
echo -n ">> INSERTING a coldstart task at 2010010206 ..."
cylc insert -f $SUITE_REG ColdA%2010010206 >> $OUT 2>&1
cylc insert -f $SUITE_REG ColdB%2010010206 >> $OUT 2>&1
cylc insert -f $SUITE_REG ColdC%2010010206 >> $OUT 2>&1
echo done

# PURGE THE FAILED TASK AND ITS DEPENDANTS THROUGH TO 2010010200
echo
echo ">> PURGING X%2010010112 and all dependents, through to 2010010200"
echo -n "   ... "
cylc purge -f $SUITE_REG X%2010010112 2010010200 >> $OUT 2>&1
echo done

# WAIT FOR THE SUITE TO FINISH AT 2010010212
echo
echo ">> WAITING for the suite to shut down at 2010010112"
echo -n "   ."
READY=false
while ! $READY; do
    READY=true
    ! grep "ALL TASKS FINISHED" $LOG > /dev/null 2>&1 && READY=false
    echo -n .
    sleep 1
done
echo done

# RUN A SINGLE TASK
# can be one that completes successfully or fails, it doesn't matter.
echo
# PARSE OUTPUT FROM submit TO GET JOB LOG FILES:
echo ">> RUN A SINGLE TASK (prep%2010010106) from the suite"
FOO=$(cylc submit $SUITE_REG prep%2010010106 )
STDOUT=$( echo $FOO | sed -e 's/.*1> //' | sed -e 's/ 2>.*//' )
STDERR=$( echo $FOO | sed -e 's/.*2> //' | sed -e 's/ &.*$//' )
echo "TASK OUTPUT LOGS:"
echo "  $STDOUT"
echo "  $STDERR"
echo -n "   ."
READY=false
while ! $READY; do
    egrep 'cylc \(submit.*\): prep%2010010106 finished' $STDOUT 2> /dev/null && READY=true
    echo -n .
    sleep 1
done
echo done

# DELETE THE SUITE DEFINITION DIRECTORY
echo
echo -n ">> DELETING suite definition directory ..."
rm -rf $SUITE_DIR
echo done

# UNREGISTER THE test SUITE
echo
echo -n ">> UNREGISTERING suite test ..."
cylc unregister $SUITE_REG >> $OUT 2>&1
echo done

# FINISHED
echo 
echo ">> TEST OUTPUT LOGS:"
ls -l $OUT $OUT_SCHED
echo ">> CYLC MAIN LOG FOR THE TEST:"
ls -l $LOG
echo
echo ">> DONE"