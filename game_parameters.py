"""Switches and numbers that change what participants see.

Economy (provisional, meeting of 6-oct): everything is counted in moves. Players keep a bank of
moves, invest part of it in each round (the steps their pac-man can take), and every point they
collect is food that converts into FOOD_CONVERSION moves. The contract shares the points, then
food is paid.
The numbers come from a simulation of greedy players with the 3x3 fog on the 16x16 maps
(about 23 points per map): with these values someone runs out of moves in roughly 70% of the
games under commission and 30% under wages, and a player left alone usually dies within a
few rounds.
"""

# When False, the four tutorial pages before pairing are omitted.
INCLUDE_TUTORIAL = True

START_MOVES = 40  # move bank at the start of the game
START_CONTRACT = 0.0  # 0 = commission (keep your points), 1 = wages (equal split)
INITIAL_FOOD = 10  # food each participant starts with
STALE_FOOD = 2  # food lost at the start of every round, before investing
MAX_MOVES = 60  # most moves a player can invest in one round (option b, 12-oct)
MOVE_STEP = 5  # the invest slider moves in steps of 5 moves
# Food -> moves: each point (food) collected converts into this many moves. Keep it even, so
# half a point (the contract shares in halves) is a whole number of moves.
FOOD_CONVERSION = 6
FOOD_MOVES = 8  # moves paid for food every round

N_ROUNDS = 1
CONTRACT_BLOCK = 5  # rounds played with the same contract before proposing a new one

# Lobby. The game waits for BASE_GROUP_SIZE players, or starts earlier once at
# least MIN_GROUP_SIZE active players have each moved through
# JUMP_START_WAITING_PAGES lobby pages. Each round pairs them at random.
# Someone left over sits the round out. A started game that falls below
# MIN_GROUP_SIZE ends, and those players continue to the results page.
BASE_GROUP_SIZE = 8
MIN_GROUP_SIZE = 2
JUMP_START_WAITING_PAGES = 1

# When False, a newcomer cannot join a quorum that has already opened the
# game. They wait for a new group. A quorum still filling in the lobby can
# still grow. When True, a newcomer can join until fewer than
# MIN_ROUNDS_LEFT_FOR_TOP_UP of the rounds are left. The round in progress
# counts as left.
ALLOW_JOIN_WORKING_GROUPS = True
MIN_ROUNDS_LEFT_FOR_TOP_UP = 0.3

# How long, in seconds, a participant may wait in the lobby before they are
# failed and sent to the end of the experiment.
MAX_WAIT_TIME = 300

# Seconds on one lobby page. The page advances on its own after this long.
# A lobby member counts as active for UNRESPONSIVE_WAITING_PAGES of these.
WAITING_TRIAL_TIME_ESTIMATE = 8
UNRESPONSIVE_WAITING_PAGES = 4

# Successful and unsuccessful end screens continue on their own.
END_PAGE_SECONDS = 3
INTRO_PAGE_TIME_ESTIMATE = 5

# A player whose bank reaches zero is out. Their partner keeps playing alone, without a
# contract, for at most SOLO_MAX_ROUNDS more rounds, and alone food costs SOLO_FOOD_FACTOR
# times as much (alone, a player collects as much as in a pair, so without it they survive).
SOLO_MAX_ROUNDS = 5
SOLO_FOOD_FACTOR = 3
