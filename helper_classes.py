# Helper classes to be used in the experiment
import PIL
import json

import matplotlib
import numpy as np
import matplotlib.pyplot as plt

from pathlib import Path
from matplotlib.patches import Circle
from dataclasses import dataclass

from numpy.typing import NDArray
from matplotlib.offsetbox import (
    AnnotationBbox,
    OffsetImage
)
from typing import (
    List, Tuple, Dict, Iterable,
    Optional, Union, Any
)

from psynet.utils import get_logger

logger = get_logger()
Pos = Tuple[int, int]  # (x, y)
Number = Union[int, float]


try:
    # Assume running from psynet
    from .text_variables import STYLE
    from .game_parameters import (
        WORLD_WIDTH,
        WORLD_HEIGHT,
        NUM_COINS,
        NUM_CENTROIDS,
        DISPERSION,
        NUM_FORAGERS,
        INITIAL_WEALTH,
        COORDINATOR_INITIAL_ENDOWMENT,
        RNG,
        ASSETS_PATHS,
        MAX_MOVEMENT,
        COLLECTION_CHANCE,
    )
except:
    # If not, try normal import
    from text_variables import STYLE
    from game_parameters import (
        WORLD_WIDTH,
        WORLD_HEIGHT,
        NUM_COINS,
        NUM_CENTROIDS,
        DISPERSION,
        NUM_FORAGERS,
        INITIAL_WEALTH,
        COORDINATOR_INITIAL_ENDOWMENT,
        RNG,
        ASSETS_PATHS,
        MAX_MOVEMENT,
        COLLECTION_CHANCE,
    )


def manhattan(a: Pos, b: Pos) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def in_bounds(x: int, y: int, width: int, height: int) -> bool:
    return 0 <= x < width and 0 <= y < height


def find_coins(grid: np.ndarray) -> np.ndarray:
    """Return coin coordinates as (x, y) pairs, shape (n, 2)."""
    if grid.ndim != 2:
        raise ValueError("grid must be 2D")
    ys, xs = np.where(grid == 1)
    return np.stack([xs, ys], axis=1) if xs.size else np.zeros((0, 2), dtype=int)


def closest_coin(pos: Pos, coins_xy: np.ndarray) -> Optional[Pos]:
    """Closest coin to pos among coins_xy (x,y). Ties broken by (y, x)."""
    if coins_xy.size == 0:
        return None

    d = np.abs(coins_xy[:, 0] - pos[0]) + np.abs(coins_xy[:, 1] - pos[1])
    min_d = d.min()
    candidates = coins_xy[d == min_d]

    # Tie-break: smallest y, then smallest x
    order = np.lexsort((candidates[:, 0], candidates[:, 1]))
    best = candidates[order[0]]
    return int(best[0]), int(best[1])


@dataclass
class StepResult:
    turn: int
    from_pos: Pos
    to_pos: Pos


class ForagerBot:
    """
    Greedy coin collector on a 2D 0/1 grid.

    - Grid is a numpy array of shape (HEIGHT, WIDTH).
    - Agent position is (x, y) where x is column, y is row.
    - Each turn: jump to closest coin (Manhattan distance), collect it, record visit.
    - Ties: deterministic by (y, x).
    """

    def __init__(self, grid: np.ndarray, start: Pos, max_speed: int = 1) -> None:
        if grid.ndim != 2:
            raise ValueError("grid must be 2D")

        self.grid = grid
        self.height, self.width = grid.shape
        self.reach = max_speed
        self.collection_chance = COLLECTION_CHANCE(max_speed)

        x, y = start
        if not in_bounds(x, y, self.width, self.height):
            raise ValueError(f"start {start} out of bounds for grid (W={self.width}, H={self.height})")

        self.pos: Pos = start
        self.turn: int = 0

        self.visited: List[Pos] = [tuple(start)]
        self.collected: List[Pos] = []

        self.collection_chance: float = COLLECTION_CHANCE(max_speed)  # Default reach=1
        self._rng = RNG

    @property
    def coins_remaining(self) -> int:
        return int(self.grid.sum())

    def _next_target(self) -> Pos:
        coins_xy = find_coins(self.grid)
        pos_closest_coin = closest_coin(self.pos, coins_xy)
        distance_to_closest_coin = manhattan(pos_closest_coin, self.pos)
        if distance_to_closest_coin < 6:
            assert in_bounds(pos_closest_coin[0], pos_closest_coin[1], self.width, self.height), f"Error: next target out of bounds: {pos_closest_coin}"
            return pos_closest_coin
        else:
            adjacent_tiles = [
                [self.pos[0], np.clip(self.pos[1] - 1, 0, self.height - 1).item()],
                [np.clip(self.pos[0] + 1, 0, self.width - 1).item(), self.pos[1]],
                [self.pos[0], np.clip(self.pos[1] + 1, 0, self.height - 1).item()],
                [np.clip(self.pos[0] - 1, 0, self.width - 1).item(), self.pos[1]],
            ]
            adjacent_tiles = list(set([tuple(tile) for tile in adjacent_tiles]))
            # if len(adjacent_tiles) == 2:
            #     weights = [0.5, 0.5]
            # elif len(adjacent_tiles) == 3:
            #     weights = [0.4, 0.3, 0.3]
            # elif len(adjacent_tiles) == 4:
            #     if self.pos[0] < self.width // 2:
            #         horizontal_bias = 0.3
            #     else:
            #         horizontal_bias = 0.2
            #     if self.pos[1] < self.height // 2:
            #         vertical_bias = 0.2
            #     else:
            #         vertical_bias = 0.3
            #     weights = [1 - horizontal_bias, 1 - vertical_bias, horizontal_bias, vertical_bias]
            # else:
            #     raise ValueError("invalid adjacent tiles")
            # weights = np.array(weights) / np.sum(weights)
            # random_pos = self._rng.choice(adjacent_tiles, p=weights)
            random_pos = self._rng.choice(adjacent_tiles)
            random_pos = tuple(random_pos)
            assert in_bounds(random_pos[0], random_pos[1], self.width, self.height), f"Error: next target out of bounds: {random_pos}"
            return random_pos

    def step(self) -> None:
        """
        Execute one turn. Returns StepResult, or None if no coins remain.
        """

        target: Pos = self._next_target()
        if target is None:
            return None
        
        if target == self.pos:
            # Already on a coin
            if self.grid[self.pos[1], self.pos[0]] == 1:
                if self._rng.random() < self.collection_chance:
                    self.grid[self.pos[1], self.pos[0]] = 0
                    self.collected.append(self.pos)
            self.turn += 1

        to_pos = target
        dx = np.abs(to_pos[0] - self.pos[0])
        axis = "x" if dx > 0 else "y"
        path: List[Pos] = [self.pos]

        def step_x(tx) -> None:
            x, y = self.pos
            if x != tx:
                x += 1 if tx > x else -1
            path.append((x, y))
            self.pos = (x, y)

        def step_y(ty) -> None:
            x, y = self.pos
            if y != ty:
                y += 1 if ty > y else -1
            path.append((x, y))
            self.pos = (x, y)

        while self.pos != to_pos:

            if axis == "x":
                step_x(to_pos[0])
            else:
                step_y(to_pos[1])

            axis = "y" if axis == "x" else "x"

            self.visited.append(self.pos)

            if self.grid[self.pos[1], self.pos[0]] == 1:
                if self._rng.random() < self.collection_chance:
                    self.grid[self.pos[1], self.pos[0]] = 0
                    self.collected.append(self.pos)

        self.turn += 1
        return None

    def run(self, fuel_steps: int, max_turns: Optional[int] = 100) -> List[Pos]:
        """
        Run until all coins are collected (or max_turns reached).
        Returns the list of StepResults.
        """
        while self.coins_remaining > 0:
            self.step()
            if self.turn >= max_turns:
                break
            if len(self.visited) >= fuel_steps:
                break

        return self.visited


class World:
    """2D grid world with coins placed according to a distribution.

    Grid cells contain 1 if a coin is present, otherwise 0.
    """
    width: Optional[int] = WORLD_WIDTH
    height: Optional[int] = WORLD_HEIGHT
    coin_path: Path = ASSETS_PATHS["coin_url"]
    forager_path: Path = ASSETS_PATHS["forager_url"]
    map_path: Path = None
    num_foragers: int = NUM_FORAGERS
    _rng = RNG
    max_percentage_of_coins: float = 1.0
    threshold: float = 0.5
    steepness: float = 15.0
    min_value: float = 0.02
    proportion: float = 1.0

    def __init__(
        self,
        num_coins: int,
        num_centroids: int,
        distribution: str,
        dispersion: float,
        random_coins: Optional[float] = 0.01,
        x_bias: Optional[int] = 0,
        y_bias: Optional[int] = 0,
    ) -> None:
        logger.info(f"Initializing world...")
        # Check width and height
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width and height must be positive.")
        self.grid = np.zeros((self.height, self.width))
        logger.info(f"Grid of dimensions: {self.grid.shape} created...")
        # Check number of coins
        coin_percentage = num_coins / (self.width * self.height)
        assert coin_percentage > 0, f"Error, number of coins should be greater than 0, bu got {num_coins}"
        assert coin_percentage < self.max_percentage_of_coins, f"Error: percentage of coins in world should not be greater than {self.max_percentage_of_coins}, bu got {coin_percentage}"
        logger.info(f"Percentage of map with coins: {coin_percentage}")
        self.num_coins = num_coins
        # Check centroids
        self.num_centroids = num_centroids
        # Include biases
        self.x_bias = x_bias
        self.y_bias = y_bias
        # Check distribution
        assert(distribution in ["linear_up", "linear_down", "circular", "random"]), f"Dispersion {distribution} not supported. Choose from ['linear-up', 'linear-down', 'circular']."
        self.distribution = distribution
        # Check dispersion
        assert(dispersion > 0), f"Dispersion must be greater than 0 (but got {dispersion})."
        self.dispersion = dispersion
        self.random_coins = random_coins
        logger.info("Placing coins...")
        try:
            self.create_and_place_coins()
            logger.info(f"Coins placed successfully.")
        except Exception as e:
            logger.error(f"Failed to place coins: {e}")
            raise e


    @staticmethod
    def generate_from_json(path: Path) -> "World":
        with open(path, "r") as f:
            coins = json.load(f)
        world = World.generate_from_coins(coins)
        world.map_path = path
        return world

    @staticmethod
    def generate_from_coins(
        coins: List[Pos],
    ) -> "World":
        world_parameters = {
            "num_coins": NUM_COINS,
            "num_centroids": NUM_CENTROIDS,
            "dispersion": DISPERSION,
            "distribution": "circular"
        }
        # logger.info(f"Generating from coins...")
        # logger.info(f"Step 1: initialize world...")
        world = World(**world_parameters)
        # logger.info(f"Step 2: place coins...")
        world.clear()
        world.place_given_coins(coins)
        # logger.info(f"World ready!")
        return world

    def place_given_coins(self, coins: List[Pos]) -> None:
        if len(coins) == 0:
            return
        rows, cols = self.get_rows_and_cols(coins)
        self.grid[rows, cols] = 1

    def remove_given_coins(self, coins: List[Pos]) -> None:
        if len(coins) == 0:
            return
        rows, cols = self.get_rows_and_cols(coins)
        self.grid[rows, cols] = 0

    def get_rows_and_cols(self, coins:List[Pos]) -> Tuple[NDArray, NDArray]:
        # Separate x and y
        xs, ys = zip(*coins)
        # Make sure coins are inside boundaries
        ys = [y if 0 <= y < WORLD_HEIGHT else self._rng.integers(0, WORLD_HEIGHT - 1) for y in ys]
        xs = [x if 0 <= x < WORLD_WIDTH else self._rng.integers(0, WORLD_WIDTH - 1) for x in xs]
        # Convert to arrays
        rows = np.array(ys)
        cols = np.array(xs)
        return rows, cols

    def coin_positions(self) -> List[Pos]:
        """List of (row, col) positions where coins are present."""
        rc = np.argwhere(self.grid == 1)  # (row, col)
        coin_positions = [(int(c), int(r)) for r, c in rc]  # (x, y)
        return coin_positions

    def save_world(self) -> None:
        with open(self.map_path, "w") as map_file:
            json.dump(self.coin_positions(), map_file)

    def count_coins(self) -> int:
        """Return the number of coins currently placed."""
        return self.grid.sum()

    def clear(self) -> None:
        """Remove all coins (set all cells to 0)."""
        self.grid = np.zeros((self.height, self.width))

    def create_and_place_coins(self) -> None:
        """Create and place coins."""
        self.clear()
        if self.num_coins == 0:
            return

        if self.num_centroids > 0:
            coins_per_centroid = self.num_coins // self.num_centroids
            offset = self.num_coins - coins_per_centroid * self.num_centroids
            coins_per_centroid = [coins_per_centroid for _ in range(self.num_centroids)]
            if offset > 0:
                coins_per_centroid[-1] += offset

            centroids = self.get_centroids()
            for i, (x, y) in enumerate(centroids):
                n_coins = coins_per_centroid[i]
                sample_coins = self.sample_bivariate_normal(
                    mean=(x, y),
                    cov=((self.dispersion, 0), (0, self.dispersion)),
                    n=n_coins,
                )
                # Convert to integer coordinates
                coords_x = np.array([int(x) for x, _ in sample_coins])
                coords_y = np.array([int(y) for _, y in sample_coins])
                # Keep only coins inside boundaries
                coords_x = np.clip(coords_x, 0, self.width - 1)
                coords_y = np.clip(coords_y, 0, self.height - 1)
                # Place coins
                self.grid[coords_y, coords_x] = 1

    def get_centroids(self) -> List[Pos]:
        """Return the centroids of coins placed."""
        if self.num_centroids == 1:
            sample = [(int(self.width / 2), int(self.height / 2))]

        elif self.distribution == "linear_down":
            sample = np.linspace(0, 1, self.num_centroids + 2)[1:-1]
            sample = [(int(x * self.width), int(x * self.height)) for x in sample]

        elif self.distribution == "linear_up":
            sample = np.linspace(0, 1, self.num_centroids + 2)[1:-1]
            sample = [(int(x * self.width), self.height - int(x * self.height)) for x in sample]

        elif self.distribution == "circular":
            sample = np.linspace(0, 1, self.num_centroids + 1)[:-1]
            theta = (2.0 * np.pi) * sample
            x = np.cos(theta).tolist()
            y = np.sin(theta).tolist()
            sample = list(zip(x, y))

            x_scale = 0.1 * self.width
            y_scale = 0.1 * self.height
            sample = [(x * x_scale, y * y_scale) for x, y in sample]
            sample = [(x + 0.5 * self.width, y + 0.5 * self.height) for x, y in sample]
            sample = [(int(x), int(y)) for x, y in sample]

        elif self.distribution == "random":
            sample = self.sample_bivariate_normal(
                mean=(self.width / 2, self.height / 2),
                cov=[(self.width * 1.5, 0), (0, self.height * 1.5)],
                n=self.num_centroids,
            )
            slack = self.dispersion * 1.2
            sample = [
                (int(np.clip(x, slack, self.width - slack)), int(np.clip(y, slack, self.height - slack)))
                for x, y in sample
            ]

        elif self.distribution == "oval":
            raise NotImplementedError("oval dispersion is not yet implemented.")

        else:
            raise NotImplementedError(f"Dispersion {self.distribution} not supported. Choose from ['linear-up', 'linear-down', 'circular'].")

        sample = [
            (x + self.x_bias, y + self.y_bias) for x, y in sample
        ]
        return sample

    def create_random_coins(self, p:float) -> List[Pos]:
        """Create random coins."""
        assert(0 <= p <= 1)
        coins = []
        for x in range(self.width):
            for y in range(self.height):
                if self._rng.random() < p:
                    coins.append((x, y))
        return coins

    def __str__(self) -> str:
        """ASCII representation: '1' for coin, '.' for empty."""
        lines = []
        for r in range(self.height):
            line = "".join("1" if self.grid[r][c] else "." for c in range(self.width))
            lines.append(line)
        return "\n".join(lines)

    def render(
        self,
        coin_zoom: float = 0.1,
        coin_percentage: Optional[float] = 1,
    ) -> NDArray[np.uint8]:
        """Render the world by drawing coin images at coin positions.

        Args:
            :param coin_zoom: Relative size of the coin inside a cell (0<zoom<=1).
            :param coin_percentage: Probability of drawing a coin.
        """
        if not (0 < coin_zoom <= 1.0):
            raise ValueError("coin_zoom must be in (0, 1].")

        # Canvas sized roughly to grid, independent of DPI
        fig, ax = plt.subplots(
            figsize=(8, 5),
            dpi=100
        )

        # Light cell grid
        ax.set_xticks(np.arange(-.5, self.width, 1), minor=True)
        ax.set_yticks(np.arange(-.5, self.height, 1), minor=True)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_aspect("equal")
        # ax.set_title("World", pad=8)
        ax.set_axis_off()

        # Load coin image (RGBA supported)
        raw_coin_img = plt.imread(self.coin_path)
        coin_img = OffsetImage(raw_coin_img, zoom=coin_zoom)

        # Place the coin image centered in each occupied cell
        half = 0.5 * coin_zoom
        coins = self.coin_positions()
        for (r, c) in coins:
            if self._rng.random() < coin_percentage:
                coin_img.image.axes = ax
                ab = AnnotationBbox(
                    coin_img,
                    (c + half, r + half),
                    frameon=False
                )
                ax.add_artist(ab)

        # Render the figure to a buffer
        fig.canvas.draw()
        # Convert to a NumPy array (RGBA)
        rgba_bytes = fig.canvas.buffer_rgba().tobytes()
        width, height = fig.canvas.get_width_height()
        pil_image = PIL.Image.frombytes(mode="RGBA", size=[width, height], data=rgba_bytes)
        img = np.array(pil_image)

        plt.show()
        plt.close(fig)

    def sample_bivariate_normal(
        self,
        mean: Tuple[Number, Number],
        cov: List[Tuple[Number, Number]],
        n: int,
    ) -> List[Pos]:
        """
        Sample n points from a 2D (bivariate) normal distribution.

        Parameters
        ----------
        n : int
            Number of samples.
        mean : Iterable[float]
            Length-2 mean vector [mu_x, mu_y].
        cov : Iterable[Iterable[float]]
            2x2 covariance matrix [[var_x, cov_xy], [cov_yx, var_y]].

        Returns
        -------
        List[Tuple[float, float]] | NDArray[np.float_]
            The sampled coordinates.
        """
        mean_arr = np.asarray(mean, dtype=float)
        cov_arr = np.asarray(cov, dtype=float)

        samples: NDArray[np.float64] = self._rng.multivariate_normal(
            mean=mean_arr,
            cov=cov_arr,
            size=n
        )

        return [tuple(row) for row in samples]

    @staticmethod
    def get_probability_of_view(
        x:float,
        threshold:float,
        steepness:float,
        min_value:float,
        proportion:float,
    ) -> float:
        assert min_value >= 0
        assert min_value <= 1
        sigmoid_value = 1.0 / (1.0 + np.exp(-steepness * (x - threshold)))
        proportional_value = sigmoid_value * proportion
        return max(proportional_value, min_value)

    def unbias_coins(self) -> NDArray:
        coins = self.grid.copy()
        padding_w = self.width // 4
        padding_h = self.height // 4
        new_coins = coins[padding_h:, padding_w:].copy()
        coins[:self.width - padding_h, :self.height - padding_w] = new_coins
        coins[self.width - padding_h:, self.height - padding_w:] = np.zeros((padding_h, padding_w))
        coins = np.fliplr(coins)
        return coins

    def coordinator_view(self, information_investment:float) -> List[float]:
        # Initiate view
        terrain = np.ones((self.height, self.width)) * 140
        coins = self.coin_positions().copy()
        # Determine probability of view given investment
        p = World.get_probability_of_view(
            information_investment,
            threshold=self.threshold,
            steepness=self.steepness,
            min_value=self.min_value,
            proportion=self.proportion,
        )
        # Add random noise
        randomly_placed_coins = self.create_random_coins(1 - information_investment)
        coins += randomly_placed_coins
        # Keep only a max percentage of coins
        max_coins = int(self.count_coins() * 1)
        coins = self._rng.choice(coins, size=max_coins, replace=False).tolist()

        # Draw coins that are randomly selected to be seen according to investment
        for (x, y) in coins:
            if self._rng.random() < p:
                terrain[y, x] = 255
        return terrain.tolist()

    def generate_rgba_array(self, a_even=255, a_odd=140) -> List[float]:
        coords = self.coin_positions()
        xs, ys = zip(*coords)
        rows = np.array(ys)
        cols = np.array(xs)
        terrain = np.ones((self.height, self.width)) * a_odd
        terrain[rows, cols] = a_even
        return terrain.tolist()

    def generate_terrain(self) -> NDArray[np.int32]:
        coords = self.coin_positions()
        xs, ys = zip(*coords)
        rows = np.array(ys)
        cols = np.array(xs)
        terrain = self._rng.integers(220, 255, size=(self.height, self.width))
        terrain[rows, cols] = 0

        # Check coin positions are 0
        coin_checks = [terrain[y, x] == 0 for x, y in coords]
        assert(np.all(coin_checks))

        return terrain.tolist()

    def reward_from_bots(self, positions: List[Pos], max_speed: int) -> Tuple[List[int], List[Pos]]:
        # Create a back up of current coins
        available_coins = self.coin_positions().copy()
        # Start record of coins colleted per bot
        coins_collected = []
        tiles_visited = []
        # Collect per position
        for location in positions:
            collected, visited = self.bot_collect(
                available_coins=available_coins,
                starting_pos=location,
                max_speed=max_speed
            )
            coins_collected.append(len(collected))
            tiles_visited.append(visited)
            self.remove_given_coins(collected)
        # Restart original coins
        self.place_given_coins(available_coins)
        return coins_collected, tiles_visited

    def bot_collect(
        self,
        available_coins: List[Pos],
        starting_pos: Pos,
        max_speed: int,
    ) -> Tuple[List[Pos], List[Pos]]:
        bot = ForagerBot(
            grid=self.grid.copy(),
            start=starting_pos,
            max_speed=max_speed
        )
        steps = bot.run(
            fuel_steps=MAX_MOVEMENT(max_speed),
            max_turns=MAX_MOVEMENT(max_speed),
        )
        return bot.collected, bot.visited

    def simple_bot_collect(
        self,
        available_coins: List[Pos],
        location: Pos,
        collection_probability: Optional[float] = 0.7,
        max_distance: Optional[float] = 15.0
    ) -> List[tuple]:
        coins_collected = []
        for coin in available_coins:
            distance = World.get_distance(location, coin)
            if distance < max_distance:
                if self._rng.random() < collection_probability:
                    coins_collected.append(coin)
        return coins_collected

    def show_bots(
        self,
        locations: List[Pos],
        max_distance: Optional[float] = 15.0,
        ax: Optional[matplotlib.axes.Axes] = None,
    ) -> matplotlib.axes.Axes:
        if ax is None:
            fig, ax = plt.subplots(
                figsize=(8, 5),
                dpi=100
            )
        img = self.generate_terrain()
        ax.imshow(img)
        for location in locations:
            x, y = location
            r = max_distance
            c = Circle(
                (x, y), r,
                facecolor = "none",  # no fill
                edgecolor = "red",  # red perimeter
                linewidth = 4,  # thick outline (adjust as needed)
            )
            ax.add_patch(c)
        ax.axis('off')
        return ax

    @staticmethod
    def get_distance(point1, point2) -> float:
        x1, y1 = point1
        x2, y2 = point2
        return np.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


class WealthTracker:
    """Keeps track of the coins throughout iterations"""

    def __init__(self, coins:List[int]=INITIAL_WEALTH) -> None:
        for f_coins in coins:
            assert(isinstance(f_coins, int))
        assert(len(coins) == NUM_FORAGERS)
        self.coins = coins
        self.n_coins = sum(coins)
        self.coordinator_reward: Union[float, None] = None
        self.foragers_rewards: Union[List[float], None] = None

    def initialize(self, sliders: Dict[str, float], investment:float) -> None:

        # print("Number of coins: ", self.n_coins)

        # Calculate coordinator's wealth
        self.calculate_coordinator_reward(sliders, investment)
        # print("Coordinator reward: ", self.get_coordinator_reward())

        # Calculate foragers' breakdown
        remaining, wages, forager_commissions = self.get_foragers_breakdown(sliders)
        # print("Remaining after overhead:", remaining)
        # print("Wages:", wages)
        # print("Forager commissions:", forager_commissions)

        foragers_rewards = wages + np.array(forager_commissions)
        self.foragers_rewards = foragers_rewards.tolist()
        # print("Foragers rewards:", self.foragers_rewards)

        # logger.info(f"Foragers rewards: {self.foragers_rewards}")

    def get_foragers_breakdown(self, sliders) -> Tuple[int, int, List[int]]:
        overhead = sliders["overhead"]
        logger.info(f"Overhead: {overhead} --- n_coins: {self.n_coins}")
        remaining = self.n_coins - int(overhead * self.n_coins)

        for_salaries = int(remaining * sliders["wages"])
        if for_salaries < NUM_FORAGERS:
            for_salaries = 0
        # print("= for salaries:", for_salaries)
        salary = int(for_salaries / NUM_FORAGERS)

        if self.n_coins == 0:
            forager_proportions = np.zeros(NUM_FORAGERS)
        else:
            forager_proportions = np.array(self.coins) / self.n_coins
        # print("remaining - for salaries:", remaining - for_salaries)
        forager_commissions = forager_proportions * (remaining - for_salaries)
        forager_commissions = [int(commission) for commission in forager_commissions]

        return int(remaining), int(salary), forager_commissions

    def calculate_coordinator_reward(self, sliders: Dict[str, float], investment:float) -> None:
        # Get slider parameters
        overhead = sliders["overhead"]
        if isinstance(overhead, tuple):
            overhead = overhead[0]
        assert isinstance(overhead, float), f"Error: Expected overhead of type float, got {type(overhead)} --- {overhead=}"
        coordinator_reward = overhead * self.n_coins + int(COORDINATOR_ENDOWMENT - investment * COORDINATOR_ENDOWMENT)
        self.coordinator_reward = int(coordinator_reward)

    def get_coordinator_reward(self) -> float:
        assert(self.coordinator_reward is not None), "Coordinator wealth is not set yet. Run update() first."
        return self.coordinator_reward

    def get_forager_reward(self, forager_id: int) -> float:
        assert(self.foragers_rewards is not None), "Forager wealth is not set yet. Run update() first."
        return self.foragers_rewards[forager_id]


class RewardProcessing:
    """Processes rewards and gives feedback"""

    @staticmethod
    def get_reward(
        coins: List[int],
        sliders: Any,
        investment: float,
        trial_type: str
    ) -> float:
        trial_types = ["coordinator"] + [f"forager-{i}" for i in range(NUM_FORAGERS)]
        assert(trial_type in trial_types), f"Invalid trial type. Expected one of {trial_types} but got {trial_type}."

        accumulated_wealth = WealthTracker(coins)
        accumulated_wealth.initialize(sliders, investment)

        if trial_type == "coordinator":
            score = accumulated_wealth.get_coordinator_reward()
        elif trial_type.startswith("forager"):
            forager_id = trial_type.split("-")[1]
            forager_id = int(forager_id)
            score = accumulated_wealth.get_forager_reward(forager_id)
        else:
            raise ValueError(f"Invalid trial type: {trial_type}. Expected one of {trial_types}.")

        return score

    @staticmethod
    def get_reward_text(
        coins: List[int],
        sliders: Dict[str, float],
        investment: float,
        trial_type: str
    ) -> str:

        n_coins = sum(coins)
        score = RewardProcessing.get_reward(
            coins, sliders, investment, trial_type
        )

        coins_foraged = coins.copy()
        if trial_type.startswith("forager"):
            my_id = int(trial_type.split("-")[1])
            my_coins = coins_foraged[my_id]
            coins_foraged = [coins_foraged[my_id]] + coins_foraged[:my_id] + coins_foraged[my_id+1:]

        reward_text = f"{STYLE}"
        reward_text += f"<p>Foragers collected the following numbers of coins:</p>"
        for i, f_coins in enumerate(coins_foraged):
            reward_text += f"{f_coins} coins"
            if i < len(coins) - 2:
                reward_text += f", "
            elif i == len(coins) - 2:
                reward_text += f", and "
            else:
                pass
        reward_text += f"<p>The total number of coins collected was {n_coins}.</p>"
        reward_text += f"<br>"
        reward_text += f"<p>You score is:</p>"
        reward_text += f"<p class='final-note'> {int(score)} coins</p>"
        reward_text += f"<br>"
        reward_text += f"<p>How was your score obtained?</p>"

        if trial_type.startswith("coordinator"):
            remaining = COORDINATOR_ENDOWMENT - int(investment * COORDINATOR_ENDOWMENT)
            reward_text += f"""
        <br>
        <p>
        Your initial endowment was 10 coins and you invested {int(investment * 10)} coins in gathering information, 
        keeping {remaining} coins from your endowment.
        </p>
        <p>
        The foragers collected {int(n_coins)} coins. 
        Since the overhead is {sliders["overhead"] * 100}%, 
        you receive {int(n_coins * sliders["overhead"])} of these coins. 
        </p>
        <p>
        Adding these together ({remaining} + {int(n_coins * sliders["overhead"])}), 
        we obtain {int(score)} coins as your score.
        </p>
"""
        elif trial_type.startswith("forager"):
            accumulated_wealth = WealthTracker(coins)
            remaining, wages, forager_commissions = accumulated_wealth.get_foragers_breakdown(sliders)
            my_forager_id = int(trial_type.split("-")[1])
            if n_coins == 0:
                my_percentage = 0
            else:
                my_percentage = round(coins[my_forager_id] / n_coins * 100)
            my_commission = forager_commissions[my_forager_id]
            reward_text += f"""
            <p>
              You collected {coins[my_forager_id]} coins. With an overhead of {sliders["overhead"] * 100}%,
              you pay the coordinator {int(coins[my_forager_id] * sliders["overhead"])} coins.
              Your final score is your coins minus the overhead:
              {coins[my_forager_id]} − {int(coins[my_forager_id] * sliders["overhead"])} = {int(score)} coins.
            </p>
            """
            # reward_text += f"""
            # <p>
            #   Together, you and the other foragers collected {int(n_coins)} coins.
            #   After an overhead of {sliders["overhead"] * 100}%, {remaining} coins remained to distribute.
            # </p>
            #
            # <p>
            #   With wages set to {sliders["wages"] * 100}%, a total of {int(remaining * sliders["wages"])} coins are allocated to salaries
            #   and split equally among all foragers. This gives you a salary of {wages} coins.
            # </p>
            #
            # <p>
            #   You personally collected {coins[my_forager_id]} coins, which corresponds to {my_percentage}% of the total.
            #   You receive that same percentage of the remaining {remaining - int(remaining * sliders["wages"])} coins, for a bonus of {my_commission} coins.
            #   Your final score is your salary plus your bonus: {wages} + {my_commission} = {int(score)}.
            # </p>
            # """
        else:
            raise ValueError(f"Invalid trial type: {trial_type}.")

        return reward_text
