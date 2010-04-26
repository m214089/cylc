#!/usr/bin/python

#         __________________________
#         |____C_O_P_Y_R_I_G_H_T___|
#         |                        |
#         |  (c) NIWA, 2008-2010   |
#         | Contact: Hilary Oliver |
#         |  h.oliver@niwa.co.nz   |
#         |    +64-4-386 0461      |
#         |________________________|


import re
import sys
import logging
from prerequisites import prerequisites

# PREREQUISITES:
# A collection of messages representing the prerequisite conditions
# of ONE TASK. "Satisfied" => the prerequisite has been satisfied.
# Prerequisites can interact with a broker (above) to get satisfied.

# FUZZY_PREREQUISITES:
# For cycle-time based prerequisites of the form "X more recent than
# or equal to this cycle time". A delimited time cutoff is expected
# in the message string. Requires a more complex satisfy_me() method.

class fuzzy_prerequisites( prerequisites ):
    def add( self, message ):

        # check for fuzziness before pass on to the base class method

        # extract fuzzy cycle time bounds from my prerequisite
        m = re.compile( "^(.*)(\d{10}:\d{10})(.*)$").match( message )
        if not m:
            # ADD ARTIFICIAL BOUNDS
            # TO DO: this is a hack, find a better way.
            m = re.compile( "^(.*)(\d{10})(.*)$").match( message )
            if m:
                [ one, two, three ] = m.groups()
                bounds = two + ':' + two
                message = re.sub( '\d{10}', bounds, message )
            else:
                log = logging.getLogger( "main." + self.task_name )            
                log.critical( '[' + self.c_time + '] No fuzzy bounds or ref time detected:' )
                log.critical( '[' + self.c_time + '] -> ' + message )
                sys.exit(1)

        prerequisites.add( self, message )

    def sharpen_up( self, fuzzy, sharp ):
        # replace a fuzzy prerequisite with the actual output message
        # that satisfied it, and set it satisfied. This allows the task
        # run() method to know the actual output message.
        del self.satisfied[ fuzzy ]
        self.satisfied[ sharp ] = True

    def satisfy_me( self, outputs ):
        log = logging.getLogger( "main." + self.task_name )            
        # can any completed outputs satisfy any of my prequisites?
        for prereq in self.satisfied.keys():
            # for each of my prerequisites
            if not self.satisfied[ prereq ]:
                # if it is not yet satisfied

                # extract fuzzy cycle time bounds from my prerequisite
                m = re.compile( "^(.*)(\d{10}:\d{10})(.*)$").match( prereq )
                [ my_start, my_minmax, my_end ] = m.groups()
                [ my_min, my_max ] = my_minmax.split(':')

                possible_satisfiers = {}
                found_at_least_one = False
                for output in outputs.satisfied.keys():

                    if outputs.satisfied[output]:
                        # extract cycle time from other's output
                        # message

                        m = re.compile( "^(.*)(\d{10})(.*)$").match( output )
                        if not m:
                            # this output can't possibly satisfy a
                            # fuzzy; move on to the next one.
                            continue
                
                        [ other_start, other_ctime, other_end ] = m.groups()

                        if other_start == my_start and other_end == my_end and other_ctime >= my_min and other_ctime <= my_max:
                            possible_satisfiers[ other_ctime ] = output
                            found_at_least_one = True
                        else:
                            continue

                if found_at_least_one: 
                    # choose the most recent possible satisfier
                    possible_ctimes = possible_satisfiers.keys()
                    possible_ctimes.sort( key = int, reverse = True )
                    chosen_ctime = possible_ctimes[0]
                    chosen_output = possible_satisfiers[ chosen_ctime ]

                    #print "FUZZY PREREQ: " + prereq
                    #print "SATISFIED BY: " + chosen_output

                    # replace fuzzy prereq with the actual output that satisfied it
                    self.sharpen_up( prereq, chosen_output )
                    log.debug( '[' + self.c_time + '] Got "' + chosen_output + '" from ' + outputs.owner_id )
                    self.satisfied_by[ prereq ] = outputs.owner_id



#    def will_satisfy_me( self, outputs ):
# TO DO: THINK ABOUT HOW FUZZY PREREQS AFFECT THIS FUNCTION ...
#        # will another's outputs, if/when completed, satisfy any of my
#        # prequisites?
#
#        # this is similar to satisfy_me() but we don't need to know the most
#        # recent satisfying output message, just if any one can do it.
#
#        for prereq in self.satisfied.keys():
#            # for each of my prerequisites
#            if not self.satisfied[ prereq ]:
##                # if my prerequisite is not already satisfied
#
#                # extract cycle time from my prerequisite
#                m = re.compile( "^(.*)(\d{10}:\d{10})(.*)$").match( prereq )
#                if not m:
#                    #log.critical( "FAILED TO MATCH MIN:MAX IN " + prereq )
#                    sys.exit(1)
#
#                [ my_start, my_minmax, my_end ] = m.groups()
#                [ my_min, my_max ] = my_minmax.split(':')
#
#                for output in outputs.satisfied.keys():
#
#                    # extract cycle time from other's output message
#                    m = re.compile( "^(.*)(\d{10})(.*)$").match( output )
#                    if not m:
#                        # this output can't possibly satisfy a
#                        # fuzzy; move on to the next one.
#                        continue
#
#                    [ other_start, other_ctime, other_end ] = m.groups()
#
#                    if other_start == my_start and other_end == my_end and other_ctime >= my_min and other_ctime <= my_max:
#                        self.sharpen_up( prereq, output )
