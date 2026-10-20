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
INCLUDE_TUTORIAL = False

START_MOVES = 40  # bank at the start of the game
MAX_MOVES = 60  # most moves a player can invest in one round (option b, 12-oct)
MOVE_STEP = 5  # the invest slider moves in steps of 5 moves
# Food -> moves: each point (food) collected converts into this many moves. Keep it even, so
# half a point (the contract shares in halves) is a whole number of moves.
FOOD_CONVERSION = 6
FOOD_MOVES = 8  # moves paid for food every round

N_ROUNDS = 10
CONTRACT_BLOCK = 5  # rounds played with the same contract before proposing a new one

# A player whose bank reaches zero is out. Their partner keeps playing alone, without a
# contract, for at most SOLO_MAX_ROUNDS more rounds, and alone food costs SOLO_FOOD_FACTOR
# times as much (alone, a player collects as much as in a pair, so without it they survive).
SOLO_MAX_ROUNDS = 5
SOLO_FOOD_FACTOR = 3
