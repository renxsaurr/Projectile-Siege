"""
PHYSICS CALCULATIONS for Projectile Siege

assumptions:
    - no air resistance
    - constant gravity g = 9.81 m/s², pointing down
    - flat ground at y = 0
    - units: meters (m), seconds (s), degrees for angles
    - x is horizontal distance from the tower, y is height above the ground
"""
import math

# gravitational acceleration (m/s²)
G = 9.81


# ---------------------------------------------------------------------------
# UNIFORM MOTION  (constant velocity: walking enemies, airships, horizontal flight)
#     a = 0        x = x₀ + v·t
# ---------------------------------------------------------------------------

def uniform_position(x0, v, t):
    """Position after moving at constant velocity v for t seconds.

    x = x₀ + v·t        (v is negative when moving left, toward the tower)
    """
    return x0 + v * t


def time_to_travel(dx, v):
    """Time needed to cover a distance dx at constant speed v.

    From x = x₀ + v·t:   t = Δx / v
    """
    return dx / v


# ---------------------------------------------------------------------------
# FREE FALL  (an object released from rest: the Wall Drop rocks, airship bombs)
#     a = −g        vy = −g·t        y = h − ½·g·t²
# ---------------------------------------------------------------------------

def free_fall_time(h):
    """Time for an object dropped from height h to reach the ground.

    Start from   y = h − ½·g·t²
    set y = 0:   0 = h − ½·g·t²
    solve:       t = √(2h / g)
    """
    return math.sqrt(2 * h / G)


def free_fall_speed(h):
    """Speed when an object dropped from height h hits the ground.

    v = g·t, and with t = √(2h/g) this becomes   v = √(2·g·h)
    """
    return math.sqrt(2 * G * h)


# ---------------------------------------------------------------------------
# PROJECTILE MOTION  (cannon shells, catapult stones)
# The motion is split into two independent parts:
#     horizontal: no force, so constant velocity
#     vertical:   free fall, constant acceleration −g
# ---------------------------------------------------------------------------

def velocity_components(v0, angle_deg):
    """Split the launch velocity into horizontal and vertical components.

    v₀x = v₀·cosθ
    v₀y = v₀·sinθ
    """
    theta = math.radians(angle_deg)
    return v0 * math.cos(theta), v0 * math.sin(theta)


def launch_point(pivot_x, pivot_y, length, angle_deg):
    """Launch point = end of a barrel of length L rotated to angle θ around its pivot.

    x₀ = pivot_x + L·cosθ
    h₀ = pivot_y + L·sinθ
    """
    theta = math.radians(angle_deg)
    return pivot_x + length * math.cos(theta), pivot_y + length * math.sin(theta)


def speed_and_angle(vx, vy):
    """The reverse of velocity_components: rebuild v₀ and θ from the components.

    v₀ = √(vx² + vy²)
    θ  = tan⁻¹(vy / vx)
    """
    return math.hypot(vx, vy), math.degrees(math.atan2(vy, vx))


def position(x0, y0, v0x, v0y, t):
    """Position of the projectile t seconds after launch.

    x = x₀ + v₀x·t              (constant horizontal velocity)
    y = y₀ + v₀y·t − ½·g·t²     (constant downward acceleration)
    """
    x = x0 + v0x * t
    y = y0 + v0y * t - 0.5 * G * t * t
    return x, y


def vertical_velocity(v0y, t):
    """Vertical velocity t seconds after launch (positive = going up).

    vy = v₀y − g·t
    The horizontal velocity never changes: vx = v₀x.
    """
    return v0y - G * t


def time_to_apex(v0y):
    """Time to reach the highest point, where the vertical velocity is zero.

    0 = v₀y − g·t   ->   t_top = v₀y / g
    A shot fired level or downward has no rise, so this is 0.
    """
    return max(0.0, v0y / G)


def max_height(h0, v0y):
    """Highest point of the path, launched from height h₀.

    From vy² = v₀y² − 2·g·Δy with vy = 0 at the top:
        H = h₀ + v₀y² / (2g)
    A shot fired level or downward never rises above h₀.
    """
    if v0y <= 0:
        return h0
    return h0 + v0y * v0y / (2 * G)


def time_of_flight(h0, v0y):
    """Time until the projectile, launched from height h₀, hits the ground (y = 0).

    Set y = 0:        0 = h₀ + v₀y·t − ½·g·t²
    Rewrite as:       ½·g·t² − v₀y·t − h₀ = 0
    Quadratic formula, keeping the positive root:
        T = (v₀y + √(v₀y² + 2·g·h₀)) / g
    """
    return (v0y + math.sqrt(v0y * v0y + 2 * G * h0)) / G


def horizontal_range(x0, v0x, T):
    """Where the projectile lands, measured from the tower.

    R = x₀ + v₀x·T
    """
    return x0 + v0x * T


def launch_speed_to_hit(dx, dy, angle_deg):
    """Launch speed needed to hit a target at a fixed angle (used by the catapults' aim).

    dx = horizontal distance to the target (positive)
    dy = height of the target above the launch point (negative if below)

    Removing t from the x and y equations gives the trajectory equation:
        dy = dx·tanθ − g·dx² / (2·v₀²·cos²θ)
    Solving it for v₀:
        v₀ = √( g·dx² / (2·cos²θ·(dx·tanθ − dy)) )
    Returns None when the target can't be reached at this angle.
    """
    theta = math.radians(angle_deg)
    denom = 2 * math.cos(theta) ** 2 * (dx * math.tan(theta) - dy)
    if dx <= 0 or denom <= 0:
        return None
    return math.sqrt(G * dx * dx / denom)
