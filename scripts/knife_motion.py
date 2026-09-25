"""Level-blade press, spread, and lift motion in metres and seconds."""

import numpy as np

PRESS_END_S = 0.90
ACCEL_END_S = 1.65
DECEL_START_S = 3.15
SPREAD_END_S = 3.50
LIFT_END_S = 4.0
# Press the trailing half of the pat so butter remains in front of the blade.
# Centering the press strands it by 1.5 s; pressing farther left tears it.
PRESS_END_X_M = -0.055
# Finish near the far edge while leaving room for butter displaced ahead of
# the blade to remain on the bread.
SPREAD_END_X_M = 0.049
SPREAD_SPEED_M_S = ((SPREAD_END_X_M - PRESS_END_X_M) /
                    (DECEL_START_S - ACCEL_END_S
                     + 0.5 * (ACCEL_END_S - PRESS_END_S)
                     + 0.5 * (SPREAD_END_S - DECEL_START_S)))
START_Z_M = 0.0565
PRESS_Z_M = 0.0445
SWEEP_Z_M = 0.0365
SWEEP_END_Z_M = 0.0348
LIFT_Z_M = 0.0575


def _ease(u):
    """Zero slope and acceleration at both ends."""
    return u * u * u * (10.0 + u * (-15.0 + 6.0 * u))


def _ease_integral(u):
    """Integral of _ease from zero to u (one half at u=1)."""
    return u**4 * (2.5 + u * (-3.0 + u))


def _sweep_height(t):
    u = np.clip((t - ACCEL_END_S) / (SPREAD_END_S - ACCEL_END_S), 0.0, 1.0)
    return SWEEP_Z_M + (SWEEP_END_Z_M - SWEEP_Z_M) * _ease(u)


def knife_pose(t):
    """Press in place; spread without a pause; lift at the end.

    The blade stays level. Position and velocity are continuous at every
    transition, avoiding the impulse from the previous sharp motion changes.
    """
    t = min(max(float(t), 0.0), LIFT_END_S)
    if t < PRESS_END_S:
        u = t / PRESS_END_S
        x = PRESS_END_X_M
        z = START_Z_M + (PRESS_Z_M - START_Z_M) * _ease(u)
    elif t < ACCEL_END_S:
        duration = ACCEL_END_S - PRESS_END_S
        u = (t - PRESS_END_S) / duration
        x = PRESS_END_X_M + SPREAD_SPEED_M_S * duration * _ease_integral(u)
        z = PRESS_Z_M + (SWEEP_Z_M - PRESS_Z_M) * _ease(u)
    elif t < DECEL_START_S:
        x = (PRESS_END_X_M + 0.5 * SPREAD_SPEED_M_S * (ACCEL_END_S - PRESS_END_S)
             + SPREAD_SPEED_M_S * (t - ACCEL_END_S))
        z = _sweep_height(t)
    elif t < SPREAD_END_S:
        duration = SPREAD_END_S - DECEL_START_S
        u = (t - DECEL_START_S) / duration
        x = (PRESS_END_X_M + 0.5 * SPREAD_SPEED_M_S * (ACCEL_END_S - PRESS_END_S)
             + SPREAD_SPEED_M_S * (DECEL_START_S - ACCEL_END_S)
             + SPREAD_SPEED_M_S * duration * (u - _ease_integral(u)))
        z = _sweep_height(t)
    else:
        u = (t - SPREAD_END_S) / (LIFT_END_S - SPREAD_END_S)
        x = SPREAD_END_X_M
        z = SWEEP_END_Z_M + (LIFT_Z_M - SWEEP_END_Z_M) * _ease(u)
    # Differentiate the prescribed motion in float64. Float32 position
    # subtraction at 50 us introduces stair steps in the blade velocity.
    return np.array((x, 0.0, z), dtype=np.float64)
