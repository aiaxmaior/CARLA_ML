import pygame
import time
import sys # Import the sys module

pygame.init()
pygame.joystick.init()

joystick_count = pygame.joystick.get_count()
if joystick_count == 0:
    print("No joysticks found.")
    pygame.quit()
    exit()

print(f"Found {joystick_count} joysticks:")

joysticks = []
for i in range(joystick_count):
    joystick = pygame.joystick.Joystick(i)
    joystick.init()
    joysticks.append(joystick)
    print(f"  Joystick {i}: {joystick.get_name()} (Axes: {joystick.get_numaxes()}, Buttons: {joystick.get_numbuttons()}, Hats: {joystick.get_numhats()})")

# --- Control Configuration ---
# Steering
STEER_JOYSTICK_ID = 1
STEER_AXIS_ID = 0

# Throttle
THROTTLE_JOYSTICK_ID = 1
THROTTLE_AXIS_ID = 1

# Brake
BRAKE_JOYSTICK_ID = 1
BRAKE_AXIS_ID = 5

# --- Helper function for pedal mapping (handles inversion and 0-1 range) ---
def map_pedal_input(raw_value):
    # Pygame output is -1 (pressed) to 1 (released)
    # We want 0 (released) to 1 (pressed) for CARLA
    return (raw_value * -1 + 1) / 2

print("\nReading configured inputs. Press Ctrl+C to exit.")
print("Press Ctrl+C to exit.")

try:
    while True:
        # Process events to keep Pygame responsive
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise KeyboardInterrupt # Use exception to break loop

        # Initialize control values
        steer_val = 0.0
        throttle_val = 0.0
        brake_val = 0.0

        # Read Steering
        if STEER_JOYSTICK_ID < joystick_count and joysticks[STEER_JOYSTICK_ID].get_numaxes() > STEER_AXIS_ID:
            raw_steer = joysticks[STEER_JOYSTICK_ID].get_axis(STEER_AXIS_ID)
            steer_val = raw_steer # Already -1 to 1
        else:
            if STEER_JOYSTICK_ID >= joystick_count:
                sys.stdout.write("Steering joystick ID out of range! ")
            elif joysticks[STEER_JOYSTICK_ID].get_numaxes() <= STEER_AXIS_ID:
                sys.stdout.write(f"Steering axis ID {STEER_AXIS_ID} out of range for J{STEER_JOYSTICK_ID}! ")

        # Read Throttle
        if THROTTLE_JOYSTICK_ID < joystick_count and joysticks[THROTTLE_JOYSTICK_ID].get_numaxes() > THROTTLE_AXIS_ID:
            raw_throttle = joysticks[THROTTLE_JOYSTICK_ID].get_axis(THROTTLE_AXIS_ID)
            throttle_val = map_pedal_input(raw_throttle)
        else:
            if THROTTLE_JOYSTICK_ID >= joystick_count:
                sys.stdout.write("Throttle joystick ID out of range! ")
            elif joysticks[THROTTLE_JOYSTICK_ID].get_numaxes() <= THROTTLE_AXIS_ID:
                sys.stdout.write(f"Throttle axis ID {THROTTLE_AXIS_ID} out of range for J{THROTTLE_JOYSTICK_ID}! ")

        # Read Brake
        if BRAKE_JOYSTICK_ID < joystick_count and joysticks[BRAKE_JOYSTICK_ID].get_numaxes() > BRAKE_AXIS_ID:
            raw_brake = joysticks[BRAKE_JOYSTICK_ID].get_axis(BRAKE_AXIS_ID)
            brake_val = map_pedal_input(raw_brake)
        else:
            if BRAKE_JOYSTICK_ID >= joystick_count:
                sys.stdout.write("Brake joystick ID out of range! ")
            elif joysticks[BRAKE_JOYSTICK_ID].get_numaxes() <= BRAKE_AXIS_ID:
                sys.stdout.write(f"Brake axis ID {BRAKE_AXIS_ID} out of range for J{BRAKE_JOYSTICK_ID}! ")

        output_string = f"Steer: {steer_val:+.2f} | Throttle: {throttle_val:.2f} | Brake: {brake_val:.2f}"
        sys.stdout.write(" " * 150 + '\r') # Clear with spaces
        sys.stdout.write(output_string + '\r') # Write the new data
        sys.stdout.flush() # Ensure it's written to the console immediately

        time.sleep(0.01) # Small delay to avoid overwhelming the console

except KeyboardInterrupt:
    print("\nExiting.")
finally:
    pygame.quit()